from __future__ import annotations

import sqlite3
from typing import Any

from ledgerguard.common.db import Row, fetch_all, fetch_one


def insert_rule(
    conn: sqlite3.Connection,
    rule_id: str,
    version: int,
    name: str,
    rule_type: str,
    params: str,
    priority: int,
    effect: str,
    active: bool,
    valid_from: str,
    changed_by: str,
) -> None:
    conn.execute(
        "INSERT INTO fraud_rules (id, version, name, type, params, priority, effect, active, valid_from, changed_by) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (rule_id, version, name, rule_type, params, priority, effect, int(active), valid_from, changed_by),
    )


# ————————————————————————————————————————

def latest_version(conn: sqlite3.Connection, rule_id: str) -> Row | None:
    return fetch_one(conn, "SELECT * FROM fraud_rules WHERE id = ? ORDER BY version DESC LIMIT 1", (rule_id,))


# ————————————————————————————————————————

def versions_at(conn: sqlite3.Connection, at: str) -> list[Row]:
    return fetch_all(
        conn,
        "SELECT r.* FROM fraud_rules r WHERE r.valid_from <= ? AND r.version = "
        "(SELECT MAX(version) FROM fraud_rules WHERE id = r.id AND valid_from <= ?) "
        "ORDER BY r.priority, r.id",
        (at, at),
    )


# ————————————————————————————————————————

def all_versions(conn: sqlite3.Connection, rule_id: str | None) -> list[Row]:
    if rule_id:
        return fetch_all(conn, "SELECT * FROM fraud_rules WHERE id = ? ORDER BY version", (rule_id,))
    return fetch_all(conn, "SELECT * FROM fraud_rules ORDER BY priority, id, version")


# ————————————————————————————————————————

def count_rules(conn: sqlite3.Connection) -> int:
    found = fetch_one(conn, "SELECT COUNT(*) AS total FROM fraud_rules")
    return int(found["total"]) if found else 0


# ————————————————————————————————————————

def insert_evaluation(
    conn: sqlite3.Connection,
    evaluation_id: str,
    transfer_id: str,
    score: int,
    decision: str,
    results: str,
    thresholds: str,
    correlation_id: str,
    created_at: str,
) -> None:
    conn.execute(
        "INSERT INTO fraud_evaluations (id, transfer_id, score, decision, results, thresholds, correlation_id, "
        "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (evaluation_id, transfer_id, score, decision, results, thresholds, correlation_id, created_at),
    )


# ————————————————————————————————————————

def evaluation_for_transfer(conn: sqlite3.Connection, transfer_id: str) -> Row | None:
    return fetch_one(
        conn, "SELECT * FROM fraud_evaluations WHERE transfer_id = ? ORDER BY seq DESC LIMIT 1", (transfer_id,)
    )


# ————————————————————————————————————————

def get_evaluation(conn: sqlite3.Connection, evaluation_id: str) -> Row | None:
    return fetch_one(conn, "SELECT * FROM fraud_evaluations WHERE id = ?", (evaluation_id,))


# ————————————————————————————————————————

def evaluations_until(conn: sqlite3.Connection, at: str, limit: int) -> list[Row]:
    return fetch_all(
        conn,
        "SELECT * FROM fraud_evaluations WHERE created_at <= ? ORDER BY seq DESC LIMIT ?",
        (at, limit),
    )


# ————————————————————————————————————————

def insert_case(
    conn: sqlite3.Connection, case_id: str, transfer_id: str, evaluation_id: str, score: int, opened_at: str
) -> None:
    conn.execute(
        "INSERT INTO fraud_cases (id, transfer_id, evaluation_id, score, status, opened_at) "
        "VALUES (?, ?, ?, ?, 'open', ?)",
        (case_id, transfer_id, evaluation_id, score, opened_at),
    )


# ————————————————————————————————————————

def get_case(conn: sqlite3.Connection, case_id: str) -> Row | None:
    return fetch_one(conn, "SELECT * FROM fraud_cases WHERE id = ?", (case_id,))


# ————————————————————————————————————————

def case_for_transfer(conn: sqlite3.Connection, transfer_id: str) -> Row | None:
    return fetch_one(conn, "SELECT * FROM fraud_cases WHERE transfer_id = ?", (transfer_id,))


# ————————————————————————————————————————

def list_cases(
    conn: sqlite3.Connection,
    statuses: list[str],
    after: tuple[int, int] | None,
    limit: int,
) -> list[Row]:
    marks = ", ".join("?" for _ in statuses)
    clauses = [f"status IN ({marks})"]
    params: list[Any] = list(statuses)
    if after is not None:
        clauses.append("(score < ? OR (score = ? AND seq > ?))")
        params.extend([after[0], after[0], after[1]])
    params.append(limit + 1)
    return fetch_all(
        conn,
        f"SELECT * FROM fraud_cases WHERE {' AND '.join(clauses)} ORDER BY score DESC, seq ASC LIMIT ?",
        params,
    )


# ————————————————————————————————————————

def update_case(
    conn: sqlite3.Connection,
    case_id: str,
    status: str,
    resolution: str | None,
    resolved_at: str | None,
    resolved_by: str | None,
    comment: str | None,
) -> None:
    conn.execute(
        "UPDATE fraud_cases SET status = ?, resolution = ?, resolved_at = ?, resolved_by = ?, comment = ? "
        "WHERE id = ?",
        (status, resolution, resolved_at, resolved_by, comment, case_id),
    )


# ————————————————————————————————————————

def insert_action(conn: sqlite3.Connection, case_id: str, action: str, comment: str, actor: str, at: str) -> None:
    conn.execute(
        "INSERT INTO fraud_case_actions (case_id, action, comment, actor, at) VALUES (?, ?, ?, ?, ?)",
        (case_id, action, comment, actor, at),
    )


# ————————————————————————————————————————

def list_actions(conn: sqlite3.Connection, case_id: str) -> list[Row]:
    return fetch_all(conn, "SELECT * FROM fraud_case_actions WHERE case_id = ? ORDER BY seq", (case_id,))
