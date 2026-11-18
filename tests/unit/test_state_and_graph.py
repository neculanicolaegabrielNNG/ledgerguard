from __future__ import annotations

import pytest

from ledgerguard.common.errors import DomainError
from ledgerguard.common.ports import TransferFact
from ledgerguard.fraud.graph import build_graph
from ledgerguard.transfers.state_machine import STATES, TRANSITIONS, assert_transition, can_transition


def edge(source: str, target: str, state: str = "completed") -> TransferFact:
    return TransferFact("t", "c", source, target, 1_000, "2026-01-01T00:00:00.000000Z", state)


# ————————————————————————————————————————

def test_every_state_is_declared() -> None:
    assert set(STATES) == {"created", "evaluated", "approved", "under_review", "blocked", "completed", "cancelled"}


# ————————————————————————————————————————

@pytest.mark.parametrize(
    ("current", "target"),
    [(state, target) for state, targets in TRANSITIONS.items() for target in targets],
)
def test_declared_transitions_are_allowed(current: str, target: str) -> None:
    assert can_transition(current, target)
    assert_transition(current, target)


# ————————————————————————————————————————

@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("created", "completed"),
        ("completed", "cancelled"),
        ("blocked", "completed"),
        ("cancelled", "approved"),
        ("evaluated", "completed"),
    ],
)
def test_undeclared_transitions_are_rejected(current: str, target: str) -> None:
    assert not can_transition(current, target)
    with pytest.raises(DomainError) as error:
        assert_transition(current, target)
    assert error.value.code == "invalid_transition"


# ————————————————————————————————————————

def test_graph_marks_cycles_as_suspicious_clusters() -> None:
    graph = build_graph([edge("a", "b"), edge("b", "c"), edge("c", "a"), edge("x", "y")])
    suspicious = {node["id"] for node in graph["nodes"] if node["suspicious"]}
    assert suspicious == {"a", "b", "c"}
    assert graph["clusters"] == [["a", "b", "c"]]


# ————————————————————————————————————————

def test_graph_marks_flagged_transfers() -> None:
    graph = build_graph([edge("a", "b", "under_review"), edge("c", "d")])
    suspicious = {node["id"] for node in graph["nodes"] if node["suspicious"]}
    assert suspicious == {"a", "b"}
    flagged = [item for item in graph["edges"] if item["flagged"]]
    assert len(flagged) == 1


# ————————————————————————————————————————

def test_graph_aggregates_repeated_edges() -> None:
    graph = build_graph([edge("a", "b"), edge("a", "b")])
    assert graph["edges"][0]["count"] == 2
    assert graph["edges"][0]["amount_ron_minor"] == 2_000
