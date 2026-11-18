from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from ledgerguard.common.clock import parse_iso
from ledgerguard.common.ports import TransferFact

EFFECTS = ("score_add", "review", "block")

REQUIRED_PARAMS: dict[str, tuple[str, ...]] = {
    "amount_vs_history": ("score", "min_history_count", "multiplier", "floor_ron_minor"),
    "velocity": ("score", "window_seconds", "max_count"),
    "structuring": ("score", "threshold_ron_minor", "band_pct", "window_seconds", "min_count"),
    "new_account_volume": ("score", "max_age_seconds", "volume_ron_minor", "window_seconds"),
    "new_beneficiary_large": ("score", "amount_ron_minor"),
    "circular_flow": ("score", "max_depth", "window_seconds"),
    "behavior_change": (
        "score",
        "min_history_count",
        "ratio",
        "recent_seconds",
        "baseline_seconds",
        "floor_ron_minor",
    ),
    "fx_anomaly": ("score", "max_change_bps", "lookback_seconds", "alerts_trigger"),
}


@dataclass(frozen=True)
class Rule:
    id: str
    version: int
    name: str
    type: str
    params: dict[str, Any]
    priority: int
    effect: str
    active: bool
    valid_from: str


# ————————————————————————————————————————

@dataclass(frozen=True)
class CurrentTransfer:
    transfer_id: str
    customer_id: str
    from_account_id: str
    to_account_id: str
    amount_ron_minor: int
    currency: str


# ————————————————————————————————————————

@dataclass(frozen=True)
class Facts:
    now: datetime
    transfer: CurrentTransfer
    customer_history: list[TransferFact]
    all_edges: list[TransferFact]
    account_age_seconds: int
    beneficiary_seen: bool
    fx_change_bps: int
    fx_alerts_recent: int


# ————————————————————————————————————————

@dataclass(frozen=True)
class RuleResult:
    rule_id: str
    rule_version: int
    rule_name: str
    type: str
    effect: str
    triggered: bool
    score: int
    measured: dict[str, Any]
    threshold: dict[str, Any]

    # ————————————————————————————————————————

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "rule_version": self.rule_version,
            "rule_name": self.rule_name,
            "type": self.type,
            "effect": self.effect,
            "triggered": self.triggered,
            "score": self.score,
            "measured": self.measured,
            "threshold": self.threshold,
        }


# ————————————————————————————————————————

Outcome = tuple[bool, dict[str, Any], dict[str, Any]]


def _within(fact: TransferFact, now: datetime, seconds: int) -> bool:
    return parse_iso(fact.created_at) >= now - timedelta(seconds=seconds)


# ————————————————————————————————————————

def find_path(adjacency: dict[str, set[str]], start: str, goal: str, max_hops: int) -> list[str] | None:
    if max_hops < 1:
        return None
    queue: deque[list[str]] = deque([[start]])
    visited = {start}
    while queue:
        path = queue.popleft()
        if path[-1] == goal and len(path) > 1:
            return path
        if len(path) - 1 >= max_hops:
            continue
        for neighbor in sorted(adjacency.get(path[-1], set())):
            if neighbor == goal:
                return [*path, neighbor]
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append([*path, neighbor])
    return None


# ————————————————————————————————————————

def _amount_vs_history(rule: Rule, facts: Facts) -> Outcome:
    params = rule.params
    completed = [item for item in facts.customer_history if item.state == "completed"]
    count = len(completed)
    average = sum(item.amount_ron_minor for item in completed) // count if count else 0
    amount = facts.transfer.amount_ron_minor
    triggered = (
        count >= params["min_history_count"]
        and amount >= params["floor_ron_minor"]
        and amount > params["multiplier"] * average
    )
    measured = {
        "amount_ron_minor": amount,
        "average_ron_minor": average,
        "history_count": count,
        "ratio_x100": amount * 100 // average if average else 0,
    }
    threshold = {
        "multiplier": params["multiplier"],
        "floor_ron_minor": params["floor_ron_minor"],
        "min_history_count": params["min_history_count"],
    }
    return triggered, measured, threshold


# ————————————————————————————————————————

def _velocity(rule: Rule, facts: Facts) -> Outcome:
    params = rule.params
    recent = [item for item in facts.customer_history if _within(item, facts.now, params["window_seconds"])]
    count = len(recent) + 1
    return (
        count > params["max_count"],
        {"count_in_window": count},
        {"max_count": params["max_count"], "window_seconds": params["window_seconds"]},
    )


# ————————————————————————————————————————

def _structuring(rule: Rule, facts: Facts) -> Outcome:
    params = rule.params
    limit = params["threshold_ron_minor"]
    lower = limit * (100 - params["band_pct"]) // 100
    amount = facts.transfer.amount_ron_minor
    current_in_band = lower <= amount < limit
    banded = [
        item
        for item in facts.customer_history
        if lower <= item.amount_ron_minor < limit and _within(item, facts.now, params["window_seconds"])
    ]
    count = len(banded) + (1 if current_in_band else 0)
    total = sum(item.amount_ron_minor for item in banded) + (amount if current_in_band else 0)
    return (
        current_in_band and count >= params["min_count"],
        {"count_in_band": count, "total_ron_minor": total, "band_lower_ron_minor": lower},
        {"threshold_ron_minor": limit, "min_count": params["min_count"], "window_seconds": params["window_seconds"]},
    )


# ————————————————————————————————————————

