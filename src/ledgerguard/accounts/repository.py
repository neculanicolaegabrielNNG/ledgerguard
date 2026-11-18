from __future__ import annotations

import sqlite3
from typing import Any

from ledgerguard.common.db import Row, fetch_all, fetch_one


def insert_customer(conn: sqlite3.Connection, customer_id: str, name: str, created_at: str) -> None:
    conn.execute(
        "INSERT INTO customers (id, name, created_at) VALUES (?, ?, ?)", (customer_id, name, created_at)
    )


# ————————————————————————————————————————

def count_customers(conn: sqlite3.Connection) -> int:
    found = fetch_one(conn, "SELECT COUNT(*) AS total FROM customers")
    return int(found["total"]) if found else 0


# ————————————————————————————————————————

def get_customer(conn: sqlite3.Connection, customer_id: str) -> Row | None:
    return fetch_one(conn, "SELECT * FROM customers WHERE id = ?", (customer_id,))


# ————————————————————————————————————————

def insert_account(
    conn: sqlite3.Connection,
    account_id: str,
    customer_id: str | None,
    currency: str,
    kind: str,
    system_key: str | None,
    name: str,
    allow_negative: bool,
    created_at: str,
) -> None:
    conn.execute(
        "INSERT INTO accounts (id, customer_id, currency, kind, system_key, name, allow_negative, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (account_id, customer_id, currency, kind, system_key, name, int(allow_negative), created_at),
    )


# ————————————————————————————————————————

def get_account(conn: sqlite3.Connection, account_id: str) -> Row | None:
    return fetch_one(
        conn,
        "SELECT a.*, c.name AS customer_name FROM accounts a "
        "LEFT JOIN customers c ON c.id = a.customer_id WHERE a.id = ?",
        (account_id,),
    )


# ————————————————————————————————————————

def get_by_system_key(conn: sqlite3.Connection, system_key: str) -> Row | None:
    return fetch_one(conn, "SELECT * FROM accounts WHERE system_key = ?", (system_key,))


# ————————————————————————————————————————

def list_accounts(
    conn: sqlite3.Connection,
    customer_id: str | None,
    currency: str | None,
    kind: str | None,
    after_seq: int | None,
    limit: int,
) -> list[Row]:
    clauses: list[str] = []
    params: list[Any] = []
    if customer_id:
        clauses.append("a.customer_id = ?")
        params.append(customer_id)
    if currency:
        clauses.append("a.currency = ?")
        params.append(currency)
    if kind:
        clauses.append("a.kind = ?")
        params.append(kind)
    if after_seq is not None:
        clauses.append("a.seq > ?")
        params.append(after_seq)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit + 1)
    return fetch_all(
        conn,
        "SELECT a.*, c.name AS customer_name FROM accounts a "
        f"LEFT JOIN customers c ON c.id = a.customer_id {where} ORDER BY a.seq LIMIT ?",
        params,
    )


# ————————————————————————————————————————

def list_ids_without_overdraft(conn: sqlite3.Connection) -> list[str]:
    return [item["id"] for item in fetch_all(conn, "SELECT id FROM accounts WHERE allow_negative = 0")]


# ————————————————————————————————————————

def list_all(conn: sqlite3.Connection) -> list[Row]:
    return fetch_all(conn, "SELECT * FROM accounts ORDER BY seq")
