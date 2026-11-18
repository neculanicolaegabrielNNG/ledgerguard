from __future__ import annotations

import json
from typing import Any

from ledgerguard.agents import repository
from ledgerguard.agents.llm import LlmClient, LlmUnavailable, OfflineAnalyst
from ledgerguard.agents.models import AnalystReport
from ledgerguard.agents.tools import ANALYST_TOOLS, ASSISTANT_TOOLS, ToolBox
from ledgerguard.audit import service as audit
from ledgerguard.common.clock import to_iso
from ledgerguard.common.context import Ctx
from ledgerguard.common.db import Row
from ledgerguard.common.errors import conflict, forbidden, not_found
from ledgerguard.common.ids import new_id
from ledgerguard.fraud import service as fraud
from ledgerguard.transfers import service as transfers


def _report_view(row: Row) -> Row:
    return {
        "id": row["id"],
        "case_id": row["case_id"],
        "transfer_id": row["transfer_id"],
        "created_at": row["created_at"],
        **json.loads(row["report"]),
    }


# ————————————————————————————————————————

def latest_report(ctx: Ctx, case_id: str) -> Row | None:
    found = repository.latest_report(ctx.conn, case_id)
    return _report_view(found) if found else None


# ————————————————————————————————————————

def analyze_case(ctx: Ctx, llm: LlmClient, case_id: str) -> Row:
    case = fraud.get_case(ctx, case_id)
    transfer = transfers.get_transfer(ctx, case["transfer_id"])
    case_input = {
        "case_id": case_id,
        "transfer_id": transfer["id"],
        "score": case["score"],
        "from_account_id": transfer["from_account_id"],
        "to_account_id": transfer["to_account_id"],
        "currency": transfer["currency"],
        "amount_ron_minor": transfer["amount_ron_minor"],
        "description": transfer["description"],
    }
    report: AnalystReport
    try:
        report = llm.investigate(case_input, ToolBox(ctx, ANALYST_TOOLS))
    except LlmUnavailable:
        report = OfflineAnalyst().investigate(case_input, ToolBox(ctx, ANALYST_TOOLS))
        report = report.model_copy(update={"engine": "offline-fallback"})
    report_id = new_id("rep")
    with ctx.transaction():
        repository.insert_report(
            ctx.conn,
            report_id,
            case_id,
            transfer["id"],
            report.engine,
            report.recommendation,
            report.confidence,
            report.model_dump_json(),
            ctx.correlation_id,
            to_iso(ctx.clock.now()),
        )
        audit.record(
            ctx,
            "agent.report",
            "fraud_case",
            case_id,
            {
                "report_id": report_id,
                "engine": report.engine,
                "recommendation": report.recommendation,
                "confidence": report.confidence,
                "flags": report.flags,
            },
        )
    stored = latest_report(ctx, case_id)
    assert stored is not None
    return stored


# ————————————————————————————————————————

def analyze_pending(ctx: Ctx, llm: LlmClient, limit: int = 10) -> int:
    analyzed = 0
    for case in fraud.list_cases(ctx, "pending", None, 50)["items"]:
        if analyzed >= limit:
            break
        if repository.latest_report(ctx.conn, case["id"]) is None:
            analyze_case(ctx, llm, case["id"])
            analyzed += 1
    return analyzed


# ————————————————————————————————————————

def assistant_chat(ctx: Ctx, llm: LlmClient, message: str) -> dict[str, Any]:
    if ctx.actor.role != "customer":
        raise forbidden("Asistentul este disponibil doar clienților.")
    try:
        reply = llm.interpret(message, ToolBox(ctx, ASSISTANT_TOOLS))
    except LlmUnavailable:
        reply = OfflineAnalyst().interpret(message, ToolBox(ctx, ASSISTANT_TOOLS))
    with ctx.transaction():
        audit.record(
            ctx,
            "assistant.chat",
            "customer",
            str(ctx.actor.customer_id),
            {
                "message": message[:500],
                "intent": reply.intent,
                "action_id": reply.proposal["action_id"] if reply.proposal else None,
            },
        )
    return reply.model_dump()


# ————————————————————————————————————————

def _owned_action(ctx: Ctx, action_id: str) -> Row:
    action = repository.get_action(ctx.conn, action_id)
    if action is None:
        raise not_found("assistant_action", action_id)
    if action["customer_id"] != ctx.actor.customer_id:
        raise forbidden()
    return action


# ————————————————————————————————————————

def claim_action(ctx: Ctx, action_id: str) -> dict[str, Any]:
    with ctx.transaction():
        action = _owned_action(ctx, action_id)
        now = to_iso(ctx.clock.now())
        if action["status"] != "pending":
            raise conflict("action_not_pending", "Acțiunea nu mai este în așteptare.", {"status": action["status"]})
        if action["expires_at"] < now:
            repository.update_action(ctx.conn, action_id, "expired", now)
            raise conflict("action_expired", "Acțiunea a expirat.")
        repository.update_action(ctx.conn, action_id, "confirmed", now)
        audit.record(ctx, "assistant.confirmed", "assistant_action", action_id, {})
        payload: dict[str, Any] = json.loads(action["payload"])
    return payload


# ————————————————————————————————————————

def reject_action(ctx: Ctx, action_id: str) -> dict[str, Any]:
    with ctx.transaction():
        action = _owned_action(ctx, action_id)
        if action["status"] != "pending":
            raise conflict("action_not_pending", "Acțiunea nu mai este în așteptare.", {"status": action["status"]})
        repository.update_action(ctx.conn, action_id, "rejected", to_iso(ctx.clock.now()))
        audit.record(ctx, "assistant.rejected", "assistant_action", action_id, {})
    return {"action_id": action_id, "status": "rejected"}
