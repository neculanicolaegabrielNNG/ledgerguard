from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ledgerguard.app import workflows
from ledgerguard.app.deps import auth_ctx, idempotent_response, limit
from ledgerguard.common.context import Ctx
from ledgerguard.transfers import service

router = APIRouter(tags=["transfers"])


class TransferIn(BaseModel):
    from_account_id: str = Field(min_length=1, max_length=64)
    to_account_id: str = Field(min_length=1, max_length=64)
    amount_minor: int = Field(gt=0, le=10**12)
    description: str = Field(default="", max_length=200)


# ————————————————————————————————————————

class ScheduleIn(BaseModel):
    from_account_id: str = Field(min_length=1, max_length=64)
    to_account_id: str = Field(min_length=1, max_length=64)
    amount_minor: int = Field(gt=0, le=10**12)
    description: str = Field(default="", max_length=200)
    interval_seconds: int = Field(ge=60)
    first_run_at: str | None = None
    ends_at: str | None = None


# ————————————————————————————————————————

@router.get("/transfers/quote")
def quote(
    from_account_id: str,
    to_account_id: str,
    amount_minor: int,
    ctx: Ctx = Depends(auth_ctx("customer")),
) -> dict[str, Any]:
    return service.quote(ctx, from_account_id, to_account_id, amount_minor)


# ————————————————————————————————————————

@router.post("/transfers", status_code=201, dependencies=[Depends(limit("money"))])
def create_transfer(
    body: TransferIn,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ctx: Ctx = Depends(auth_ctx("customer")),
) -> JSONResponse:
    return idempotent_response(
        ctx,
        idempotency_key,
        "transfers.create",
        body.model_dump(),
        lambda: (
            201,
            workflows.create_transfer_detail(
                ctx, body.from_account_id, body.to_account_id, body.amount_minor, body.description
            ),
        ),
    )


# ————————————————————————————————————————

@router.get("/transfers")
def list_transfers(
    state: str | None = None,
    account_id: str | None = None,
    customer_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
    ctx: Ctx = Depends(auth_ctx("customer", "compliance", "admin")),
) -> dict[str, Any]:
    return service.list_transfers(ctx, state, account_id, customer_id, date_from, date_to, cursor, limit)


# ————————————————————————————————————————

@router.get("/transfers/{transfer_id}")
def get_transfer(
    transfer_id: str, ctx: Ctx = Depends(auth_ctx("customer", "compliance", "admin"))
) -> dict[str, Any]:
    return workflows.transfer_detail(ctx, transfer_id)


# ————————————————————————————————————————

@router.post("/transfers/{transfer_id}/cancel")
def cancel_transfer(transfer_id: str, ctx: Ctx = Depends(auth_ctx("customer"))) -> dict[str, Any]:
    return workflows.cancel_transfer(ctx, transfer_id)


# ————————————————————————————————————————

@router.post("/scheduled-payments", status_code=201)
def create_scheduled(body: ScheduleIn, ctx: Ctx = Depends(auth_ctx("customer"))) -> dict[str, Any]:
    return service.create_scheduled_payment(
        ctx,
        body.from_account_id,
        body.to_account_id,
        body.amount_minor,
        body.description,
        body.interval_seconds,
        body.first_run_at,
        body.ends_at,
    )


# ————————————————————————————————————————

@router.get("/scheduled-payments")
def list_scheduled(ctx: Ctx = Depends(auth_ctx("customer"))) -> dict[str, Any]:
    return {"items": service.list_scheduled_payments(ctx)}


# ————————————————————————————————————————

@router.delete("/scheduled-payments/{payment_id}", status_code=204)
def cancel_scheduled(payment_id: str, ctx: Ctx = Depends(auth_ctx("customer"))) -> None:
    service.cancel_scheduled_payment(ctx, payment_id)
