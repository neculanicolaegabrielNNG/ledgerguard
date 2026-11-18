from __future__ import annotations

from typing import Any

from ledgerguard.accounts import service as accounts
from ledgerguard.audit import service as audit
from ledgerguard.common.clock import iso_after, normalize_instant, parse_iso, to_iso
from ledgerguard.common.context import Actor, Ctx
from ledgerguard.common.db import Row
from ledgerguard.common.errors import DomainError, conflict, forbidden, invalid, not_found
from ledgerguard.common.idempotency import run_idempotent
from ledgerguard.common.ids import new_id
from ledgerguard.common.pagination import build_page, clamp_limit, decode_seq
from ledgerguard.fraud import service as fraud
from ledgerguard.fx import service as fx
from ledgerguard.ledger import service as ledger
from ledgerguard.ledger.service import Leg
from ledgerguard.transfers import repository
from ledgerguard.transfers.state_machine import assert_transition

SIMILARITY_PERCENT = 30


def authorize_transfer(ctx: Ctx, transfer: Row) -> None:
    if ctx.actor.role == "customer" and transfer["customer_id"] != ctx.actor.customer_id:
        raise forbidden()


# ————————————————————————————————————————

def get_transfer(ctx: Ctx, transfer_id: str) -> Row:
    found = repository.get_transfer(ctx.conn, transfer_id)
    if found is None:
        raise not_found("transfer", transfer_id)
    authorize_transfer(ctx, found)
    return found


# ————————————————————————————————————————

def transitions_of(ctx: Ctx, transfer_id: str) -> list[Row]:
    return repository.list_transitions(ctx.conn, transfer_id)


# ————————————————————————————————————————

def _transition(ctx: Ctx, transfer_id: str, target: str, reason: str) -> None:
    current = repository.get_transfer(ctx.conn, transfer_id)
    if current is None:
        raise not_found("transfer", transfer_id)
    assert_transition(current["state"], target)
    now = to_iso(ctx.clock.now())
    repository.update_state(ctx.conn, transfer_id, target, now)
    repository.insert_transition(ctx.conn, transfer_id, current["state"], target, ctx.actor.label, reason, now)
    audit.record(
        ctx,
        "transfer.transition",
        "transfer",
        transfer_id,
        {"from": current["state"], "to": target, "reason": reason},
    )


# ————————————————————————————————————————

def _legs(ctx: Ctx, source: Row, target: Row, conversion: fx.Conversion) -> list[Leg]:
    amount = conversion.source_amount_minor
    payout = conversion.target_amount_minor
    if conversion.source_currency == conversion.target_currency:
        return [
            Leg(source["id"], conversion.source_currency, -amount, conversion.source_rate),
            Leg(target["id"], conversion.target_currency, amount, conversion.source_rate),
        ]
    exchange_in = accounts.system_account(ctx, accounts.EXCHANGE_KEY, conversion.source_currency)
    exchange_out = accounts.system_account(ctx, accounts.EXCHANGE_KEY, conversion.target_currency)
    return [
        Leg(source["id"], conversion.source_currency, -amount, conversion.source_rate),
        Leg(exchange_in["id"], conversion.source_currency, amount, conversion.source_rate),
        Leg(exchange_out["id"], conversion.target_currency, -payout, conversion.target_rate),
        Leg(target["id"], conversion.target_currency, payout, conversion.target_rate),
    ]


# ————————————————————————————————————————

def _execute(ctx: Ctx, transfer_id: str) -> None:
    transfer = repository.get_transfer(ctx.conn, transfer_id)
    assert transfer is not None
    source = accounts.get_account(ctx, transfer["from_account_id"])
    target = accounts.get_account(ctx, transfer["to_account_id"])
    conversion = fx.quote_conversion(ctx, transfer["amount_minor"], source["currency"], target["currency"])
    transaction_id = ledger.post_transaction(
        ctx, "transfer", _legs(ctx, source, target, conversion), transfer["description"], transfer_id=transfer_id
    )
    repository.update_execution(
        ctx.conn,
        transfer_id,
        conversion.target_amount_minor,
        conversion.amount_ron_minor,
        conversion.spread_bps,
        transaction_id,
        to_iso(ctx.clock.now()),
    )


