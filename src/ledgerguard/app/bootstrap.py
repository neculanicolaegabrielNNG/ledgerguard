from __future__ import annotations

from ledgerguard.accounts import service as accounts
from ledgerguard.app.wiring import make_ctx
from ledgerguard.common.clock import Clock
from ledgerguard.common.context import Actor
from ledgerguard.common.db import connect
from ledgerguard.common.migrate import apply_migrations
from ledgerguard.common.settings import Settings
from ledgerguard.fraud import service as fraud
from ledgerguard.fx import service as fx
from ledgerguard.fx.providers import SimulatedProvider


def prepare_database(settings: Settings, clock: Clock, simulated: SimulatedProvider) -> list[str]:
    conn = connect(settings.db_path)
    try:
        applied = apply_migrations(conn, settings.migrations_dir)
    finally:
        conn.close()
    ctx = make_ctx(settings, clock, "bootstrap", Actor.system("bootstrap"))
    try:
        accounts.ensure_system_accounts(ctx)
        fx.seed_initial_rates(ctx, simulated.initial_rates(), "seed")
        fraud.ensure_default_rules(ctx)
    finally:
        ctx.conn.close()
    return applied
