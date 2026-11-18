from __future__ import annotations

import json
from typing import Any

from ledgerguard.audit import service as audit
from ledgerguard.common.clock import iso_before, seconds_between, to_iso
from ledgerguard.common.context import Ctx
from ledgerguard.common.db import Row
from ledgerguard.common.errors import conflict, invalid, not_found
from ledgerguard.common.ids import new_id
from ledgerguard.common.pagination import build_page, clamp_limit, decode_cursor, encode_cursor
from ledgerguard.fraud import repository
from ledgerguard.fraud.defaults import DEFAULT_RULES
from ledgerguard.fraud.engine import (
    EFFECTS,
    CurrentTransfer,
    Facts,
    Rule,
    decide,
    evaluate_rules,
    validate_params,
)
from ledgerguard.fraud.graph import build_graph as build_graph_pure
from ledgerguard.fx import service as fx

HISTORY_DAYS = 90
EDGE_DAYS = 30
DAY_SECONDS = 86_400
CASE_ACTIONS = ("approve", "block", "escalate")


def _to_rule(row: Row) -> Rule:
    return Rule(
        id=row["id"],
        version=int(row["version"]),
        name=row["name"],
        type=row["type"],
        params=json.loads(row["params"]),
        priority=int(row["priority"]),
        effect=row["effect"],
        active=bool(row["active"]),
        valid_from=row["valid_from"],
    )


# ————————————————————————————————————————

def _rule_view(row: Row) -> Row:
    return {**row, "params": json.loads(row["params"]), "active": bool(row["active"])}


# ————————————————————————————————————————

def ensure_default_rules(ctx: Ctx) -> None:
    with ctx.transaction():
        if repository.count_rules(ctx.conn) > 0:
            return
        now = to_iso(ctx.clock.now())
        for rule in DEFAULT_RULES:
            repository.insert_rule(
                ctx.conn,
                rule["id"],
                1,
                rule["name"],
                rule["type"],
                json.dumps(rule["params"], sort_keys=True),
                rule["priority"],
                rule["effect"],
                True,
                now,
                "seed",
            )


# ————————————————————————————————————————

def active_rules(ctx: Ctx, at_iso: str | None = None) -> list[Rule]:
    moment = at_iso or to_iso(ctx.clock.now())
    return [rule for rule in (_to_rule(row) for row in repository.versions_at(ctx.conn, moment)) if rule.active]


# ————————————————————————————————————————

def list_rules(ctx: Ctx, include_history: bool, rule_id: str | None) -> list[Row]:
    if include_history or rule_id:
        return [_rule_view(row) for row in repository.all_versions(ctx.conn, rule_id)]
    return [_rule_view(row) for row in repository.versions_at(ctx.conn, to_iso(ctx.clock.now()))]


# ————————————————————————————————————————

def update_rule(ctx: Ctx, rule_id: str, changes: dict[str, Any]) -> Row:
    with ctx.transaction():
        current = repository.latest_version(ctx.conn, rule_id)
        if current is None:
            raise not_found("rule", rule_id)
        merged_params = {**json.loads(current["params"]), **(changes.get("params") or {})}
        effect = changes.get("effect") or current["effect"]
        if effect not in EFFECTS:
            raise invalid("invalid_effect", "Efect necunoscut.", {"effect": effect})
        problems = validate_params(current["type"], merged_params)
        if problems:
            raise invalid("invalid_rule_params", "Parametri invalizi.", {"problems": problems})
        name = changes.get("name") or current["name"]
        priority = changes["priority"] if changes.get("priority") is not None else current["priority"]
        active = changes["active"] if changes.get("active") is not None else bool(current["active"])
        version = int(current["version"]) + 1
        repository.insert_rule(
            ctx.conn,
            rule_id,
            version,
            name,
            current["type"],
            json.dumps(merged_params, sort_keys=True),
            int(priority),
            effect,
            bool(active),
            to_iso(ctx.clock.now()),
            ctx.actor.label,
        )
        audit.record(
            ctx,
            "fraud.rule_updated",
            "fraud_rule",
            rule_id,
            {
                "from_version": int(current["version"]),
                "to_version": version,
                "before": {
                    "params": json.loads(current["params"]),
                    "effect": current["effect"],
                    "active": bool(current["active"]),
                },
                "after": {"params": merged_params, "effect": effect, "active": bool(active)},
            },
        )
        created = repository.latest_version(ctx.conn, rule_id)
    assert created is not None
    return _rule_view(created)


# ————————————————————————————————————————

