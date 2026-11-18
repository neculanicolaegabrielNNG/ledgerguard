from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ledgerguard.app import workflows
from ledgerguard.app.deps import anonymous_ctx, auth_ctx
from ledgerguard.common.clock import to_iso
from ledgerguard.common.context import Ctx

router = APIRouter(tags=["system"])


@router.get("/health")
def health(ctx: Ctx = Depends(anonymous_ctx)) -> dict[str, Any]:
    return {"status": "ok", "time": to_iso(ctx.clock.now())}


# ————————————————————————————————————————

@router.get("/timetravel")
def time_travel(at: str, ctx: Ctx = Depends(auth_ctx("compliance", "admin"))) -> dict[str, Any]:
    return workflows.time_travel(ctx, at)
