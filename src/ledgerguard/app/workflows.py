from __future__ import annotations

from typing import Any

from ledgerguard.accounts import service as accounts
from ledgerguard.agents import service as agents
from ledgerguard.common.clock import normalize_instant
from ledgerguard.common.context import Ctx
from ledgerguard.common.errors import invalid
from ledgerguard.fraud import service as fraud
from ledgerguard.fx import service as fx
from ledgerguard.ledger import service as ledger
from ledgerguard.ledger.service import Leg
from ledgerguard.transfers import service as transfers

TIME_TRAVEL_TRANSFER_LIMIT = 200


def deposit(ctx: Ctx, account_id: str, amount_minor: int, description: str) -> dict[str, Any]:
    with ctx.transaction():
        account = accounts.get_account(ctx, account_id)
        if account["kind"] != "customer":
            raise invalid("account_not_depositable", "Depunerile sunt permise doar în conturi de client.")
        currency = account["currency"]
        rate = fx.rate_for(ctx, currency)
        cash = accounts.system_account(ctx, accounts.CASH_KEY, currency)
        transaction_id = ledger.post_transaction(
            ctx,
            "deposit",
            [Leg(cash["id"], currency, -amount_minor, rate), Leg(account_id, currency, amount_minor, rate)],
            description,
        )
        balance = ledger.balance(ctx, account_id)
    return {
        "transaction_id": transaction_id,
        "account_id": account_id,
        "amount_minor": amount_minor,
        "currency": currency,
        "balance_minor": balance,
    }


# ————————————————————————————————————————

def transfer_detail(ctx: Ctx, transfer_id: str) -> dict[str, Any]:
    transfer = transfers.get_transfer(ctx, transfer_id)
    detail: dict[str, Any] = {**transfer, "transitions": transfers.transitions_of(ctx, transfer_id)}
    if ctx.actor.role == "customer":
        detail["risk_score"] = None
        detail["decision"] = None
        detail["evaluation"] = None
        detail["case_id"] = None
        return detail
    case = fraud.case_for_transfer(ctx, transfer_id)
    detail["evaluation"] = fraud.get_evaluation_for_transfer(ctx, transfer_id)
    detail["case_id"] = case["id"] if case else None
    return detail


# ————————————————————————————————————————

def create_transfer_detail(
    ctx: Ctx,
    from_account_id: str,
    to_account_id: str,
    amount_minor: int,
    description: str,
    channel: str = "api",
) -> dict[str, Any]:
    with ctx.transaction():
        created = transfers.create_transfer(ctx, from_account_id, to_account_id, amount_minor, description, channel)
        return transfer_detail(ctx, created["id"])


# ————————————————————————————————————————

def cancel_transfer(ctx: Ctx, transfer_id: str) -> dict[str, Any]:
    with ctx.transaction():
        transfers.cancel_transfer(ctx, transfer_id)
        fraud.close_case_cancelled(ctx, transfer_id)
        return transfer_detail(ctx, transfer_id)


# ————————————————————————————————————————

def confirm_assistant_action(ctx: Ctx, action_id: str) -> dict[str, Any]:
    with ctx.transaction():
        payload = agents.claim_action(ctx, action_id)
        detail = create_transfer_detail(
            ctx,
            payload["from_account_id"],
            payload["to_account_id"],
            payload["amount_minor"],
            payload["description"],
            "assistant",
        )
    return {"action_id": action_id, "transfer": detail}


# ————————————————————————————————————————

def case_detail(ctx: Ctx, case_id: str) -> dict[str, Any]:
    case = fraud.get_case(ctx, case_id)
    return {
        **case,
        "transfer": transfer_detail(ctx, case["transfer_id"]),
        "agent_report": agents.latest_report(ctx, case_id),
    }


# ————————————————————————————————————————

def decide_case(ctx: Ctx, case_id: str, action: str, comment: str) -> dict[str, Any]:
    with ctx.transaction():
        case = fraud.record_decision(ctx, case_id, action, comment)
        transfers.apply_review_decision(ctx, case["transfer_id"], action, comment)
    return case_detail(ctx, case_id)


# ————————————————————————————————————————

def time_travel(ctx: Ctx, at_text: str) -> dict[str, Any]:
    at_iso = normalize_instant(at_text)
    balances = [
        {
            "account_id": account["id"],
            "customer_id": account["customer_id"],
            "currency": account["currency"],
            "kind": account["kind"],
            "balance_minor": ledger.balance(ctx, account["id"], at_iso),
        }
        for account in accounts.all_accounts(ctx)
        if account["created_at"] <= at_iso
    ]
    evaluations = {item["transfer_id"]: item for item in fraud.evaluations_until(ctx, at_iso, 1000)}
    decisions = []
    for row in transfers.snapshot(ctx, at_iso, TIME_TRAVEL_TRANSFER_LIMIT):
        evaluation = evaluations.get(row["id"])
        decisions.append(
            {
                "transfer_id": row["id"],
                "state_at": row["state_at"] or "created",
                "amount_minor": row["amount_minor"],
                "currency": row["currency"],
                "amount_ron_minor": row["amount_ron_minor"],
                "created_at": row["created_at"],
                "score": evaluation["score"] if evaluation else None,
                "decision": evaluation["decision"] if evaluation else None,
                "triggered": [item["rule_id"] for item in evaluation["results"] if item["triggered"]]
                if evaluation
                else [],
            }
        )
    rules = [
        {
            "id": rule.id,
            "version": rule.version,
            "type": rule.type,
            "effect": rule.effect,
            "priority": rule.priority,
            "params": rule.params,
        }
        for rule in fraud.active_rules(ctx, at_iso)
    ]
    return {
        "at": at_iso,
        "balances": balances,
        "rules": rules,
        "decisions": decisions,
        "fx_rates": fx.rates_at(ctx, at_iso),
    }
