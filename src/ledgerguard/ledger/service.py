from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ledgerguard.accounts import service as accounts
from ledgerguard.audit import service as audit
from ledgerguard.common.clock import normalize_instant, to_iso
from ledgerguard.common.context import Ctx
from ledgerguard.common.db import Row
from ledgerguard.common.errors import conflict, invalid, not_found
from ledgerguard.common.ids import new_id
from ledgerguard.common.money import SUPPORTED_CURRENCIES, to_ron_minor
from ledgerguard.common.pagination import build_page, clamp_limit, decode_seq
from ledgerguard.fx.service import RateRef
from ledgerguard.ledger import repository


@dataclass(frozen=True)
class Leg:
    account_id: str
    currency: str
    amount_minor: int
    rate: RateRef
    amount_ron_minor: int | None = None


# ————————————————————————————————————————

def _ron_value(leg: Leg) -> int:
    if leg.amount_ron_minor is not None:
        return leg.amount_ron_minor
    magnitude = to_ron_minor(abs(leg.amount_minor), leg.rate.rate_e8)
    return magnitude if leg.amount_minor > 0 else -magnitude


# ————————————————————————————————————————

def _validate_legs(legs: list[Leg]) -> None:
    if len(legs) < 2:
        raise invalid("ledger_too_few_legs", "O tranzacție are cel puțin două înregistrări.")
    totals: dict[str, int] = {}
    for leg in legs:
        if leg.amount_minor == 0:
            raise invalid("ledger_zero_amount", "Sumele nule nu sunt permise.")
        totals[leg.currency] = totals.get(leg.currency, 0) + leg.amount_minor
    unbalanced = {currency: total for currency, total in totals.items() if total != 0}
    if unbalanced:
        raise invalid("ledger_unbalanced", "Tranzacția nu este echilibrată pe monedă.", {"totals": unbalanced})


# ————————————————————————————————————————

def _check_accounts(ctx: Ctx, legs: list[Leg]) -> None:
    deltas: dict[str, int] = {}
    currencies: dict[str, str] = {}
    for leg in legs:
        deltas[leg.account_id] = deltas.get(leg.account_id, 0) + leg.amount_minor
        currencies[leg.account_id] = leg.currency
    for account_id, delta in deltas.items():
        account = accounts.get_account(ctx, account_id)
        if account["currency"] != currencies[account_id]:
            raise invalid("currency_mismatch", "Moneda înregistrării nu corespunde contului.")
        if account["status"] != "active":
            raise conflict("account_closed", "Contul este închis.", {"account_id": account_id})
        if not account["allow_negative"] and delta < 0:
            balance = repository.account_balance(ctx.conn, account_id, None)
            if balance + delta < 0:
                raise invalid(
                    "insufficient_funds",
                    "Fonduri insuficiente.",
                    {"account_id": account_id, "available_minor": balance, "required_minor": -delta},
                )


# ————————————————————————————————————————

def post_transaction(
    ctx: Ctx,
    kind: str,
    legs: list[Leg],
    description: str,
    transfer_id: str | None = None,
    reverses_id: str | None = None,
) -> str:
    _validate_legs(legs)
    transaction_id = new_id("txn")
    now = to_iso(ctx.clock.now())
    with ctx.transaction():
        _check_accounts(ctx, legs)
        values = [_ron_value(leg) for leg in legs]
        repository.insert_transaction(
            ctx.conn, transaction_id, kind, description, transfer_id, reverses_id, sum(values), ctx.correlation_id, now
        )
        for leg, ron_value in zip(legs, values, strict=True):
            repository.insert_entry(
                ctx.conn,
                transaction_id,
                leg.account_id,
                leg.currency,
                leg.amount_minor,
                ron_value,
                leg.rate.rate_e8,
                leg.rate.rate_id,
                leg.rate.valid_from,
                now,
            )
        audit.record(
            ctx,
            "ledger.posted",
            "transaction",
            transaction_id,
            {"kind": kind, "entries": len(legs), "transfer_id": transfer_id, "reverses_id": reverses_id},
        )
    return transaction_id


# ————————————————————————————————————————

def reverse_transaction(ctx: Ctx, transaction_id: str, reason: str) -> str:
    with ctx.transaction():
        original = repository.get_transaction(ctx.conn, transaction_id)
        if original is None:
            raise not_found("transaction", transaction_id)
        if original["kind"] == "reversal":
            raise conflict("cannot_reverse_reversal", "O tranzacție inversă nu poate fi inversată.")
        if repository.reversal_of(ctx.conn, transaction_id) is not None:
            raise conflict("already_reversed", "Tranzacția a fost deja inversată.")
        legs = [
            Leg(
                entry["account_id"],
                entry["currency"],
                -int(entry["amount_minor"]),
                RateRef(entry["fx_rate_id"], entry["currency"], int(entry["fx_rate_e8"]), entry["fx_rate_at"]),
                -int(entry["amount_ron_minor"]),
            )
            for entry in repository.entries_for_transaction(ctx.conn, transaction_id)
        ]
        reversal_id = post_transaction(
            ctx, "reversal", legs, f"Inversare: {reason}", original["transfer_id"], transaction_id
        )
        audit.record(ctx, "ledger.reversed", "transaction", transaction_id, {"reversal_id": reversal_id, "reason": reason})
    return reversal_id


# ————————————————————————————————————————

def balance(ctx: Ctx, account_id: str, at_iso: str | None = None) -> int:
    return repository.account_balance(ctx.conn, account_id, at_iso)


# ————————————————————————————————————————

def get_transaction(ctx: Ctx, transaction_id: str) -> Row:
    found = repository.get_transaction(ctx.conn, transaction_id)
    if found is None:
        raise not_found("transaction", transaction_id)
    reversal = repository.reversal_of(ctx.conn, transaction_id)
    return {
        **found,
        "entries": repository.entries_for_transaction(ctx.conn, transaction_id),
        "reversed_by": reversal["id"] if reversal else None,
    }


# ————————————————————————————————————————

def list_entries(
    ctx: Ctx,
    account_id: str,
    date_from: str | None,
    date_to: str | None,
    cursor: str | None,
    limit: int,
) -> dict[str, Any]:
    size = clamp_limit(limit)
    start = normalize_instant(date_from) if date_from else None
    end = normalize_instant(date_to) if date_to else None
    rows = repository.list_entries(ctx.conn, account_id, start, end, decode_seq(cursor), size)
    return build_page(rows, size)


# ————————————————————————————————————————

def check_invariants(ctx: Ctx) -> dict[str, Any]:
    sums = {currency: 0 for currency in SUPPORTED_CURRENCIES}
    for row in repository.currency_sums(ctx.conn):
        sums[row["currency"]] = int(row["total"])
    unbalanced = repository.unbalanced_transactions(ctx.conn)
    negative: list[dict[str, Any]] = []
    for account_id in accounts.account_ids_without_overdraft(ctx):
        value = repository.account_balance(ctx.conn, account_id, None)
        if value < 0:
            negative.append({"account_id": account_id, "balance_minor": value})
    ok = all(total == 0 for total in sums.values()) and not unbalanced and not negative
    return {
        "ok": ok,
        "currency_sums": sums,
        "unbalanced_transactions": unbalanced,
        "negative_accounts": negative,
        "entry_count": repository.count_entries(ctx.conn),
    }
