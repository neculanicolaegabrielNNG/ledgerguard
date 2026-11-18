from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ledgerguard.common.db import connect
from ledgerguard.common.migrate import apply_migrations
from ledgerguard.common.settings import PROJECT_ROOT
from ledgerguard.simulation.metrics import StepOutcome, compute_metrics
from ledgerguard.simulation.strategies import STRATEGIES, build_scenario


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_scenarios_are_reproducible(strategy: str) -> None:
    assert build_scenario(strategy, 11, 8) == build_scenario(strategy, 11, 8)
    assert build_scenario(strategy, 11, 8) != build_scenario(strategy, 12, 8)


# ————————————————————————————————————————

@pytest.mark.parametrize("strategy", STRATEGIES)
def test_scenario_steps_are_ordered_and_reference_known_accounts(strategy: str) -> None:
    scenario = build_scenario(strategy, 3, 6)
    keys = {account.key for account in scenario.accounts}
    offsets = [step.offset_seconds for step in scenario.steps]
    assert offsets == sorted(offsets)
    assert [step.index for step in scenario.steps] == list(range(len(scenario.steps)))
    assert all(step.from_key in keys and step.to_key in keys for step in scenario.steps)
    assert any(step.malicious for step in scenario.steps)


# ————————————————————————————————————————

def test_metrics_compute_detection_and_false_alarms() -> None:
    outcomes = [
        StepOutcome(0, "benign", False, 0, "completed"),
        StepOutcome(1, "attack", True, 100, "completed"),
        StepOutcome(2, "attack", True, 700, "under_review"),
        StepOutcome(3, "benign", False, 800, "blocked"),
        StepOutcome(4, "attack", True, 1_300, "blocked"),
    ]
    metrics = compute_metrics(outcomes)
    assert metrics["malicious_total"] == 3
    assert metrics["malicious_caught"] == 2
    assert metrics["false_alarms"] == 1
    assert metrics["steps_to_detection"] == 2
    assert metrics["seconds_to_detection"] == 600
    assert metrics["detection_rate_pct"] == 66
    assert metrics["false_alarm_rate_pct"] == 50


# ————————————————————————————————————————

def migrated(tmp_path: Path) -> sqlite3.Connection:
    conn = connect(tmp_path / "unit.db")
    apply_migrations(conn, PROJECT_ROOT / "migrations")
    return conn


# ————————————————————————————————————————

def test_migrations_are_applied_once(tmp_path: Path) -> None:
    conn = migrated(tmp_path)
    assert apply_migrations(conn, PROJECT_ROOT / "migrations") == []
    conn.close()


# ————————————————————————————————————————

def test_ledger_rejects_update_and_delete(tmp_path: Path) -> None:
    conn = migrated(tmp_path)
    conn.execute(
        "INSERT INTO accounts (id, currency, kind, system_key, name, allow_negative, created_at) "
        "VALUES ('a1', 'RON', 'system_cash', 'k1', 'x', 1, 't')"
    )
    conn.execute(
        "INSERT INTO accounts (id, currency, kind, system_key, name, allow_negative, created_at) "
        "VALUES ('a2', 'RON', 'fx_exchange', 'k2', 'y', 1, 't')"
    )
    conn.execute(
        "INSERT INTO transactions (id, kind, correlation_id, created_at) VALUES ('t1', 'deposit', 'c', 't')"
    )
    conn.execute(
        "INSERT INTO ledger_entries (transaction_id, account_id, currency, amount_minor, amount_ron_minor, "
        "fx_rate_e8, fx_rate_at, created_at) VALUES ('t1', 'a1', 'RON', -100, -100, 100000000, 't', 't')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE ledger_entries SET amount_minor = 5")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM ledger_entries")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE transactions SET description = 'x'")
    conn.close()


# ————————————————————————————————————————

def test_ledger_rejects_currency_mismatch(tmp_path: Path) -> None:
    conn = migrated(tmp_path)
    conn.execute(
        "INSERT INTO accounts (id, currency, kind, system_key, name, allow_negative, created_at) "
        "VALUES ('a1', 'RON', 'system_cash', 'k1', 'x', 1, 't')"
    )
    conn.execute(
        "INSERT INTO transactions (id, kind, correlation_id, created_at) VALUES ('t1', 'deposit', 'c', 't')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO ledger_entries (transaction_id, account_id, currency, amount_minor, amount_ron_minor, "
            "fx_rate_e8, fx_rate_at, created_at) VALUES ('t1', 'a1', 'EUR', 100, 497, 497000000, 't', 't')"
        )
    conn.close()