def _new_account_volume(rule: Rule, facts: Facts) -> Outcome:
    params = rule.params
    source = facts.transfer.from_account_id
    sent = facts.transfer.amount_ron_minor + sum(
        item.amount_ron_minor
        for item in facts.customer_history
        if item.from_account_id == source and _within(item, facts.now, params["window_seconds"])
    )
    age = facts.account_age_seconds
    return (
        age < params["max_age_seconds"] and sent > params["volume_ron_minor"],
        {"account_age_seconds": age, "volume_ron_minor": sent},
        {"max_age_seconds": params["max_age_seconds"], "volume_ron_minor": params["volume_ron_minor"]},
    )


# ————————————————————————————————————————

def _new_beneficiary_large(rule: Rule, facts: Facts) -> Outcome:
    params = rule.params
    amount = facts.transfer.amount_ron_minor
    return (
        (not facts.beneficiary_seen) and amount >= params["amount_ron_minor"],
        {"amount_ron_minor": amount, "beneficiary_seen": facts.beneficiary_seen},
        {"amount_ron_minor": params["amount_ron_minor"]},
    )


# ————————————————————————————————————————

def _circular_flow(rule: Rule, facts: Facts) -> Outcome:
    params = rule.params
    adjacency: dict[str, set[str]] = {}
    for edge in facts.all_edges:
        if _within(edge, facts.now, params["window_seconds"]):
            adjacency.setdefault(edge.from_account_id, set()).add(edge.to_account_id)
    source = facts.transfer.from_account_id
    path = find_path(adjacency, facts.transfer.to_account_id, source, int(params["max_depth"]) - 1)
    cycle = [source, *path] if path else []
    return (
        path is not None,
        {"cycle": cycle, "cycle_length": len(cycle) - 1 if cycle else 0},
        {"max_depth": params["max_depth"], "window_seconds": params["window_seconds"]},
    )


# ————————————————————————————————————————

def _behavior_change(rule: Rule, facts: Facts) -> Outcome:
    params = rule.params
    amount = facts.transfer.amount_ron_minor
    recent_cut = facts.now - timedelta(seconds=params["recent_seconds"])
    base_cut = facts.now - timedelta(seconds=params["baseline_seconds"])
    recent = sum(
        item.amount_ron_minor for item in facts.customer_history if parse_iso(item.created_at) >= recent_cut
    ) + amount
    baseline = [item for item in facts.customer_history if base_cut <= parse_iso(item.created_at) < recent_cut]
    days = max(1, (params["baseline_seconds"] - params["recent_seconds"]) // 86_400)
    daily = sum(item.amount_ron_minor for item in baseline) // days
    triggered = (
        len(baseline) >= params["min_history_count"]
        and recent >= params["floor_ron_minor"]
        and recent > params["ratio"] * max(daily, 1)
    )
    return (
        triggered,
        {"recent_ron_minor": recent, "baseline_daily_ron_minor": daily, "baseline_count": len(baseline)},
        {"ratio": params["ratio"], "floor_ron_minor": params["floor_ron_minor"]},
    )


# ————————————————————————————————————————

def _fx_anomaly(rule: Rule, facts: Facts) -> Outcome:
    params = rule.params
    change = abs(facts.fx_change_bps)
    return (
        change > params["max_change_bps"] or facts.fx_alerts_recent >= params["alerts_trigger"],
        {"change_bps": facts.fx_change_bps, "alerts_recent": facts.fx_alerts_recent},
        {"max_change_bps": params["max_change_bps"], "alerts_trigger": params["alerts_trigger"]},
    )


# ————————————————————————————————————————

EVALUATORS: dict[str, Callable[[Rule, Facts], Outcome]] = {
    "amount_vs_history": _amount_vs_history,
    "velocity": _velocity,
    "structuring": _structuring,
    "new_account_volume": _new_account_volume,
    "new_beneficiary_large": _new_beneficiary_large,
    "circular_flow": _circular_flow,
    "behavior_change": _behavior_change,
    "fx_anomaly": _fx_anomaly,
}


# ————————————————————————————————————————

def evaluate_rules(rules: list[Rule], facts: Facts) -> list[RuleResult]:
    results: list[RuleResult] = []
    for rule in sorted(rules, key=lambda item: (item.priority, item.id)):
        evaluator = EVALUATORS.get(rule.type)
        if evaluator is None:
            results.append(
                RuleResult(rule.id, rule.version, rule.name, rule.type, rule.effect, False, 0, {"error": "unknown_type"}, {})
            )
            continue
        triggered, measured, threshold = evaluator(rule, facts)
        score = int(rule.params.get("score", 0)) if triggered else 0
        results.append(
            RuleResult(rule.id, rule.version, rule.name, rule.type, rule.effect, triggered, score, measured, threshold)
        )
    return results


# ————————————————————————————————————————

def decide(results: list[RuleResult], review_score: int, block_score: int) -> tuple[int, str]:
    hits = [item for item in results if item.triggered]
    score = min(100, sum(item.score for item in hits))
    if any(item.effect == "block" for item in hits) or score >= block_score:
        return score, "block"
    if any(item.effect == "review" for item in hits) or score >= review_score:
        return score, "review"
    return score, "approve"


# ————————————————————————————————————————

def validate_params(rule_type: str, params: dict[str, Any]) -> list[str]:
    required = REQUIRED_PARAMS.get(rule_type)
    if required is None:
        return [f"tip necunoscut: {rule_type}"]
    problems: list[str] = []
    for key in required:
        value = params.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            problems.append(f"parametrul '{key}' trebuie să fie întreg >= 0")
    return problems
