from __future__ import annotations

from ledgerguard.common.errors import conflict

TRANSITIONS: dict[str, frozenset[str]] = {
    "created": frozenset({"evaluated", "cancelled"}),
    "evaluated": frozenset({"approved", "under_review", "blocked"}),
    "approved": frozenset({"completed", "cancelled"}),
    "under_review": frozenset({"approved", "blocked", "cancelled"}),
    "blocked": frozenset({"cancelled"}),
    "completed": frozenset(),
    "cancelled": frozenset(),
}

STATES: tuple[str, ...] = tuple(TRANSITIONS)


def can_transition(current: str, target: str) -> bool:
    return target in TRANSITIONS.get(current, frozenset())


# ————————————————————————————————————————

def assert_transition(current: str, target: str) -> None:
    if not can_transition(current, target):
        raise conflict(
            "invalid_transition",
            f"Tranziția {current} -> {target} nu este permisă.",
            {"from": current, "to": target},
        )
