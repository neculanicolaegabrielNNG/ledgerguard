from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ledgerguard.agents import service as agents
from ledgerguard.app import workflows
from ledgerguard.app.deps import auth_ctx, idempotent_response, limit
from ledgerguard.common.context import Ctx
from ledgerguard.common.errors import invalid
from ledgerguard.fraud import service

router = APIRouter(tags=["fraud"])


class RuleUpdateIn(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    params: dict[str, int] | None = None
    priority: int | None = Field(default=None, ge=0, le=1000)
    effect: str | None = None
    active: bool | None = None


# ————————————————————————————————————————

class DecisionIn(BaseModel):
    action: str
    comment: str = Field(min_length=3, max_length=500)


# ————————————————————————————————————————

@router.get("/fraud/rules")
def list_rules(
    include_history: bool = False,
    rule_id: str | None = None,
    ctx: Ctx = Depends(auth_ctx("compliance", "admin")),
) -> dict[str, Any]:
    return {"items": service.list_rules(ctx, include_history, rule_id)}


# ————————————————————————————————————————

@router.put("/fraud/rules/{rule_id}")
def update_rule(rule_id: str, body: RuleUpdateIn, ctx: Ctx = Depends(auth_ctx("admin"))) -> dict[str, Any]:
    changes = body.model_dump(exclude_none=True)
    if not changes:
        raise invalid("empty_update", "Nu s-a transmis nicio modificare.")
    return service.update_rule(ctx, rule_id, changes)


# ————————————————————————————————————————

@router.get("/fraud/cases")
def list_cases(
    status: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
    ctx: Ctx = Depends(auth_ctx("compliance", "admin")),
) -> dict[str, Any]:
    return service.list_cases(ctx, status, cursor, limit)


# ————————————————————————————————————————

@router.get("/fraud/cases/{case_id}")
def get_case(case_id: str, ctx: Ctx = Depends(auth_ctx("compliance", "admin"))) -> dict[str, Any]:
    return workflows.case_detail(ctx, case_id)


# ————————————————————————————————————————

@router.post("/fraud/cases/{case_id}/decision", dependencies=[Depends(limit("money"))])
def decide_case(
    case_id: str,
    body: DecisionIn,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ctx: Ctx = Depends(auth_ctx("compliance", "admin")),
) -> JSONResponse:
    payload = {"case_id": case_id, **body.model_dump()}
    return idempotent_response(
        ctx,
        idempotency_key,
        "fraud.decision",
        payload,
        lambda: (200, workflows.decide_case(ctx, case_id, body.action, body.comment)),
    )


# ————————————————————————————————————————

@router.post("/fraud/cases/{case_id}/analyze")
def analyze_case(
    case_id: str, request: Request, ctx: Ctx = Depends(auth_ctx("compliance", "admin"))
) -> dict[str, Any]:
    return agents.analyze_case(ctx, request.app.state.llm, case_id)


# ————————————————————————————————————————

@router.get("/fraud/graph")
def get_graph(days: int = 30, ctx: Ctx = Depends(auth_ctx("compliance", "admin"))) -> dict[str, Any]:
    return service.build_graph(ctx, max(1, min(days, 365)))
