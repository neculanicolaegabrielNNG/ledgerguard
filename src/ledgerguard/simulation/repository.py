from __future__ import annotations

import sqlite3

from ledgerguard.common.db import Row, fetch_all, fetch_one


def insert_run(
    conn: sqlite3.Connection,
    run_id: str,
    strategy: str,
    seed: int,
    benign_count: int,
    metrics: str,
    steps: str,
    created_by: str,
    created_at: str,
) -> None:
    conn.execute(
        "INSERT INTO simulation_runs (id, strategy, seed, benign_count, metrics, steps, created_by, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, strategy, seed, benign_count, metrics, steps, created_by, created_at),
    )


# ————————————————————————————————————————

def get_run(conn: sqlite3.Connection, run_id: str) -> Row | None:
    return fetch_one(conn, "SELECT * FROM simulation_runs WHERE id = ?", (run_id,))


# ————————————————————————————————————————

def list_runs(conn: sqlite3.Connection, after_seq: int | None, limit: int) -> list[Row]:
    if after_seq is None:
        return fetch_all(conn, "SELECT * FROM simulation_runs ORDER BY seq DESC LIMIT ?", (limit + 1,))
    return fetch_all(
        conn, "SELECT * FROM simulation_runs WHERE seq < ? ORDER BY seq DESC LIMIT ?", (after_seq, limit + 1)
    )
