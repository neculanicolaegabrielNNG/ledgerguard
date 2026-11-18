from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ledgerguard.accounts import service
from ledgerguard.app.deps import auth_ctx
from ledgerguard.common.context import Ctx
from ledgerguard.common.errors import invalid
from ledgerguard.ledger import service as ledger

router = APIRouter(tags=["accounts"])


class AccountIn(BaseModel):
    currency: str = Field(min_length=3, max_length=3)
    name: str = Field(default="", max_length=100)
    customer_id: str | None = None


# ————————————————————————————————————————

def _with_balance(ctx: Ctx, account: dict[str, Any]) -> dict[str, Any]:
    return {**account, "balance_minor": ledger.balance(ctx, account["id"])}


# ————————————————————————————————————————

@router.get("/accounts")
def list_accounts(
    customer_id: str | None = None,
    currency: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
    ctx: Ctx = Depends(auth_ctx("customer", "compliance", "admin")),
) -> dict[str, Any]:
    page = service.list_accounts(ctx, customer_id, currency, cursor, limit)
    page["items"] = [_with_balance(ctx, item) for item in page["items"]]
    return page


# ————————————————————————————————————————

@router.post("/accounts", status_code=201)
def create_account(body: AccountIn, ctx: Ctx = Depends(auth_ctx("customer", "admin"))) -> dict[str, Any]:
    if ctx.actor.role == "customer":
        customer_id = ctx.actor.customer_id
    else:
        customer_id = body.customer_id
    if not customer_id:
        raise invalid("customer_required", "Clientul este obligatoriu.")
    return _with_balance(ctx, service.create_account(ctx, customer_id, body.currency, body.name))


# ————————————————————————————————————————

@router.get("/accounts/{account_id}")
def get_account(
    account_id: str, ctx: Ctx = Depends(auth_ctx("customer", "compliance", "admin"))
) -> dict[str, Any]:
    account = service.get_account(ctx, account_id)
    service.authorize_account(ctx, account)
    return _with_balance(ctx, account)
