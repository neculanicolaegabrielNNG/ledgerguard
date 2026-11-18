from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from typing import Any

from ledgerguard.common.db import Row, fetch_all, fetch_one


def insert_log(
    conn: sqlite3.Connection,
    at: str,
    correlation_id: str,
    actor: str,
    actor_role: str,
    action: str,
    entity_type: str,
    entity_id: str,
    payload: str,
) -> int:
    cursor = conn.execute(
        "INSERT INTO audit_log (at, correlation_id, actor, actor_role, action, entity_type, entity_id, payload) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (at, correlation_id, actor, actor_role, action, entity_type, entity_id, payload),
    )
    return int(cursor.lastrowid or 0)


# ————————————————————————————————————————

def search_logs(
    conn: sqlite3.Connection,
    filters: dict[str, str | None],
    text: str | None,
    after_seq: int | None,
    limit: int,
) -> list[Row]:
    clauses: list[str] = []
    params: list[Any] = []
    for column in ("entity_type", "entity_id", "actor", "action", "correlation_id"):
        value = filters.get(column)
        if value:
            clauses.append(f"{column} = ?")
            params.append(value)
    if filters.get("date_from"):
        clauses.append("at >= ?")
        params.append(filters["date_from"])
    if filters.get("date_to"):
        clauses.append("at <= ?")
        params.append(filters["date_to"])
    if text:
        clauses.append("(action LIKE ? OR entity_id LIKE ? OR payload LIKE ? OR actor LIKE ?)")
        pattern = f"%{text}%"
        params.extend([pattern, pattern, pattern, pattern])
    if after_seq is not None:
        clauses.append("seq < ?")
        params.append(after_seq)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit + 1)
    return fetch_all(conn, f"SELECT * FROM audit_log {where} ORDER BY seq DESC LIMIT ?", params)


# ————————————————————————————————————————

def insert_webhook(
    conn: sqlite3.Connection,
    webhook_id: str,
    url: str,
    events: str,
    secret: str,
    created_at: str,
    created_by: str,
) -> None:
    conn.execute(
        "INSERT INTO webhooks (id, url, events, secret, created_at, created_by) VALUES (?, ?, ?, ?, ?, ?)",
        (webhook_id, url, events, secret, created_at, created_by),
    )


# ————————————————————————————————————————

def list_webhooks(conn: sqlite3.Connection, active_only: bool) -> list[Row]:
    sql = "SELECT * FROM webhooks" + (" WHERE active = 1" if active_only else "") + " ORDER BY seq"
    return fetch_all(conn, sql)


# ————————————————————————————————————————

def get_webhook(conn: sqlite3.Connection, webhook_id: str) -> Row | None:
    return fetch_one(conn, "SELECT * FROM webhooks WHERE id = ?", (webhook_id,))


# ————————————————————————————————————————

def deactivate_webhook(conn: sqlite3.Connection, webhook_id: str) -> None:
    conn.execute("UPDATE webhooks SET active = 0 WHERE id = ?", (webhook_id,))


# ————————————————————————————————————————

def insert_delivery(
    conn: sqlite3.Connection, delivery_id: str, webhook_id: str, event: str, payload: str, created_at: str
) -> None:
    conn.execute(
        "INSERT INTO webhook_deliveries (id, webhook_id, event, payload, created_at) VALUES (?, ?, ?, ?, ?)",
        (delivery_id, webhook_id, event, payload, created_at),
    )


# ————————————————————————————————————————

def pending_deliveries(conn: sqlite3.Connection, limit: int) -> list[Row]:
    return fetch_all(
        conn,
        "SELECT d.*, w.url AS url, w.secret AS secret FROM webhook_deliveries d "
        "JOIN webhooks w ON w.id = d.webhook_id "
        "WHERE d.status = 'pending' AND d.attempts < 5 ORDER BY d.seq LIMIT ?",
        (limit,),
    )


# ————————————————————————————————————————

def mark_delivery(
    conn: sqlite3.Connection, delivery_id: str, status: str, status_code: int | None, at: str
) -> None:
    conn.execute(
        "UPDATE webhook_deliveries SET status = ?, attempts = attempts + 1, last_status_code = ?, "
        "delivered_at = CASE WHEN ? = 'delivered' THEN ? ELSE delivered_at END WHERE id = ?",
        (status, status_code, status, at, delivery_id),
    )


# ————————————————————————————————————————

def list_deliveries(conn: sqlite3.Connection, after_seq: int | None, limit: int) -> list[Row]:
    params: Sequence[Any]
    if after_seq is None:
        return fetch_all(conn, "SELECT * FROM webhook_deliveries ORDER BY seq DESC LIMIT ?", (limit + 1,))
    params = (after_seq, limit + 1)
    return fetch_all(
        conn, "SELECT * FROM webhook_deliveries WHERE seq < ? ORDER BY seq DESC LIMIT ?", params
    )
