from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterator
from typing import Any

from fastapi import Header, Request
from fastapi.responses import JSONResponse

from ledgerguard.auth import service as auth
from ledgerguard.common.context import Actor, Ctx
from ledgerguard.common.errors import forbidden
from ledgerguard.common.idempotency import run_idempotent, validate_key
from ledgerguard.common.ids import new_id
from ledgerguard.app.wiring import make_ctx

def open_ctx(request: Request, actor: Actor) -> Ctx:
    correlation_id = getattr(request.state, "correlation_id", None) or new_id("cor")
    return make_ctx(request.app.state.settings, request.app.state.clock, correlation_id, actor)


# ————————————————————————————————————————

def anonymous_ctx(request: Request) -> Iterator[Ctx]:
    ctx = open_ctx(request, Actor.anonymous())
    try:
        yield ctx
    finally:
        ctx.conn.close()


# ————————————————————————————————————————

def auth_ctx(*roles: str) -> Callable[..., Iterator[Ctx]]:
    def dependency(request: Request, authorization: str | None = Header(default=None)) -> Iterator[Ctx]:
        ctx = open_ctx(request, Actor.anonymous())
        try:
            actor = auth.actor_from_header(ctx, authorization)
            if roles and actor.role not in roles:
                raise forbidden()
            yield ctx.as_actor(actor)
        finally:
            ctx.conn.close()

    return dependency


# ————————————————————————————————————————

def limit(group: str) -> Callable[..., None]:
    def dependency(request: Request, authorization: str | None = Header(default=None)) -> None:
        settings = request.app.state.settings
        maximum = settings.rate_limit_login if group == "login" else settings.rate_limit_money
        if authorization:
            identity = hashlib.sha256(authorization.encode("utf-8")).hexdigest()[:24]
        else:
            identity = request.client.host if request.client else "unknown"
        request.app.state.limiter.check(f"{group}:{identity}", maximum)

    return dependency


# ————————————————————————————————————————

def idempotent_response(
    ctx: Ctx,
    key: str | None,
    operation: str,
    payload: dict[str, Any],
    action: Callable[[], tuple[int, dict[str, Any]]],
) -> JSONResponse:
    validated = validate_key(key)
    scope = ctx.actor.user_id or ctx.actor.label
    result = run_idempotent(ctx, scope, validated, operation, payload, action)
    response = JSONResponse(result.body, status_code=result.status_code)
    if result.replayed:
        response.headers["Idempotent-Replay"] = "true"
    return response
