from __future__ import annotations

import base64
from collections.abc import Callable, Sequence
from typing import Any

from ledgerguard.common.errors import bad_request

MAX_LIMIT = 200


def clamp_limit(limit: int) -> int:
    return max(1, min(limit, MAX_LIMIT))


# ————————————————————————————————————————

def encode_cursor(*parts: int | str) -> str:
    raw = "|".join(str(part) for part in parts).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


# ————————————————————————————————————————

def decode_cursor(cursor: str | None) -> list[str] | None:
    if not cursor:
        return None
    try:
        return base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8").split("|")
    except (ValueError, UnicodeError) as error:
        raise bad_request("invalid_cursor", "Cursor invalid.") from error


# ————————————————————————————————————————

def decode_seq(cursor: str | None) -> int | None:
    parts = decode_cursor(cursor)
    if parts is None:
        return None
    try:
        return int(parts[0])
    except ValueError as error:
        raise bad_request("invalid_cursor", "Cursor invalid.") from error


# ————————————————————————————————————————

def build_page(
    rows: Sequence[dict[str, Any]],
    limit: int,
    cursor_of: Callable[[dict[str, Any]], str] | None = None,
) -> dict[str, Any]:
    has_more = len(rows) > limit
    items = list(rows[:limit])
    next_cursor: str | None = None
    if has_more and items:
        last = items[-1]
        next_cursor = cursor_of(last) if cursor_of else encode_cursor(last["seq"])
    return {"items": items, "next_cursor": next_cursor}
