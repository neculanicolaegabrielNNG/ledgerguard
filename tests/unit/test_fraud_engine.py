from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from ledgerguard.common.clock import to_iso
from ledgerguard.common.ports import TransferFact
from ledgerguard.fraud.defaults import DEFAULT_RULES
from ledgerguard.fraud.engine import (
    CurrentTransfer,
    Facts,
    Rule,
    decide,
    evaluate_rules,
    find_path,
    validate_params,
)

NOW = datetime(2026, 1, 10, 12, 0, tzinfo=UTC)


def rule(rule_id: str, **param_overrides: int) -> Rule:
    data = next(item for item in DEFAULT_RULES if item["id"] == rule_id)
    return Rule(
        id=data["id"],
        version=1,
        name=data["name"],
        type=data["type"],
        params={**data["params"], **param_overrides},
        priority=data["priority"],
        effect=data["effect"],
        active=True,
        valid_from="2026-01-01T00:00:00.000000Z",
    )


# ————————————————————————————————————————

def fact(seconds_ago: int, amount: int, source: str = "a1", target: str = "a2", state: str = "completed") -> TransferFact:
    return TransferFact("t", "c1", source, target, amount, to_iso(NOW - timedelta(seconds=seconds_ago)), state)


# ————————————————————————————————————————

def facts(amount: int = 10_000, **overrides: Any) -> Facts:
    values: dict[str, Any] = {
        "now": NOW,
        "transfer": CurrentTransfer("current", "c1", "a1", "a2", amount, "RON"),
        "customer_history": [],
        "all_edges": [],
        "account_age_seconds": 10**7,
        "beneficiary_seen": True,
        "fx_change_bps": 0,
        "fx_alerts_recent": 0,
    }
    values.update(overrides)
    return Facts(**values)


# ————————————————————————————————————————

def triggered(rule_id: str, scenario: Facts, **param_overrides: int) -> bool:
    return evaluate_rules([rule(rule_id, **param_overrides)], scenario)[0].triggered


# ————————————————————————————————————————

def test_amount_vs_history_triggers_above_multiple_of_average() -> None:
    history = [fact(3_600 * index, 10_000) for index in range(1, 5)]
    assert triggered("R-AMOUNT-HISTORY", facts(400_000, customer_history=history))
    assert not triggered("R-AMOUNT-HISTORY", facts(40_000, customer_history=history))


# ————————————————————————————————————————

def test_amount_vs_history_needs_enough_history() -> None:
    history = [fact(3_600, 10_000)]
    assert not triggered("R-AMOUNT-HISTORY", facts(400_000, customer_history=history))


# ————————————————————————————————————————

def test_velocity_counts_current_transfer() -> None:
    history = [fact(60 * index, 1_000) for index in range(1, 6)]
    assert triggered("R-VELOCITY", facts(customer_history=history))
    assert not triggered("R-VELOCITY", facts(customer_history=history[:4]))


# ————————————————————————————————————————

def test_velocity_ignores_transfers_outside_window() -> None:
    history = [fact(10_000 + index, 1_000) for index in range(10)]
    assert not triggered("R-VELOCITY", facts(customer_history=history))


# ————————————————————————————————————————

def test_structuring_requires_current_transfer_in_band() -> None:
    history = [fact(3_600, 4_500_000), fact(7_200, 4_800_000)]
    assert triggered("R-STRUCTURING", facts(4_600_000, customer_history=history))
    assert not triggered("R-STRUCTURING", facts(1_000_000, customer_history=history))


# ————————————————————————————————————————

def test_new_account_volume_uses_age_and_volume() -> None:
    assert triggered("R-NEW-ACCOUNT", facts(2_500_000, account_age_seconds=3_600))
    assert not triggered("R-NEW-ACCOUNT", facts(2_500_000, account_age_seconds=10**7))
    assert not triggered("R-NEW-ACCOUNT", facts(500_000, account_age_seconds=3_600))


# ————————————————————————————————————————

