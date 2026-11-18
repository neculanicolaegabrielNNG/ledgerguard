from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from ledgerguard.app.deps import auth_ctx
from ledgerguard.audit import service as audit
from ledgerguard.common.context import Ctx
from ledgerguard.common.errors import bad_request
from ledgerguard.common.money import FOREIGN_CURRENCIES
from ledgerguard.fx import service
from ledgerguard.fx.providers import SimulatedProvider

router = APIRouter(tags=["fx"])


class ShockIn(BaseModel):
    currency: str
    bps: int = Field(ge=-5000, le=5000)


# ————————————————————————————————————————

class FreezeIn(BaseModel):
    frozen: bool


# ————————————————————————————————————————

@router.get("/fx/rates")
def get_rates(ctx: Ctx = Depends(auth_ctx("customer", "compliance", "admin"))) -> dict[str, Any]:
    return {"items": service.current_rates(ctx)}


# ————————————————————————————————————————

@router.get("/fx/rates/history")
def get_history(
    currency: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
    ctx: Ctx = Depends(auth_ctx("customer", "compliance", "admin")),
) -> dict[str, Any]:
    return service.history(ctx, currency, cursor, limit)


# ————————————————————————————————————————

@router.get("/fx/alerts")
def get_alerts(
    currency: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
    ctx: Ctx = Depends(auth_ctx("compliance", "admin")),
) -> dict[str, Any]:
    return service.alerts(ctx, currency, cursor, limit)


# ————————————————————————————————————————

@router.post("/fx/refresh")
def refresh_rates(request: Request, ctx: Ctx = Depends(auth_ctx("admin"))) -> dict[str, Any]:
    return service.refresh(ctx, request.app.state.fx_provider)


# ————————————————————————————————————————

@router.post("/fx/shock")
def shock_rate(body: ShockIn, request: Request, ctx: Ctx = Depends(auth_ctx("admin"))) -> dict[str, Any]:
    if body.currency not in FOREIGN_CURRENCIES:
        raise bad_request("unsupported_currency", "Moneda nu poate fi șocată.", {"currency": body.currency})
    simulated: SimulatedProvider = request.app.state.simulated
    new_rate = simulated.shock(body.currency, body.bps)
    with ctx.transaction():
        audit.record(ctx, "fx.shock", "fx_provider", "simulated", {"currency": body.currency, "bps": body.bps})
    return {"currency": body.currency, "provider_rate_e8": new_rate}


# ————————————————————————————————————————

@router.post("/fx/freeze")
def freeze_rates(body: FreezeIn, request: Request, ctx: Ctx = Depends(auth_ctx("admin"))) -> dict[str, Any]:
    simulated: SimulatedProvider = request.app.state.simulated
    simulated.freeze(body.frozen)
    with ctx.transaction():
        audit.record(ctx, "fx.freeze", "fx_provider", "simulated", {"frozen": body.frozen})
    return {"frozen": simulated.frozen}
