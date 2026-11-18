from __future__ import annotations

import sqlite3
from typing import Any

from ledgerguard.common.db import Row, fetch_all, fetch_one


def insert_transfer(conn: sqlite3.Connection, values: dict[str, Any]) -> None:
    conn.execute(
        "INSERT INTO transfers (id, customer_id, from_account_id, to_account_id, amount_minor, currency, "
        "target_amount_minor, target_currency, amount_ron_minor, spread_bps, state, description, channel, "
        "correlation_id, created_at, updated_at) VALUES (:id, :customer_id, :from_account_id, :to_account_id, "
        ":amount_minor, :currency, :target_amount_minor, :target_currency, :amount_ron_minor, :spread_bps, "
        "'created', :description, :channel, :correlation_id, :created_at, :created_at)",
        values,
    )


# ————————————————————————————————————————

def get_transfer(conn: sqlite3.Connection, transfer_id: str) -> Row | None:
    return fetch_one(conn, "SELECT * FROM transfers WHERE id = ?", (transfer_id,))


# ————————————————————————————————————————

def update_state(conn: sqlite3.Connection, transfer_id: str, state: str, at: str) -> None:
    conn.execute("UPDATE transfers SET state = ?, updated_at = ? WHERE id = ?", (state, at, transfer_id))


# ————————————————————————————————————————

def update_evaluation(conn: sqlite3.Connection, transfer_id: str, score: int, decision: str) -> None:
    conn.execute("UPDATE transfers SET risk_score = ?, decision = ? WHERE id = ?", (score, decision, transfer_id))


# ————————————————————————————————————————

def update_execution(
    conn: sqlite3.Connection,
    transfer_id: str,
    target_amount_minor: int,
    amount_ron_minor: int,
    spread_bps: int,
    transaction_id: str,
    at: str,
) -> None:
    conn.execute(
        "UPDATE transfers SET target_amount_minor = ?, amount_ron_minor = ?, spread_bps = ?, transaction_id = ?, "
        "updated_at = ? WHERE id = ?",
        (target_amount_minor, amount_ron_minor, spread_bps, transaction_id, at, transfer_id),
    )


# ————————————————————————————————————————

def insert_transition(
    conn: sqlite3.Connection,
    transfer_id: str,
    from_state: str | None,
    to_state: str,
    actor: str,
    reason: str,
    at: str,
) -> None:
    conn.execute(
        "INSERT INTO transfer_transitions (transfer_id, from_state, to_state, actor, reason, at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (transfer_id, from_state, to_state, actor, reason, at),
    )


# ————————————————————————————————————————

def list_transitions(conn: sqlite3.Connection, transfer_id: str) -> list[Row]:
    return fetch_all(conn, "SELECT * FROM transfer_transitions WHERE transfer_id = ? ORDER BY seq", (transfer_id,))


# ————————————————————————————————————————

def list_transfers(
    conn: sqlite3.Connection,
    filters: dict[str, str | None],
    after_seq: int | None,
    limit: int,
) -> list[Row]:
    clauses: list[str] = []
    params: list[Any] = []
    if filters.get("customer_id"):
        clauses.append("customer_id = ?")
        params.append(filters["customer_id"])
    if filters.get("state"):
        clauses.append("state = ?")
        params.append(filters["state"])
    if filters.get("account_id"):
        clauses.append("(from_account_id = ? OR to_account_id = ?)")
        params.extend([filters["account_id"], filters["account_id"]])
    if filters.get("date_from"):
        clauses.append("created_at >= ?")
        params.append(filters["date_from"])
    if filters.get("date_to"):
        clauses.append("created_at <= ?")
        params.append(filters["date_to"])
    if after_seq is not None:
        clauses.append("seq < ?")
        params.append(after_seq)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit + 1)
    return fetch_all(conn, f"SELECT * FROM transfers {where} ORDER BY seq DESC LIMIT ?", params)


# ————————————————————————————————————————

