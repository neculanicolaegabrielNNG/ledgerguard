from __future__ import annotations

import secrets
import sys

from ledgerguard.accounts import service as accounts
from ledgerguard.agents import testing
from ledgerguard.app import workflows
from ledgerguard.app.bootstrap import prepare_database
from ledgerguard.app.wiring import make_ctx
from ledgerguard.auth import service as auth
from ledgerguard.common.clock import SystemClock
from ledgerguard.common.context import Actor
from ledgerguard.common.settings import Settings
from ledgerguard.fx import service as fx
from ledgerguard.fx.providers import SimulatedProvider

ADMIN_EMAIL = "admin@ledgerguard.local"
COMPLIANCE_EMAIL = "compliance@ledgerguard.local"
CLIENT_EMAIL = "client@ledgerguard.local"
FX_HISTORY_POINTS = 24


def seed(settings: Settings) -> list[tuple[str, str, str]]:
    clock = SystemClock()
    simulated = SimulatedProvider(settings.fx_seed, settings.fx_volatility_bps)
    prepare_database(settings, clock, simulated)
    password = settings.seed_password or secrets.token_urlsafe(12)
    ctx = make_ctx(settings, clock, "seed", Actor(None, "admin", None, "seed"))
    credentials: list[tuple[str, str, str]] = []
    try:
        for email, role in ((ADMIN_EMAIL, "admin"), (COMPLIANCE_EMAIL, "compliance")):
            if not auth.user_exists(ctx, email):
                auth.create_user(ctx, email, password, role, None)
                credentials.append((email, password, role))
        if not auth.user_exists(ctx, CLIENT_EMAIL):
            with ctx.transaction():
                customer = accounts.create_customer(ctx, "Client Demonstrativ")
                auth.create_user(ctx, CLIENT_EMAIL, password, "customer", customer["id"])
                ron = accounts.create_account(ctx, customer["id"], "RON", "Cont curent RON")
                eur = accounts.create_account(ctx, customer["id"], "EUR", "Cont EUR")
                workflows.deposit(ctx, ron["id"], 1_000_000, "Depunere inițială")
                workflows.deposit(ctx, eur["id"], 200_000, "Depunere inițială")
            credentials.append((CLIENT_EMAIL, password, "customer"))
        if accounts.count_customers(ctx) <= 1:
            testing.generate_synthetic_data(ctx, 7, 6, 4, password)
        for _ in range(FX_HISTORY_POINTS):
            fx.refresh(ctx, simulated)
    finally:
        ctx.conn.close()
    return credentials


# ————————————————————————————————————————

def main() -> int:
    settings = Settings.from_env()
    credentials = seed(settings)
    if credentials:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        path = settings.data_dir / "seed_credentials.txt"
        path.write_text(
            "\n".join(f"{email}\t{password}\t{role}" for email, password, role in credentials) + "\n",
            encoding="utf-8",
        )
        print(f"Date inițiale create. Credențiale: {path}")
    else:
        print("Utilizatorii de bază există deja; credențialele existente nu au fost modificate.")
    return 0


# ————————————————————————————————————————

if __name__ == "__main__":
    sys.exit(main())