def _fx_lookback(rules: list[Rule]) -> int:
    for rule in rules:
        if rule.type == "fx_anomaly":
            return int(rule.params["lookback_seconds"])
    return DAY_SECONDS


# ————————————————————————————————————————

def _fx_facts(ctx: Ctx, currencies: set[str], lookback: int) -> tuple[int, int]:
    worst = 0
    alerts = 0
    for currency in sorted(currencies):
        snapshot = fx.context(ctx, currency, lookback)
        if abs(snapshot["change_bps"]) > abs(worst):
            worst = snapshot["change_bps"]
        alerts += snapshot["alerts_recent"]
    return worst, alerts


# ————————————————————————————————————————

def evaluate_transfer(ctx: Ctx, transfer: Row) -> Row:
    history = ctx.history
    if history is None:
        raise RuntimeError("history port is not configured")
    now = ctx.clock.now()
    transfer_id = transfer["id"]
    customer_id = transfer["customer_id"]
    rules = active_rules(ctx)
    currencies = {transfer["currency"], transfer["target_currency"]}
    fx_change, fx_alerts = _fx_facts(ctx, currencies, _fx_lookback(rules))
    facts = Facts(
        now=now,
        transfer=CurrentTransfer(
            transfer_id,
            customer_id,
            transfer["from_account_id"],
            transfer["to_account_id"],
            int(transfer["amount_ron_minor"]),
            transfer["currency"],
        ),
        customer_history=history.customer_transfers(customer_id, iso_before(now, HISTORY_DAYS * DAY_SECONDS), transfer_id),
        all_edges=history.edges_since(iso_before(now, EDGE_DAYS * DAY_SECONDS), transfer_id),
        account_age_seconds=seconds_between(history.account_created_at(transfer["from_account_id"]), now),
        beneficiary_seen=history.beneficiary_seen(customer_id, transfer["to_account_id"], transfer_id)
        or history.account_owner(transfer["to_account_id"]) == customer_id,
        fx_change_bps=fx_change,
        fx_alerts_recent=fx_alerts,
    )
    results = evaluate_rules(rules, facts)
    thresholds = {"review_score": ctx.settings.fraud_review_score, "block_score": ctx.settings.fraud_block_score}
    score, decision = decide(results, ctx.settings.fraud_review_score, ctx.settings.fraud_block_score)
    evaluation_id = new_id("evl")
    serialized = [item.as_dict() for item in results]
    with ctx.transaction():
        repository.insert_evaluation(
            ctx.conn,
            evaluation_id,
            transfer_id,
            score,
            decision,
            json.dumps(serialized, sort_keys=True),
            json.dumps(thresholds, sort_keys=True),
            ctx.correlation_id,
            to_iso(now),
        )
        audit.record(
            ctx,
            "fraud.evaluated",
            "transfer",
            transfer_id,
            {
                "evaluation_id": evaluation_id,
                "score": score,
                "decision": decision,
                "triggered": [item["rule_id"] for item in serialized if item["triggered"]],
            },
        )
    return {
        "id": evaluation_id,
        "transfer_id": transfer_id,
        "score": score,
        "decision": decision,
        "results": serialized,
        "thresholds": thresholds,
        "created_at": to_iso(now),
    }


# ————————————————————————————————————————

def _evaluation_view(row: Row) -> Row:
    return {**row, "results": json.loads(row["results"]), "thresholds": json.loads(row["thresholds"])}


# ————————————————————————————————————————

def get_evaluation_for_transfer(ctx: Ctx, transfer_id: str) -> Row | None:
    found = repository.evaluation_for_transfer(ctx.conn, transfer_id)
    return _evaluation_view(found) if found else None


# ————————————————————————————————————————

def evaluations_until(ctx: Ctx, at_iso: str, limit: int) -> list[Row]:
    return [_evaluation_view(row) for row in repository.evaluations_until(ctx.conn, at_iso, limit)]


# ————————————————————————————————————————

def open_case(ctx: Ctx, transfer_id: str, evaluation: Row) -> Row:
    case_id = new_id("cas")
    with ctx.transaction():
        repository.insert_case(
            ctx.conn, case_id, transfer_id, evaluation["id"], int(evaluation["score"]), to_iso(ctx.clock.now())
        )
        audit.record(
            ctx,
            "fraud.case_opened",
            "fraud_case",
            case_id,
            {"transfer_id": transfer_id, "score": evaluation["score"]},
        )
        audit.emit_event(
            ctx,
            "transfer.under_review",
            {"case_id": case_id, "transfer_id": transfer_id, "score": evaluation["score"]},
        )
    return get_case(ctx, case_id)


# ————————————————————————————————————————

