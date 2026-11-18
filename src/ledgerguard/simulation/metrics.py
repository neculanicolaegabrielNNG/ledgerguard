from __future__ import annotations

from dataclasses import dataclass
from typing import Any

FLAGGED_STATES = ("under_review", "blocked")


@dataclass(frozen=True)
class StepOutcome:
    index: int
    label: str
    malicious: bool
    offset_seconds: int
    state: str


# ————————————————————————————————————————

def _percent(part: int, whole: int) -> int:
    return part * 100 // whole if whole else 0


# ————————————————————————————————————————

def compute_metrics(outcomes: list[StepOutcome]) -> dict[str, Any]:
    malicious = [item for item in outcomes if item.malicious]
    benign = [item for item in outcomes if not item.malicious]
    caught = [item for item in malicious if item.state in FLAGGED_STATES]
    false_alarms = [item for item in benign if item.state in FLAGGED_STATES]
    errors = [item for item in outcomes if item.state.startswith("error")]
    steps_to_detection: int | None = None
    seconds_to_detection: int | None = None
    if caught and malicious:
        first = caught[0]
        steps_to_detection = sum(1 for item in malicious if item.index <= first.index)
        seconds_to_detection = first.offset_seconds - malicious[0].offset_seconds
    return {
        "malicious_total": len(malicious),
        "malicious_caught": len(caught),
        "malicious_missed": len(malicious) - len(caught),
        "benign_total": len(benign),
        "false_alarms": len(false_alarms),
        "detection_rate_pct": _percent(len(caught), len(malicious)),
        "false_alarm_rate_pct": _percent(len(false_alarms), len(benign)),
        "steps_to_detection": steps_to_detection,
        "seconds_to_detection": seconds_to_detection,
        "errors": len(errors),
    }
