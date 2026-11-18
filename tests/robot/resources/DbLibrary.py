from __future__ import annotations

import sqlite3
from typing import Any


class DbLibrary:
    ROBOT_LIBRARY_SCOPE = "GLOBAL"

    def __init__(self) -> None:
        self._path: str | None = None
        self._conn: sqlite3.Connection | None = None

    # ————————————————————————————————————————

    def connect_to_db(self, path: str) -> None:
        self.disconnect_db()
        self._path = path
        conn = sqlite3.connect(path, timeout=20, isolation_level=None, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        self._conn = conn

    # ————————————————————————————————————————

    def disconnect_db(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ————————————————————————————————————————

    def query(self, sql: str, *params: Any) -> list[dict[str, Any]]:
        assert self._conn is not None, "database not connected"
        return [dict(row) for row in self._conn.execute(sql, params).fetchall()]

    # ————————————————————————————————————————

    def scalar(self, sql: str, *params: Any) -> Any:
        assert self._conn is not None, "database not connected"
        row = self._conn.execute(sql, params).fetchone()
        return row[0] if row is not None else None

    # ————————————————————————————————————————

    def execute_expecting_error(self, sql: str, *params: Any) -> str:
        assert self._conn is not None, "database not connected"
        try:
            self._conn.execute(sql, params)
        except sqlite3.Error as error:
            return str(error)
        raise AssertionError(f"statement succeeded but an error was expected: {sql}")

    # ————————————————————————————————————————

    def execute_statement(self, sql: str, *params: Any) -> None:
        assert self._conn is not None, "database not connected"
        self._conn.execute(sql, params)

    # ————————————————————————————————————————

    def ledger_sums_by_currency(self) -> dict[str, int]:
        rows = self.query("SELECT currency, SUM(amount_minor) AS total FROM ledger_entries GROUP BY currency")
        return {row["currency"]: int(row["total"]) for row in rows}

    # ————————————————————————————————————————

    def unbalanced_transactions(self) -> list[dict[str, Any]]:
        return self.query(
            "SELECT transaction_id, currency, SUM(amount_minor) AS total FROM ledger_entries "
            "GROUP BY transaction_id, currency HAVING SUM(amount_minor) <> 0"
        )

    # ————————————————————————————————————————

    def recomputed_balance(self, account_id: str) -> int:
        return int(
            self.scalar("SELECT COALESCE(SUM(amount_minor), 0) FROM ledger_entries WHERE account_id = ?", account_id)
        )

    # ————————————————————————————————————————

    def total_money(self, currency: str) -> int:
        return int(
            self.scalar(
                "SELECT COALESCE(SUM(e.amount_minor), 0) FROM ledger_entries e JOIN accounts a ON a.id = e.account_id "
                "WHERE a.kind = 'customer' AND e.currency = ?",
                currency,
            )
        )

    # ————————————————————————————————————————

    def system_balance(self, system_key: str) -> int:
        return int(
            self.scalar(
                "SELECT COALESCE(SUM(e.amount_minor), 0) FROM ledger_entries e JOIN accounts a ON a.id = e.account_id "
                "WHERE a.system_key = ?",
                system_key,
            )
        )

    # ————————————————————————————————————————

    def customer_negative_balances(self) -> list[dict[str, Any]]:
        return self.query(
            "SELECT a.id AS account_id, COALESCE(SUM(e.amount_minor), 0) AS balance FROM accounts a "
            "LEFT JOIN ledger_entries e ON e.account_id = a.id WHERE a.kind = 'customer' "
            "GROUP BY a.id HAVING balance < 0"
        )
