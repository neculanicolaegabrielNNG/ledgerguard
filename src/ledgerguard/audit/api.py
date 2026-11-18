from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ledgerguard.app.deps import auth_ctx
from ledgerguard.audit import service
from ledgerguard.common.context import Ctx

router = APIRouter(tags=["audit"])


class WebhookIn(BaseModel):
    url: str = Field(min_length=8, max_length=500)
    events: list[str] = Field(min_length=1)


# ————————————————————————————————————————

@router.get("/audit")
def search_audit(
    entity_type: str | None = None,
    entity_id: str | None = None,
    actor: str | None = None,
    action: str | None = None,
    correlation_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    q: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
    ctx: Ctx = Depends(auth_ctx("compliance", "admin")),
) -> dict[str, Any]:
    filters = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "actor": actor,
        "action": action,
        "correlation_id": correlation_id,
        "date_from": date_from,
        "date_to": date_to,
    }
    return service.search(ctx, filters, q, cursor, limit)


# ————————————————————————————————————————

@router.post("/webhooks", status_code=201)
def create_webhook(body: WebhookIn, ctx: Ctx = Depends(auth_ctx("admin"))) -> dict[str, Any]:
    return service.create_webhook(ctx, body.url, body.events)


# ————————————————————————————————————————

@router.get("/webhooks")
def list_webhooks(ctx: Ctx = Depends(auth_ctx("admin"))) -> dict[str, Any]:
    return {"items": service.list_webhooks(ctx)}


# ————————————————————————————————————————

@router.get("/webhooks/deliveries")
def list_deliveries(
    cursor: str | None = None, limit: int = 50, ctx: Ctx = Depends(auth_ctx("admin"))
) -> dict[str, Any]:
    return service.list_deliveries(ctx, cursor, limit)


# ————————————————————————————————————————

@router.delete("/webhooks/{webhook_id}", status_code=204)
def delete_webhook(webhook_id: str, ctx: Ctx = Depends(auth_ctx("admin"))) -> None:
    service.delete_webhook(ctx, webhook_id)
