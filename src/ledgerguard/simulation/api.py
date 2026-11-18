from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from ledgerguard.app.deps import auth_ctx
from ledgerguard.common.clock import FixedClock
from ledgerguard.common.context import Ctx
from ledgerguard.simulation import service
from ledgerguard.simulation.runner import Advance, HttpxSimClient

router = APIRouter(tags=["simulation"])


class RunIn(BaseModel):
    strategy: str
    seed: int = Field(default=1, ge=0, le=10**9)
    benign_count: int = Field(default=10, ge=0, le=200)


# ————————————————————————————————————————

def _advancer(request: Request) -> Advance | None:
    clock = request.app.state.clock
    if not isinstance(clock, FixedClock):
        return None

    def advance(seconds: int) -> None:
        clock.advance(seconds)

    return advance


# ————————————————————————————————————————

@router.post("/simulation/runs", status_code=201)
def start_run(
    body: RunIn,
    request: Request,
    authorization: str | None = Header(default=None),
    ctx: Ctx = Depends(auth_ctx("admin")),
) -> dict[str, Any]:
    token = (authorization or "")[7:].strip()
    client = TestClient(request.app, base_url="http://simulation.local", raise_server_exceptions=False)
    try:
        return service.run(
            ctx, HttpxSimClient(client), token, body.strategy, body.seed, body.benign_count, _advancer(request)
        )
    finally:
        client.close()


# ————————————————————————————————————————

@router.get("/simulation/runs")
def list_runs(
    cursor: str | None = None, limit: int = 20, ctx: Ctx = Depends(auth_ctx("compliance", "admin"))
) -> dict[str, Any]:
    return service.list_runs(ctx, cursor, limit)


# ————————————————————————————————————————

@router.get("/simulation/runs/{run_id}")
def get_run(run_id: str, ctx: Ctx = Depends(auth_ctx("compliance", "admin"))) -> dict[str, Any]:
    return service.get_run(ctx, run_id)
