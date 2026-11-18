from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from typing import Protocol

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


class Clock(Protocol):
    def now(self) -> datetime: ...


# ————————————————————————————————————————

class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


# ————————————————————————————————————————

class FixedClock:
    def __init__(self, start: datetime) -> None:
        self._current = start.astimezone(UTC)
        self._lock = threading.Lock()

    # ————————————————————————————————————————

    def now(self) -> datetime:
        with self._lock:
            return self._current

    # ————————————————————————————————————————

    def advance(self, seconds: int) -> datetime:
        with self._lock:
            self._current = self._current + timedelta(seconds=seconds)
            return self._current

    # ————————————————————————————————————————

    def set(self, value: datetime) -> None:
        with self._lock:
            self._current = value.astimezone(UTC)


# ————————————————————————————————————————

def to_iso(value: datetime) -> str:
    return value.astimezone(UTC).strftime(ISO_FORMAT)


# ————————————————————————————————————————

def parse_iso(text: str) -> datetime:
    return datetime.strptime(text, ISO_FORMAT).replace(tzinfo=UTC)


# ————————————————————————————————————————

def iso_after(value: datetime, seconds: int) -> str:
    return to_iso(value + timedelta(seconds=seconds))


# ————————————————————————————————————————

def iso_before(value: datetime, seconds: int) -> str:
    return to_iso(value - timedelta(seconds=seconds))


# ————————————————————————————————————————

def seconds_between(earlier_iso: str, later: datetime) -> int:
    return int((later - parse_iso(earlier_iso)).total_seconds())


# ————————————————————————————————————————

def normalize_instant(text: str) -> str:
    cleaned = text.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(cleaned)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return to_iso(parsed)