# ————————————————————————————————————————

def quote(ctx: Ctx, from_account_id: str, to_account_id: str, amount_minor: int) -> dict[str, Any]:
    source = accounts.get_account(ctx, from_account_id)
    target = accounts.get_account(ctx, to_account_id)
    accounts.authorize_account(ctx, source)
    conversion = fx.quote_conversion(ctx, amount_minor, source["currency"], target["currency"])
    return {
        "source_currency": conversion.source_currency,
        "target_currency": conversion.target_currency,
        "source_amount_minor": conversion.source_amount_minor,
        "target_amount_minor": conversion.target_amount_minor,
        "amount_ron_minor": conversion.amount_ron_minor,
        "spread_bps": conversion.spread_bps,
        "source_rate_e8": conversion.source_rate.rate_e8,
        "target_rate_e8": conversion.target_rate.rate_e8,
    }


# ————————————————————————————————————————

def _validate_parties(source: Row, target: Row) -> None:
    if source["kind"] != "customer" or target["kind"] != "customer":
        raise invalid("account_not_transferable", "Transferurile sunt permise doar între conturi de client.")
    if source["id"] == target["id"]:
        raise invalid("same_account", "Contul sursă și destinație sunt identice.")
    if source["status"] != "active" or target["status"] != "active":
        raise conflict("account_closed", "Unul dintre conturi este închis.")


# ————————————————————————————————————————

def create_transfer(
    ctx: Ctx,
    from_account_id: str,
    to_account_id: str,
    amount_minor: int,
    description: str,
    channel: str = "api",
) -> Row:
    if ctx.actor.role != "customer" or not ctx.actor.customer_id:
        raise forbidden("Doar clienții pot iniția transferuri.")
    if amount_minor <= 0:
        raise invalid("invalid_amount", "Suma trebuie să fie pozitivă.")
    with ctx.transaction():
        source = accounts.get_account(ctx, from_account_id)
        target = accounts.get_account(ctx, to_account_id)
        accounts.authorize_account(ctx, source)
        _validate_parties(source, target)
        available = ledger.balance(ctx, source["id"])
        if available < amount_minor:
            raise invalid(
                "insufficient_funds",
                "Fonduri insuficiente.",
                {"account_id": source["id"], "available_minor": available, "required_minor": amount_minor},
            )
        conversion = fx.quote_conversion(ctx, amount_minor, source["currency"], target["currency"])
        transfer_id = new_id("trf")
        repository.insert_transfer(
            ctx.conn,
            {
                "id": transfer_id,
                "customer_id": ctx.actor.customer_id,
                "from_account_id": source["id"],
                "to_account_id": target["id"],
                "amount_minor": amount_minor,
                "currency": source["currency"],
                "target_amount_minor": conversion.target_amount_minor,
                "target_currency": target["currency"],
                "amount_ron_minor": conversion.amount_ron_minor,
                "spread_bps": conversion.spread_bps,
                "description": description.strip(),
                "channel": channel,
                "correlation_id": ctx.correlation_id,
                "created_at": to_iso(ctx.clock.now()),
            },
        )
        repository.insert_transition(
            ctx.conn, transfer_id, None, "created", ctx.actor.label, "Transfer creat", to_iso(ctx.clock.now())
        )
        audit.record(
            ctx,
            "transfer.created",
            "transfer",
            transfer_id,
            {
                "from": source["id"],
                "to": target["id"],
                "amount_minor": amount_minor,
                "currency": source["currency"],
                "channel": channel,
            },
        )
        stored = repository.get_transfer(ctx.conn, transfer_id)
        assert stored is not None
        evaluation = fraud.evaluate_transfer(ctx, stored)
        repository.update_evaluation(ctx.conn, transfer_id, evaluation["score"], evaluation["decision"])
        _transition(ctx, transfer_id, "evaluated", f"Scor de risc {evaluation['score']}")
        decision = evaluation["decision"]
        if decision == "approve":
            _transition(ctx, transfer_id, "approved", "Aprobat automat")
            _execute(ctx, transfer_id)
            _transition(ctx, transfer_id, "completed", "Fonduri mutate")
        elif decision == "review":
            _transition(ctx, transfer_id, "under_review", "Necesită revizuire")
            fraud.open_case(ctx, transfer_id, evaluation)
        else:
            _transition(ctx, transfer_id, "blocked", "Blocat automat")
            audit.emit_event(
                ctx,
                "transfer.blocked",
                {"transfer_id": transfer_id, "score": evaluation["score"], "reason": "automatic"},
            )
        final = repository.get_transfer(ctx.conn, transfer_id)
    assert final is not None
    return final