def fact_rows(conn: sqlite3.Connection, customer_id: str | None, since: str, exclude_id: str | None) -> list[Row]:
    clauses = ["created_at >= ?", "state <> 'cancelled'"]
    params: list[Any] = [since]
    if customer_id:
        clauses.append("customer_id = ?")
        params.append(customer_id)
    if exclude_id:
        clauses.append("id <> ?")
        params.append(exclude_id)
    return fetch_all(
        conn,
        "SELECT id, customer_id, from_account_id, to_account_id, amount_ron_minor, created_at, state "
        f"FROM transfers WHERE {' AND '.join(clauses)} ORDER BY seq",
        params,
    )


# ————————————————————————————————————————

def beneficiary_seen(conn: sqlite3.Connection, customer_id: str, to_account_id: str, exclude_id: str | None) -> bool:
    found = fetch_one(
        conn,
        "SELECT 1 AS seen FROM transfers WHERE customer_id = ? AND to_account_id = ? "
        "AND state IN ('completed', 'approved') AND id <> ? LIMIT 1",
        (customer_id, to_account_id, exclude_id or ""),
    )
    return found is not None


# ————————————————————————————————————————

def similar(
    conn: sqlite3.Connection, customer_id: str, to_account_id: str, low: int, high: int, exclude_id: str, limit: int
) -> list[Row]:
    return fetch_all(
        conn,
        "SELECT * FROM transfers WHERE customer_id = ? AND id <> ? AND state <> 'cancelled' "
        "AND (to_account_id = ? OR amount_ron_minor BETWEEN ? AND ?) ORDER BY seq DESC LIMIT ?",
        (customer_id, exclude_id, to_account_id, low, high, limit),
    )


# ————————————————————————————————————————

def snapshot_rows(conn: sqlite3.Connection, at: str, limit: int) -> list[Row]:
    return fetch_all(
        conn,
        "SELECT t.*, (SELECT to_state FROM transfer_transitions x WHERE x.transfer_id = t.id AND x.at <= ? "
        "ORDER BY x.seq DESC LIMIT 1) AS state_at FROM transfers t WHERE t.created_at <= ? "
        "ORDER BY t.seq DESC LIMIT ?",
        (at, at, limit),
    )


# ————————————————————————————————————————

def insert_scheduled(conn: sqlite3.Connection, values: dict[str, Any]) -> None:
    conn.execute(
        "INSERT INTO scheduled_payments (id, customer_id, from_account_id, to_account_id, amount_minor, "
        "description, interval_seconds, next_run_at, ends_at, created_at) VALUES (:id, :customer_id, "
        ":from_account_id, :to_account_id, :amount_minor, :description, :interval_seconds, :next_run_at, "
        ":ends_at, :created_at)",
        values,
    )


# ————————————————————————————————————————

def get_scheduled(conn: sqlite3.Connection, payment_id: str) -> Row | None:
    return fetch_one(conn, "SELECT * FROM scheduled_payments WHERE id = ?", (payment_id,))


# ————————————————————————————————————————

def list_scheduled(conn: sqlite3.Connection, customer_id: str) -> list[Row]:
    return fetch_all(
        conn, "SELECT * FROM scheduled_payments WHERE customer_id = ? ORDER BY seq DESC", (customer_id,)
    )


# ————————————————————————————————————————

def due_scheduled(conn: sqlite3.Connection, now: str) -> list[Row]:
    return fetch_all(
        conn,
        "SELECT * FROM scheduled_payments WHERE active = 1 AND next_run_at <= ? ORDER BY next_run_at LIMIT 100",
        (now,),
    )


# ————————————————————————————————————————

def update_scheduled(
    conn: sqlite3.Connection, payment_id: str, next_run_at: str, active: bool, last_status: str
) -> None:
    conn.execute(
        "UPDATE scheduled_payments SET next_run_at = ?, active = ?, last_status = ? WHERE id = ?",
        (next_run_at, int(active), last_status, payment_id),
    )


# ————————————————————————————————————————

def deactivate_scheduled(conn: sqlite3.Connection, payment_id: str) -> None:
    conn.execute("UPDATE scheduled_payments SET active = 0 WHERE id = ?", (payment_id,))
