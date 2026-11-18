from __future__ import annotations

import sqlite3

from ledgerguard.common.db import Row, fetch_one


def insert_user(
    conn: sqlite3.Connection,
    user_id: str,
    email: str,
    password_hash: str,
    role: str,
    customer_id: str | None,
    created_at: str,
) -> None:
    conn.execute(
        "INSERT INTO users (id, email, password_hash, role, customer_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, email, password_hash, role, customer_id, created_at),
    )


# ————————————————————————————————————————

def get_by_email(conn: sqlite3.Connection, email: str) -> Row | None:
    return fetch_one(conn, "SELECT * FROM users WHERE email = ?", (email,))


# ————————————————————————————————————————

def get_by_id(conn: sqlite3.Connection, user_id: str) -> Row | None:
    return fetch_one(conn, "SELECT * FROM users WHERE id = ?", (user_id,))
