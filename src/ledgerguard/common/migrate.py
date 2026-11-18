from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from ledgerguard.common.db import connect
from ledgerguard.common.settings import Settings

CREATE_TABLE = (
    "CREATE TABLE IF NOT EXISTS schema_migrations ("
    "version TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')))"
)


def applied_versions(conn: sqlite3.Connection) -> set[str]:
    conn.execute(CREATE_TABLE)
    return {str(item[0]) for item in conn.execute("SELECT version FROM schema_migrations")}


# ————————————————————————————————————————

def apply_migrations(conn: sqlite3.Connection, directory: Path) -> list[str]:
    done = applied_versions(conn)
    applied: list[str] = []
    for path in sorted(directory.glob("*.sql")):
        version = path.stem
        if version in done:
            continue
        script = path.read_text(encoding="utf-8")
        safe_version = version.replace("'", "''")
        statement = (
            "BEGIN IMMEDIATE;\n"
            f"{script}\n"
            f"INSERT INTO schema_migrations (version) VALUES ('{safe_version}');\n"
            "COMMIT;"
        )
        try:
            conn.executescript(statement)
        except sqlite3.Error:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        applied.append(version)
    return applied


# ————————————————————————————————————————

def migrate(settings: Settings) -> list[str]:
    conn = connect(settings.db_path)
    try:
        return apply_migrations(conn, settings.migrations_dir)
    finally:
        conn.close()


# ————————————————————————————————————————

def main() -> int:
    applied = migrate(Settings.from_env())
    print(f"Migrări aplicate: {', '.join(applied) if applied else 'niciuna'}")
    return 0


# ————————————————————————————————————————

if __name__ == "__main__":
    sys.exit(main())
