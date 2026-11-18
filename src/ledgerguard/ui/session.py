from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Session:
    token: str
    role: str
    email: str
    customer_id: str | None


# ————————————————————————————————————————

STATE_LABELS = {
    "created": "Creat",
    "evaluated": "Evaluat",
    "approved": "Aprobat",
    "under_review": "În revizuire",
    "blocked": "Blocat",
    "completed": "Finalizat",
    "cancelled": "Anulat",
}


# ————————————————————————————————————————

def risk_color(score: int | None) -> str:
    if score is None:
        return "grey"
    if score >= 90:
        return "red"
    if score >= 50:
        return "orange"
    return "green"


# ————————————————————————————————————————

def risk_label(score: int | None) -> str:
    if score is None:
        return "necunoscut"
    if score >= 90:
        return "ridicat"
    if score >= 50:
        return "mediu"
    return "scăzut"
