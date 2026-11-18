from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw else default


# ————————————————————————————————————————

def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# ————————————————————————————————————————

def _env_str(name: str, default: str) -> str:
    raw = os.environ.get(name)
    return raw if raw else default


# ————————————————————————————————————————

@dataclass(frozen=True)
class Settings:
    db_path: Path
    migrations_dir: Path
    reports_dir: Path
    data_dir: Path
    jwt_secret: str
    jwt_ttl_seconds: int
    password_iterations: int
    fx_provider: str
    fx_refresh_seconds: int
    fx_max_age_seconds: int
    fx_max_change_bps: int
    fx_spread_bps: int
    fx_seed: int
    fx_volatility_bps: int
    bnr_url: str
    frankfurter_url: str
    fraud_review_score: int
    fraud_block_score: int
    rate_limit_window_seconds: int
    rate_limit_login: int
    rate_limit_money: int
    assistant_max_amount_ron_minor: int
    assistant_action_ttl_seconds: int
    anthropic_model: str
    anthropic_api_key: str | None
    worker_enabled: bool
    ui_enabled: bool
    ui_storage_secret: str
    seed_password: str | None

    # ————————————————————————————————————————

    @classmethod
    def from_env(cls) -> Settings:
        data_dir = Path(_env_str("LEDGERGUARD_DATA_DIR", str(PROJECT_ROOT / "data")))
        return cls(
            db_path=Path(_env_str("LEDGERGUARD_DB", str(data_dir / "ledgerguard.db"))),
            migrations_dir=Path(_env_str("LEDGERGUARD_MIGRATIONS", str(PROJECT_ROOT / "migrations"))),
            reports_dir=Path(_env_str("LEDGERGUARD_REPORTS", str(PROJECT_ROOT / "reports"))),
            data_dir=data_dir,
            jwt_secret=_env_str("LEDGERGUARD_JWT_SECRET", secrets.token_hex(32)),
            jwt_ttl_seconds=_env_int("LEDGERGUARD_JWT_TTL", 8 * 3600),
            password_iterations=_env_int("LEDGERGUARD_PASSWORD_ITERATIONS", 200_000),
            fx_provider=_env_str("LEDGERGUARD_FX_PROVIDER", "simulated"),
            fx_refresh_seconds=_env_int("LEDGERGUARD_FX_REFRESH_SECONDS", 60),
            fx_max_age_seconds=_env_int("LEDGERGUARD_FX_MAX_AGE_SECONDS", 86_400),
            fx_max_change_bps=_env_int("LEDGERGUARD_FX_MAX_CHANGE_BPS", 1_000),
            fx_spread_bps=_env_int("LEDGERGUARD_FX_SPREAD_BPS", 50),
            fx_seed=_env_int("LEDGERGUARD_FX_SEED", 1),
            fx_volatility_bps=_env_int("LEDGERGUARD_FX_VOLATILITY_BPS", 30),
            bnr_url=_env_str("LEDGERGUARD_BNR_URL", "https://www.bnr.ro/nbrfxrates.xml"),
            frankfurter_url=_env_str("LEDGERGUARD_FRANKFURTER_URL", "https://api.frankfurter.app"),
            fraud_review_score=_env_int("LEDGERGUARD_FRAUD_REVIEW_SCORE", 50),
            fraud_block_score=_env_int("LEDGERGUARD_FRAUD_BLOCK_SCORE", 90),
            rate_limit_window_seconds=_env_int("LEDGERGUARD_RATE_WINDOW_SECONDS", 60),
            rate_limit_login=_env_int("LEDGERGUARD_RATE_LOGIN", 30),
            rate_limit_money=_env_int("LEDGERGUARD_RATE_MONEY", 120),
            assistant_max_amount_ron_minor=_env_int("LEDGERGUARD_ASSISTANT_MAX_RON_MINOR", 500_000),
            assistant_action_ttl_seconds=_env_int("LEDGERGUARD_ASSISTANT_TTL_SECONDS", 900),
            anthropic_model=_env_str("LEDGERGUARD_ANTHROPIC_MODEL", "claude-sonnet-5-5"),
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY") or None,
            worker_enabled=_env_bool("LEDGERGUARD_WORKER", True),
            ui_enabled=_env_bool("LEDGERGUARD_UI", True),
            ui_storage_secret=_env_str("LEDGERGUARD_UI_SECRET", secrets.token_hex(32)),
            seed_password=os.environ.get("LEDGERGUARD_SEED_PASSWORD") or None,
        )

    # ————————————————————————————————————————

    def with_overrides(self, **values: Any) -> Settings:
        return replace(self, **values)
