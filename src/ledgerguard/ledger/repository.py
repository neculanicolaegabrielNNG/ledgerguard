from __future__ import annotations

import sqlite3
from typing import Any

from ledgerguard.common.db import Row, fetch_all, fetch_one, fetch_value


def insert_transaction(
    conn: sqlite3.Connection,
    transaction_id: str,
    kind: str,
    description: str,
    transfer_id: str | None,
    reverses_id: str | None,
    residual: int,
    correlation_id: str,
    created_at: str,
) -> None:
    conn.execute(
        "INSERT INTO transactions (id, kind, description, transfer_id, reverses_id, ron_residual_minor, "
        "correlation_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (transaction_id, kind, description, transfer_id, reverses_id, residual, correlation_id, created_at),
    )


# ————————————————————————————————————————

def insert_entry(
    conn: sqlite3.Connection,
    transaction_id: str,
    account_id: str,
    currency: str,
    amount_minor: int,
    amount_ron_minor: int,
    rate_e8: int,
    rate_id: str | None,
    rate_at: str,
    created_at: str,
) -> None:
    conn.execute(
        "INSERT INTO ledger_entries (transaction_id, account_id, currency, amount_minor, amount_ron_minor, "
        "fx_rate_e8, fx_rate_id, fx_rate_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            transaction_id,
            account_id,
            currency,
            amount_minor,
            amount_ron_minor,
            rate_e8,
            rate_id,
            rate_at,
            created_at,
        ),
    )


# ————————————————————————————————————————

def account_balance(conn: sqlite3.Connection, account_id: str, at: str | None) -> int:
    if at is None:
        value = fetch_value(
            conn, "SELECT COALESCE(SUM(amount_minor), 0) FROM ledger_entries WHERE account_id = ?", (account_id,)
        )
    else:
        value = fetch_value(
            conn,
            "SELECT COALESCE(SUM(amount_minor), 0) FROM ledger_entries WHERE account_id = ? AND created_at <= ?",
            (account_id, at),
        )
    return int(value or 0)


# ————————————————————————————————————————

def get_transaction(conn: sqlite3.Connection, transaction_id: str) -> Row | None:
    return fetch_one(conn, "SELECT * FROM transactions WHERE id = ?", (transaction_id,))


# ————————————————————————————————————————

def entries_for_transaction(conn: sqlite3.Connection, transaction_id: str) -> list[Row]:
    return fetch_all(
        conn, "SELECT * FROM ledger_entries WHERE transaction_id = ? ORDER BY seq", (transaction_id,)
    )


# ————————————————————————————————————————

def reversal_of(conn: sqlite3.Connection, transaction_id: str) -> Row | None:
    return fetch_one(conn, "SELECT * FROM transactions WHERE reverses_id = ?", (transaction_id,))


# ————————————————————————————————————————

def list_entries(
    conn: sqlite3.Connection,
    account_id: str,
    date_from: str | None,
    date_to: str | None,
    after_seq: int | None,
    limit: int,
) -> list[Row]:
    clauses = ["e.account_id = ?"]
    params: list[Any] = [account_id]
    if date_from:
        clauses.append("e.created_at >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("e.created_at <= ?")
        params.append(date_to)
    if after_seq is not None:
        clauses.append("e.seq < ?")
        params.append(after_seq)
    params.append(limit + 1)
    return fetch_all(
        conn,
        "SELECT e.*, t.kind AS transaction_kind, t.description AS transaction_description, "
        "t.transfer_id AS transfer_id FROM ledger_entries e JOIN transactions t ON t.id = e.transaction_id "
        f"WHERE {' AND '.join(clauses)} ORDER BY e.seq DESC LIMIT ?",
        params,
    )


# ————————————————————————————————————————

def currency_sums(conn: sqlite3.Connection) -> list[Row]:
    return fetch_all(
        conn, "SELECT currency, COALESCE(SUM(amount_minor), 0) AS total FROM ledger_entries GROUP BY currency"
    )


# ————————————————————————————————————————

def unbalanced_transactions(conn: sqlite3.Connection) -> list[Row]:
    return fetch_all(
        conn,
        "SELECT transaction_id, currency, SUM(amount_minor) AS total FROM ledger_entries "
        "GROUP BY transaction_id, currency HAVING SUM(amount_minor) <> 0",
    )


# ————————————————————————————————————————

def count_entries(conn: sqlite3.Connection) -> int:
    return int(fetch_value(conn, "SELECT COUNT(*) FROM ledger_entries") or 0)


# ————————————————————————————————————————

def transactions_between(conn: sqlite3.Connection, created_before: str) -> int:
    return int(fetch_value(conn, "SELECT COUNT(*) FROM transactions WHERE created_at <= ?", (created_before,)) or 0)
