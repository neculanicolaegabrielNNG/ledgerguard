from __future__ import annotations

import sqlite3
from typing import Any

from ledgerguard.common.db import Row, fetch_all, fetch_one, fetch_value


def insert_rate(
    conn: sqlite3.Connection, rate_id: str, currency: str, rate_e8: int, valid_from: str, source: str
) -> None:
    conn.execute(
        "INSERT INTO fx_rates (id, base, quote, rate_e8, valid_from, source) VALUES (?, ?, 'RON', ?, ?, ?)",
        (rate_id, currency, rate_e8, valid_from, source),
    )


# ————————————————————————————————————————

def latest_rate(conn: sqlite3.Connection, currency: str, at: str) -> Row | None:
    return fetch_one(
        conn,
        "SELECT * FROM fx_rates WHERE base = ? AND valid_from <= ? ORDER BY valid_from DESC, seq DESC LIMIT 1",
        (currency, at),
    )


# ————————————————————————————————————————

def earliest_rate(conn: sqlite3.Connection, currency: str) -> Row | None:
    return fetch_one(
        conn, "SELECT * FROM fx_rates WHERE base = ? ORDER BY valid_from ASC, seq ASC LIMIT 1", (currency,)
    )


# ————————————————————————————————————————

def count_rates(conn: sqlite3.Connection) -> int:
    return int(fetch_value(conn, "SELECT COUNT(*) FROM fx_rates") or 0)


# ————————————————————————————————————————

def list_rates(conn: sqlite3.Connection, currency: str | None, after_seq: int | None, limit: int) -> list[Row]:
    clauses: list[str] = []
    params: list[Any] = []
    if currency:
        clauses.append("base = ?")
        params.append(currency)
    if after_seq is not None:
        clauses.append("seq < ?")
        params.append(after_seq)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit + 1)
    return fetch_all(conn, f"SELECT * FROM fx_rates {where} ORDER BY seq DESC LIMIT ?", params)


# ————————————————————————————————————————

def insert_alert(
    conn: sqlite3.Connection,
    alert_id: str,
    currency: str,
    previous_rate_e8: int,
    proposed_rate_e8: int,
    change: int,
    source: str,
    created_at: str,
) -> None:
    conn.execute(
        "INSERT INTO fx_alerts (id, currency, previous_rate_e8, proposed_rate_e8, change_bps, source, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (alert_id, currency, previous_rate_e8, proposed_rate_e8, change, source, created_at),
    )


# ————————————————————————————————————————

def list_alerts(conn: sqlite3.Connection, currency: str | None, after_seq: int | None, limit: int) -> list[Row]:
    clauses: list[str] = []
    params: list[Any] = []
    if currency:
        clauses.append("currency = ?")
        params.append(currency)
    if after_seq is not None:
        clauses.append("seq < ?")
        params.append(after_seq)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit + 1)
    return fetch_all(conn, f"SELECT * FROM fx_alerts {where} ORDER BY seq DESC LIMIT ?", params)


# ————————————————————————————————————————

def count_alerts_since(conn: sqlite3.Connection, currency: str, since: str) -> int:
    return int(
        fetch_value(
            conn, "SELECT COUNT(*) FROM fx_alerts WHERE currency = ? AND created_at >= ?", (currency, since)
        )
        or 0
    )
