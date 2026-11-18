from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ledgerguard.accounts import service as accounts
from ledgerguard.app import workflows
from ledgerguard.app.deps import auth_ctx, idempotent_response, limit
from ledgerguard.common.context import Ctx
from ledgerguard.ledger import service

router = APIRouter(tags=["ledger"])


class DepositIn(BaseModel):
    amount_minor: int = Field(gt=0, le=10**12)
    description: str = Field(default="Depunere", max_length=200)


# ————————————————————————————————————————

class ReverseIn(BaseModel):
    reason: str = Field(min_length=3, max_length=200)


# ————————————————————————————————————————

@router.get("/accounts/{account_id}/entries")
def list_entries(
    account_id: str,
    date_from: str | None = None,
    date_to: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
    ctx: Ctx = Depends(auth_ctx("customer", "compliance", "admin")),
) -> dict[str, Any]:
    account = accounts.get_account(ctx, account_id)
    accounts.authorize_account(ctx, account)
    return service.list_entries(ctx, account_id, date_from, date_to, cursor, limit)


# ————————————————————————————————————————

@router.post("/accounts/{account_id}/deposit", status_code=201, dependencies=[Depends(limit("money"))])
def deposit(
    account_id: str,
    body: DepositIn,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ctx: Ctx = Depends(auth_ctx("admin")),
) -> JSONResponse:
    payload = {"account_id": account_id, **body.model_dump()}
    return idempotent_response(
        ctx,
        idempotency_key,
        "ledger.deposit",
        payload,
        lambda: (201, workflows.deposit(ctx, account_id, body.amount_minor, body.description)),
    )


# ————————————————————————————————————————

@router.get("/ledger/transactions/{transaction_id}")
def get_transaction(
    transaction_id: str, ctx: Ctx = Depends(auth_ctx("compliance", "admin"))
) -> dict[str, Any]:
    return service.get_transaction(ctx, transaction_id)


# ————————————————————————————————————————

@router.post(
    "/ledger/transactions/{transaction_id}/reverse", status_code=201, dependencies=[Depends(limit("money"))]
)
def reverse_transaction(
    transaction_id: str,
    body: ReverseIn,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ctx: Ctx = Depends(auth_ctx("admin")),
) -> JSONResponse:
    payload = {"transaction_id": transaction_id, **body.model_dump()}
    return idempotent_response(
        ctx,
        idempotency_key,
        "ledger.reverse",
        payload,
        lambda: (
            201,
            {"reversal_id": service.reverse_transaction(ctx, transaction_id, body.reason)},
        ),
    )


# ————————————————————————————————————————

@router.get("/ledger/invariants")
def invariants(ctx: Ctx = Depends(auth_ctx("compliance", "admin"))) -> dict[str, Any]:
    return service.check_invariants(ctx)