def get_case(ctx: Ctx, case_id: str) -> Row:
    found = repository.get_case(ctx.conn, case_id)
    if found is None:
        raise not_found("case", case_id)
    evaluation = repository.get_evaluation(ctx.conn, found["evaluation_id"])
    return {
        **found,
        "evaluation": _evaluation_view(evaluation) if evaluation else None,
        "actions": repository.list_actions(ctx.conn, case_id),
    }


# ————————————————————————————————————————

def case_for_transfer(ctx: Ctx, transfer_id: str) -> Row | None:
    found = repository.case_for_transfer(ctx.conn, transfer_id)
    return get_case(ctx, found["id"]) if found else None


# ————————————————————————————————————————

def list_cases(ctx: Ctx, status: str | None, cursor: str | None, limit: int) -> dict[str, Any]:
    size = clamp_limit(limit)
    if status in (None, "", "pending"):
        statuses = ["open", "escalated"]
    elif status in ("open", "escalated", "resolved"):
        statuses = [status]
    else:
        raise invalid("invalid_status", "Stare necunoscută.", {"status": status})
    parts = decode_cursor(cursor)
    after = (int(parts[0]), int(parts[1])) if parts and len(parts) == 2 else None
    rows = repository.list_cases(ctx.conn, statuses, after, size)
    return build_page(rows, size, lambda item: encode_cursor(item["score"], item["seq"]))


# ————————————————————————————————————————

def record_decision(ctx: Ctx, case_id: str, action: str, comment: str) -> Row:
    if action not in CASE_ACTIONS:
        raise invalid("invalid_action", "Acțiune necunoscută.", {"action": action})
    if len(comment.strip()) < 3:
        raise invalid("comment_required", "Comentariul este obligatoriu.")
    with ctx.transaction():
        found = repository.get_case(ctx.conn, case_id)
        if found is None:
            raise not_found("case", case_id)
        if found["status"] == "resolved":
            raise conflict("case_already_resolved", "Cazul este deja rezolvat.")
        now = to_iso(ctx.clock.now())
        repository.insert_action(ctx.conn, case_id, action, comment, ctx.actor.label, now)
        if action == "escalate":
            repository.update_case(ctx.conn, case_id, "escalated", None, None, None, comment)
        else:
            repository.update_case(ctx.conn, case_id, "resolved", action, now, ctx.actor.label, comment)
        audit.record(
            ctx,
            "fraud.case_decision",
            "fraud_case",
            case_id,
            {"action": action, "comment": comment, "transfer_id": found["transfer_id"]},
        )
    return get_case(ctx, case_id)


# ————————————————————————————————————————

def close_case_cancelled(ctx: Ctx, transfer_id: str) -> None:
    with ctx.transaction():
        found = repository.case_for_transfer(ctx.conn, transfer_id)
        if found is None or found["status"] == "resolved":
            return
        repository.update_case(
            ctx.conn, found["id"], "resolved", "cancelled", to_iso(ctx.clock.now()), ctx.actor.label, "Anulat de client"
        )
        audit.record(ctx, "fraud.case_closed", "fraud_case", found["id"], {"reason": "cancelled"})


# ————————————————————————————————————————

def build_graph(ctx: Ctx, days: int = EDGE_DAYS) -> dict[str, Any]:
    history = ctx.history
    if history is None:
        raise RuntimeError("history port is not configured")
    since = iso_before(ctx.clock.now(), days * DAY_SECONDS)
    return build_graph_pure(history.edges_since(since, None))


# ————————————————————————————————————————

def linked_accounts(ctx: Ctx, account_id: str, depth: int = 2) -> list[dict[str, Any]]:
    history = ctx.history
    if history is None:
        raise RuntimeError("history port is not configured")
    edges = history.edges_since(iso_before(ctx.clock.now(), EDGE_DAYS * DAY_SECONDS), None)
    neighbors: dict[str, set[str]] = {}
    for edge in edges:
        neighbors.setdefault(edge.from_account_id, set()).add(edge.to_account_id)
        neighbors.setdefault(edge.to_account_id, set()).add(edge.from_account_id)
    seen = {account_id: 0}
    frontier = [account_id]
    for level in range(1, depth + 1):
        following: list[str] = []
        for node in frontier:
            for neighbor in sorted(neighbors.get(node, set())):
                if neighbor not in seen:
                    seen[neighbor] = level
                    following.append(neighbor)
        frontier = following
    return [
        {"account_id": node, "distance": distance, "owner": history.account_owner(node)}
        for node, distance in sorted(seen.items(), key=lambda item: (item[1], item[0]))
        if node != account_id
    ]
