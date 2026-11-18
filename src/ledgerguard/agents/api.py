from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ledgerguard.agents import service, testing
from ledgerguard.app import workflows
from ledgerguard.app.deps import auth_ctx, idempotent_response, limit
from ledgerguard.common.context import Ctx

router = APIRouter(tags=["agents"])


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


# ————————————————————————————————————————

class SyntheticIn(BaseModel):
    seed: int = Field(default=1, ge=0, le=10**9)
    customers: int = Field(default=5, ge=1, le=50)
    transfers_per_customer: int = Field(default=3, ge=0, le=20)
    password: str | None = Field(default=None, min_length=8, max_length=200)


# ————————————————————————————————————————

class ProposalsIn(BaseModel):
    seed: int = Field(default=1, ge=0, le=10**9)
    count: int = Field(default=8, ge=0, le=100)
    from_openapi: bool = True


# ————————————————————————————————————————

@router.post("/assistant/chat", dependencies=[Depends(limit("money"))])
def chat(body: ChatIn, request: Request, ctx: Ctx = Depends(auth_ctx("customer"))) -> dict[str, Any]:
    return service.assistant_chat(ctx, request.app.state.llm, body.message)


# ————————————————————————————————————————

@router.post("/assistant/actions/{action_id}/confirm", dependencies=[Depends(limit("money"))])
def confirm_action(
    action_id: str,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ctx: Ctx = Depends(auth_ctx("customer")),
) -> JSONResponse:
    return idempotent_response(
        ctx,
        idempotency_key,
        "assistant.confirm",
        {"action_id": action_id},
        lambda: (200, workflows.confirm_assistant_action(ctx, action_id)),
    )


# ————————————————————————————————————————

@router.post("/assistant/actions/{action_id}/reject")
def reject_action(action_id: str, ctx: Ctx = Depends(auth_ctx("customer"))) -> dict[str, Any]:
    return service.reject_action(ctx, action_id)


# ————————————————————————————————————————

@router.post("/quality/synthetic", status_code=201)
def synthetic(body: SyntheticIn, ctx: Ctx = Depends(auth_ctx("admin"))) -> dict[str, Any]:
    return testing.generate_synthetic_data(ctx, body.seed, body.customers, body.transfers_per_customer, body.password)


# ————————————————————————————————————————

@router.get("/quality/panel")
def panel(ctx: Ctx = Depends(auth_ctx("compliance", "admin"))) -> dict[str, Any]:
    path = ctx.settings.reports_dir / "robot" / "output.xml"
    return testing.quality_panel(ctx, path)


# ————————————————————————————————————————

@router.post("/quality/proposals", status_code=201)
def create_proposals(body: ProposalsIn, request: Request, ctx: Ctx = Depends(auth_ctx("admin"))) -> dict[str, Any]:
    scenarios = testing.propose_scenarios(ctx, body.seed, body.count)
    api_cases = testing.propose_from_openapi(ctx, request.app.openapi()) if body.from_openapi else {"created": 0}
    return {"scenarios_created": scenarios["created"], "api_cases_created": api_cases["created"]}


# ————————————————————————————————————————

@router.get("/quality/proposals")
def list_proposals(
    kind: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
    ctx: Ctx = Depends(auth_ctx("compliance", "admin")),
) -> dict[str, Any]:
    return testing.list_proposals(ctx, kind, cursor, limit)


# ————————————————————————————————————————

@router.post("/quality/triage")
def triage(ctx: Ctx = Depends(auth_ctx("admin"))) -> dict[str, Any]:
    path = ctx.settings.reports_dir / "robot" / "output.xml"
    ingested = testing.ingest_robot_output(ctx, path)
    return {"run": ingested, "verdicts": testing.triage(ctx, path) if path.exists() else []}