# ————————————————————————————————————————

def apply_review_decision(ctx: Ctx, transfer_id: str, action: str, comment: str) -> Row:
    with ctx.transaction():
        transfer = repository.get_transfer(ctx.conn, transfer_id)
        if transfer is None:
            raise not_found("transfer", transfer_id)
        if transfer["state"] != "under_review":
            raise conflict(
                "transfer_not_under_review",
                "Transferul nu este în revizuire.",
                {"state": transfer["state"]},
            )
        if action == "approve":
            _transition(ctx, transfer_id, "approved", comment)
            _execute(ctx, transfer_id)
            _transition(ctx, transfer_id, "completed", "Fonduri mutate după aprobare")
        elif action == "block":
            _transition(ctx, transfer_id, "blocked", comment)
            audit.emit_event(
                ctx, "transfer.blocked", {"transfer_id": transfer_id, "reason": "compliance", "comment": comment}
            )
        final = repository.get_transfer(ctx.conn, transfer_id)
    assert final is not None
    return final


# ————————————————————————————————————————

def cancel_transfer(ctx: Ctx, transfer_id: str) -> Row:
    with ctx.transaction():
        transfer = get_transfer(ctx, transfer_id)
        if ctx.actor.role != "customer":
            raise forbidden("Doar clientul poate anula transferul.")
        _transition(ctx, transfer["id"], "cancelled", "Anulat de client")
        final = repository.get_transfer(ctx.conn, transfer_id)
    assert final is not None
    return final


# ————————————————————————————————————————

def list_transfers(
    ctx: Ctx,
    state: str | None,
    account_id: str | None,
    customer_id: str | None,
    date_from: str | None,
    date_to: str | None,
    cursor: str | None,
    limit: int,
) -> dict[str, Any]:
    size = clamp_limit(limit)
    scoped = ctx.actor.customer_id if ctx.actor.role == "customer" else customer_id
    filters = {
        "customer_id": scoped,
        "state": state,
        "account_id": account_id,
        "date_from": normalize_instant(date_from) if date_from else None,
        "date_to": normalize_instant(date_to) if date_to else None,
    }
    rows = repository.list_transfers(ctx.conn, filters, decode_seq(cursor), size)
    return build_page(rows, size)


# ————————————————————————————————————————

def fact_rows(ctx: Ctx, customer_id: str | None, since: str, exclude_id: str | None) -> list[Row]:
    return repository.fact_rows(ctx.conn, customer_id, since, exclude_id)


# ————————————————————————————————————————

def beneficiary_seen(ctx: Ctx, customer_id: str, to_account_id: str, exclude_id: str | None) -> bool:
    return repository.beneficiary_seen(ctx.conn, customer_id, to_account_id, exclude_id)


# ————————————————————————————————————————

def similar_transfers(ctx: Ctx, transfer_id: str, limit: int = 10) -> list[Row]:
    transfer = repository.get_transfer(ctx.conn, transfer_id)
    if transfer is None:
        raise not_found("transfer", transfer_id)
    amount = int(transfer["amount_ron_minor"])
    low = amount * (100 - SIMILARITY_PERCENT) // 100
    high = amount * (100 + SIMILARITY_PERCENT) // 100
    return repository.similar(
        ctx.conn, transfer["customer_id"], transfer["to_account_id"], low, high, transfer_id, limit
    )


# ————————————————————————————————————————

def account_transfers(ctx: Ctx, account_id: str, limit: int) -> list[Row]:
    size = clamp_limit(limit)
    return repository.list_transfers(ctx.conn, {"account_id": account_id}, None, size)[:size]


# ————————————————————————————————————————

