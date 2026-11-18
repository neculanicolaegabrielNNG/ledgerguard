from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from pathlib import Path
from typing import Any

Row = dict[str, Any]


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=20, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=20000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


# ————————————————————————————————————————

def fetch_all(conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> list[Row]:
    return [dict(item) for item in conn.execute(sql, tuple(params)).fetchall()]


# ————————————————————————————————————————

def fetch_one(conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> Row | None:
    found = conn.execute(sql, tuple(params)).fetchone()
    return dict(found) if found is not None else None


# ————————————————————————————————————————

def fetch_value(conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> Any:
    found = conn.execute(sql, tuple(params)).fetchone()
    return found[0] if found is not None else None
