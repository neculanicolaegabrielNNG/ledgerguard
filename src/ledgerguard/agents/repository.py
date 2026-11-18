from __future__ import annotations

import sqlite3
from typing import Any

from ledgerguard.common.db import Row, fetch_all, fetch_one


def insert_report(
    conn: sqlite3.Connection,
    report_id: str,
    case_id: str,
    transfer_id: str,
    engine: str,
    recommendation: str,
    confidence: float,
    report: str,
    correlation_id: str,
    created_at: str,
) -> None:
    conn.execute(
        "INSERT INTO agent_reports (id, case_id, transfer_id, engine, recommendation, confidence, report, "
        "correlation_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (report_id, case_id, transfer_id, engine, recommendation, confidence, report, correlation_id, created_at),
    )


# ————————————————————————————————————————

def latest_report(conn: sqlite3.Connection, case_id: str) -> Row | None:
    return fetch_one(conn, "SELECT * FROM agent_reports WHERE case_id = ? ORDER BY seq DESC LIMIT 1", (case_id,))


# ————————————————————————————————————————

def insert_action(
    conn: sqlite3.Connection,
    action_id: str,
    customer_id: str,
    user_id: str,
    payload: str,
    created_at: str,
    expires_at: str,
) -> None:
    conn.execute(
        "INSERT INTO assistant_actions (id, customer_id, user_id, payload, status, created_at, expires_at) "
        "VALUES (?, ?, ?, ?, 'pending', ?, ?)",
        (action_id, customer_id, user_id, payload, created_at, expires_at),
    )


# ————————————————————————————————————————

def get_action(conn: sqlite3.Connection, action_id: str) -> Row | None:
    return fetch_one(conn, "SELECT * FROM assistant_actions WHERE id = ?", (action_id,))


# ————————————————————————————————————————

def update_action(conn: sqlite3.Connection, action_id: str, status: str, resolved_at: str) -> None:
    conn.execute(
        "UPDATE assistant_actions SET status = ?, resolved_at = ? WHERE id = ?", (status, resolved_at, action_id)
    )


# ————————————————————————————————————————

def insert_test_run(
    conn: sqlite3.Connection,
    run_label: str,
    suite: str,
    test: str,
    status: str,
    message: str,
    tags: str,
    recorded_at: str,
) -> None:
    conn.execute(
        "INSERT INTO test_runs (run_label, suite, test, status, message, tags, recorded_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (run_label, suite, test, status, message, tags, recorded_at),
    )


# ————————————————————————————————————————

def history_of_test(conn: sqlite3.Connection, suite: str, test: str, limit: int) -> list[Row]:
    return fetch_all(
        conn,
        "SELECT status, run_label, message FROM test_runs WHERE suite = ? AND test = ? ORDER BY seq DESC LIMIT ?",
        (suite, test, limit),
    )


# ————————————————————————————————————————

def known_run_labels(conn: sqlite3.Connection) -> set[str]:
    return {item["run_label"] for item in fetch_all(conn, "SELECT DISTINCT run_label FROM test_runs")}


# ————————————————————————————————————————

def insert_proposal(
    conn: sqlite3.Connection, proposal_id: str, kind: str, title: str, detail: str, created_at: str
) -> bool:
    cursor = conn.execute(
        "INSERT OR IGNORE INTO test_proposals (id, kind, title, detail, created_at) VALUES (?, ?, ?, ?, ?)",
        (proposal_id, kind, title, detail, created_at),
    )
    return cursor.rowcount > 0


# ————————————————————————————————————————

def list_proposals(conn: sqlite3.Connection, kind: str | None, after_seq: int | None, limit: int) -> list[Row]:
    clauses: list[str] = []
    params: list[Any] = []
    if kind:
        clauses.append("kind = ?")
        params.append(kind)
    if after_seq is not None:
        clauses.append("seq < ?")
        params.append(after_seq)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit + 1)
    return fetch_all(conn, f"SELECT * FROM test_proposals {where} ORDER BY seq DESC LIMIT ?", params)


# ————————————————————————————————————————

def count_proposals(conn: sqlite3.Connection) -> int:
    found = fetch_one(conn, "SELECT COUNT(*) AS total FROM test_proposals")
    return int(found["total"]) if found else 0