def snapshot(ctx: Ctx, at_iso: str, limit: int) -> list[Row]:
    return repository.snapshot_rows(ctx.conn, at_iso, limit)


# ————————————————————————————————————————

def create_scheduled_payment(
    ctx: Ctx,
    from_account_id: str,
    to_account_id: str,
    amount_minor: int,
    description: str,
    interval_seconds: int,
    first_run_at: str | None,
    ends_at: str | None,
) -> Row:
    if ctx.actor.role != "customer" or not ctx.actor.customer_id:
        raise forbidden("Doar clienții pot programa plăți.")
    if amount_minor <= 0 or interval_seconds < 60:
        raise invalid("invalid_schedule", "Sumă sau interval invalid.")
    with ctx.transaction():
        source = accounts.get_account(ctx, from_account_id)
        target = accounts.get_account(ctx, to_account_id)
        accounts.authorize_account(ctx, source)
        _validate_parties(source, target)
        payment_id = new_id("sch")
        now = ctx.clock.now()
        repository.insert_scheduled(
            ctx.conn,
            {
                "id": payment_id,
                "customer_id": ctx.actor.customer_id,
                "from_account_id": source["id"],
                "to_account_id": target["id"],
                "amount_minor": amount_minor,
                "description": description.strip(),
                "interval_seconds": interval_seconds,
                "next_run_at": normalize_instant(first_run_at) if first_run_at else iso_after(now, interval_seconds),
                "ends_at": normalize_instant(ends_at) if ends_at else None,
                "created_at": to_iso(now),
            },
        )
        audit.record(
            ctx,
            "scheduled.created",
            "scheduled_payment",
            payment_id,
            {"amount_minor": amount_minor, "interval_seconds": interval_seconds},
        )
    created = repository.get_scheduled(ctx.conn, payment_id)
    assert created is not None
    return created


# ————————————————————————————————————————

def list_scheduled_payments(ctx: Ctx) -> list[Row]:
    if not ctx.actor.customer_id:
        return []
    return repository.list_scheduled(ctx.conn, ctx.actor.customer_id)


# ————————————————————————————————————————

def cancel_scheduled_payment(ctx: Ctx, payment_id: str) -> None:
    with ctx.transaction():
        found = repository.get_scheduled(ctx.conn, payment_id)
        if found is None:
            raise not_found("scheduled_payment", payment_id)
        if ctx.actor.role == "customer" and found["customer_id"] != ctx.actor.customer_id:
            raise forbidden()
        repository.deactivate_scheduled(ctx.conn, payment_id)
        audit.record(ctx, "scheduled.cancelled", "scheduled_payment", payment_id, {})


# ————————————————————————————————————————

def run_due_scheduled(ctx: Ctx) -> dict[str, int]:
    now = ctx.clock.now()
    due = repository.due_scheduled(ctx.conn, to_iso(now))
    completed = 0
    failed = 0
    for payment in due:
        runner = ctx.as_actor(Actor(None, "customer", payment["customer_id"], f"scheduler:{payment['id']}"))
        key = f"sched-{payment['id']}-{payment['next_run_at']}"
        payload = {
            "from": payment["from_account_id"],
            "to": payment["to_account_id"],
            "amount_minor": payment["amount_minor"],
        }
        try:
            run_idempotent(
                runner,
                f"sched:{payment['id']}",
                key,
                "transfers.create",
                payload,
                lambda payment=payment, runner=runner: (
                    201,
                    {
                        "transfer_id": create_transfer(
                            runner,
                            payment["from_account_id"],
                            payment["to_account_id"],
                            payment["amount_minor"],
                            payment["description"],
                            "scheduled",
                        )["id"]
                    },
                ),
            )
            status = "completed"
            completed += 1
        except DomainError as error:
            status = f"failed:{error.code}"
            failed += 1
        next_run = iso_after(parse_iso(payment["next_run_at"]), int(payment["interval_seconds"]))
        still_active = payment["ends_at"] is None or next_run <= payment["ends_at"]
        with ctx.transaction():
            repository.update_scheduled(ctx.conn, payment["id"], next_run, still_active, status)
            audit.record(ctx, "scheduled.ran", "scheduled_payment", payment["id"], {"status": status})
    return {"completed": completed, "failed": failed}
