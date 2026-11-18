from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ledgerguard.agents.tools import ANALYST_TOOLS, ASSISTANT_TOOLS, ToolBox
from ledgerguard.app.bootstrap import prepare_database
from ledgerguard.app.wiring import make_ctx
from ledgerguard.common.clock import FixedClock
from ledgerguard.common.context import Actor, Ctx
from ledgerguard.common.errors import DomainError
from ledgerguard.common.settings import Settings
from ledgerguard.fx.providers import SimulatedProvider


@pytest.fixture
def ctx(tmp_path: Path) -> Iterator[Ctx]:
    settings = Settings.from_env().with_overrides(
        db_path=tmp_path / "guards.db",
        data_dir=tmp_path,
        reports_dir=tmp_path / "reports",
        worker_enabled=False,
        anthropic_api_key=None,
    )
    clock = FixedClock(datetime(2026, 3, 2, 9, 0, tzinfo=UTC))
    prepare_database(settings, clock, SimulatedProvider(1, 30))
    context = make_ctx(settings, clock, "unit-guards", Actor.system("unit"))
    yield context
    context.conn.close()


# ————————————————————————————————————————

def test_unknown_tool_is_rejected(ctx: Ctx) -> None:
    box = ToolBox(ctx, ANALYST_TOOLS)
    with pytest.raises(DomainError) as error:
        box.call("run_sql", {"query": "select 1"}, "test")
    assert error.value.code == "tool_not_allowed"


# ————————————————————————————————————————

def test_analyst_cannot_use_assistant_write_tool(ctx: Ctx) -> None:
    box = ToolBox(ctx, ANALYST_TOOLS)
    with pytest.raises(DomainError) as error:
        box.call("prepare_transfer", {"from_account_id": "a", "to_account_id": "b", "amount_minor": 1}, "test")
    assert error.value.code == "tool_not_allowed"


# ————————————————————————————————————————

def test_tool_input_is_validated(ctx: Ctx) -> None:
    box = ToolBox(ctx, ANALYST_TOOLS)
    with pytest.raises(DomainError) as error:
        box.call("get_fx_context", {"currency": "EUROS"}, "test")
    assert error.value.code == "tool_input_invalid"
    with pytest.raises(DomainError):
        box.call("get_account_history", {"account_id": "x", "limit": 5000}, "test")


# ————————————————————————————————————————

def test_tool_call_limit_is_enforced(ctx: Ctx) -> None:
    box = ToolBox(ctx, ANALYST_TOOLS, max_calls=2)
    box.call("get_fx_context", {"currency": "EUR"}, "one")
    box.call("get_fx_context", {"currency": "USD"}, "two")
    with pytest.raises(DomainError) as error:
        box.call("get_fx_context", {"currency": "CHF"}, "three")
    assert error.value.code == "tool_call_limit"


# ————————————————————————————————————————

def test_every_call_is_written_to_the_audit_log(ctx: Ctx) -> None:
    box = ToolBox(ctx, ANALYST_TOOLS)
    box.call("get_fx_context", {"currency": "EUR"}, "motiv de test")
    row = ctx.conn.execute("SELECT entity_id, payload FROM audit_log WHERE action = 'agent.tool_call'").fetchone()
    assert row["entity_id"] == "get_fx_context"
    assert "motiv de test" in row["payload"]


# ————————————————————————————————————————

def test_tools_expose_schemas_without_free_form_sql() -> None:
    names = set(ANALYST_TOOLS) | set(ASSISTANT_TOOLS)
    assert not {name for name in names if "sql" in name or "query" in name}
    for spec in [*ANALYST_TOOLS.values(), *ASSISTANT_TOOLS.values()]:
        assert spec.input_model.model_json_schema()["type"] == "object"
    assert {spec.scope for spec in ANALYST_TOOLS.values()} == {"read"}


# ————————————————————————————————————————

def test_assistant_write_tool_is_only_a_proposal() -> None:
    assert ASSISTANT_TOOLS["prepare_transfer"].scope == "propose"
