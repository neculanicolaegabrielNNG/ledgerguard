from __future__ import annotations

from typing import Any

from ledgerguard.accounts import repository
from ledgerguard.audit import service as audit
from ledgerguard.common.clock import to_iso
from ledgerguard.common.context import Ctx
from ledgerguard.common.db import Row
from ledgerguard.common.errors import forbidden, invalid, not_found
from ledgerguard.common.ids import new_id
from ledgerguard.common.money import SUPPORTED_CURRENCIES
from ledgerguard.common.pagination import build_page, clamp_limit, decode_seq

CASH_KEY = "CASH-{currency}"
EXCHANGE_KEY = "FX-{currency}"


def create_customer(ctx: Ctx, name: str) -> Row:
    cleaned = name.strip()
    if not cleaned or len(cleaned) > 200:
        raise invalid("invalid_name", "Numele clientului este invalid.")
    customer_id = new_id("cus")
    with ctx.transaction():
        repository.insert_customer(ctx.conn, customer_id, cleaned, to_iso(ctx.clock.now()))
        audit.record(ctx, "customer.created", "customer", customer_id, {"name": cleaned})
    return {"id": customer_id, "name": cleaned}


# ————————————————————————————————————————

def get_customer(ctx: Ctx, customer_id: str) -> Row:
    found = repository.get_customer(ctx.conn, customer_id)
    if found is None:
        raise not_found("customer", customer_id)
    return found


# ————————————————————————————————————————

def create_account(ctx: Ctx, customer_id: str, currency: str, name: str) -> Row:
    if currency not in SUPPORTED_CURRENCIES:
        raise invalid("unsupported_currency", "Moneda nu este suportată.", {"currency": currency})
    get_customer(ctx, customer_id)
    account_id = new_id("acc")
    label = name.strip() or f"Cont {currency}"
    with ctx.transaction():
        repository.insert_account(
            ctx.conn, account_id, customer_id, currency, "customer", None, label, False, to_iso(ctx.clock.now())
        )
        audit.record(
            ctx, "account.created", "account", account_id, {"customer_id": customer_id, "currency": currency}
        )
    return get_account(ctx, account_id)


# ————————————————————————————————————————

def get_account(ctx: Ctx, account_id: str) -> Row:
    found = repository.get_account(ctx.conn, account_id)
    if found is None:
        raise not_found("account", account_id)
    return found


# ————————————————————————————————————————

def authorize_account(ctx: Ctx, account: Row) -> None:
    if ctx.actor.role == "customer" and account["customer_id"] != ctx.actor.customer_id:
        raise forbidden()


# ————————————————————————————————————————

def list_accounts(
    ctx: Ctx,
    customer_id: str | None,
    currency: str | None,
    cursor: str | None,
    limit: int,
) -> dict[str, Any]:
    size = clamp_limit(limit)
    scoped_customer = ctx.actor.customer_id if ctx.actor.role == "customer" else customer_id
    rows = repository.list_accounts(ctx.conn, scoped_customer, currency, "customer", decode_seq(cursor), size)
    return build_page(rows, size)


# ————————————————————————————————————————

def ensure_system_accounts(ctx: Ctx) -> None:
    with ctx.transaction():
        for currency in SUPPORTED_CURRENCIES:
            for template, kind, label in (
                (CASH_KEY, "system_cash", "Numerar extern"),
                (EXCHANGE_KEY, "fx_exchange", "Schimb valutar"),
            ):
                key = template.format(currency=currency)
                if repository.get_by_system_key(ctx.conn, key) is None:
                    repository.insert_account(
                        ctx.conn,
                        new_id("sys"),
                        None,
                        currency,
                        kind,
                        key,
                        f"{label} {currency}",
                        True,
                        to_iso(ctx.clock.now()),
                    )


# ————————————————————————————————————————

def system_account(ctx: Ctx, template: str, currency: str) -> Row:
    key = template.format(currency=currency)
    found = repository.get_by_system_key(ctx.conn, key)
    if found is None:
        raise not_found("system_account", key)
    return found


# ————————————————————————————————————————

def count_customers(ctx: Ctx) -> int:
    return repository.count_customers(ctx.conn)


# ————————————————————————————————————————

def account_ids_without_overdraft(ctx: Ctx) -> list[str]:
    return repository.list_ids_without_overdraft(ctx.conn)


# ————————————————————————————————————————

def all_accounts(ctx: Ctx) -> list[Row]:
    return repository.list_all(ctx.conn)