def test_new_beneficiary_large() -> None:
    assert triggered("R-NEW-BENEFICIARY", facts(2_000_000, beneficiary_seen=False))
    assert not triggered("R-NEW-BENEFICIARY", facts(2_000_000, beneficiary_seen=True))
    assert not triggered("R-NEW-BENEFICIARY", facts(100_000, beneficiary_seen=False))


# ————————————————————————————————————————

def test_circular_flow_detects_closing_transfer() -> None:
    edges = [fact(3_600, 100, "a2", "b"), fact(1_800, 100, "b", "a1")]
    assert triggered("R-CIRCULAR", facts(customer_history=[], all_edges=edges))
    assert not triggered("R-CIRCULAR", facts(all_edges=[fact(3_600, 100, "a2", "b")]))


# ————————————————————————————————————————

def test_circular_flow_respects_depth() -> None:
    edges = [fact(30, 1, "a2", "b"), fact(20, 1, "b", "c"), fact(10, 1, "c", "a1")]
    assert triggered("R-CIRCULAR", facts(all_edges=edges), max_depth=4)
    assert not triggered("R-CIRCULAR", facts(all_edges=edges), max_depth=3)


# ————————————————————————————————————————

def test_behavior_change_compares_recent_to_baseline() -> None:
    baseline = [fact(86_400 * (3 + index), 20_000) for index in range(6)]
    assert triggered("R-BEHAVIOR", facts(900_000, customer_history=baseline))
    assert not triggered("R-BEHAVIOR", facts(30_000, customer_history=baseline))


# ————————————————————————————————————————

def test_fx_anomaly_uses_change_or_alerts() -> None:
    assert triggered("R-FX-ANOMALY", facts(fx_change_bps=-450))
    assert triggered("R-FX-ANOMALY", facts(fx_alerts_recent=1))
    assert not triggered("R-FX-ANOMALY", facts(fx_change_bps=100))


# ————————————————————————————————————————

def test_decide_applies_thresholds_and_effects() -> None:
    low = evaluate_rules([rule("R-NEW-BENEFICIARY")], facts(2_000_000, beneficiary_seen=False))
    assert decide(low, 50, 90) == (30, "approve")
    review = evaluate_rules([rule("R-CIRCULAR")], facts(all_edges=[fact(1, 1, "a2", "a1")]))
    assert decide(review, 50, 90) == (70, "review")
    combined = evaluate_rules(
        [rule("R-NEW-ACCOUNT"), rule("R-NEW-BENEFICIARY"), rule("R-CIRCULAR")],
        facts(2_500_000, account_age_seconds=10, beneficiary_seen=False, all_edges=[fact(1, 1, "a2", "a1")]),
    )
    assert decide(combined, 50, 90) == (100, "block")


# ————————————————————————————————————————

def test_block_effect_forces_block_regardless_of_score() -> None:
    blocking = Rule("R-X", 1, "x", "velocity", {"score": 5, "window_seconds": 600, "max_count": 0}, 1, "block", True, "v")
    results = evaluate_rules([blocking], facts())
    assert decide(results, 50, 90) == (5, "block")


# ————————————————————————————————————————

def test_find_path_limits_hops() -> None:
    adjacency = {"a": {"b"}, "b": {"c"}, "c": {"d"}}
    assert find_path(adjacency, "a", "d", 3) == ["a", "b", "c", "d"]
    assert find_path(adjacency, "a", "d", 2) is None
    assert find_path(adjacency, "d", "a", 5) is None


# ————————————————————————————————————————

def test_validate_params_rejects_missing_and_negative_values() -> None:
    assert validate_params("velocity", {"score": 1, "window_seconds": 60, "max_count": 3}) == []
    assert validate_params("velocity", {"score": 1, "window_seconds": -1, "max_count": 3})
    assert validate_params("velocity", {"score": 1})
    assert validate_params("unknown_type", {})


# ————————————————————————————————————————

@pytest.mark.parametrize("rule_data", DEFAULT_RULES)
def test_every_default_rule_has_valid_params(rule_data: dict[str, Any]) -> None:
    assert validate_params(rule_data["type"], rule_data["params"]) == []
