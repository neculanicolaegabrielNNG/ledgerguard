from __future__ import annotations

import logging
import re
import sqlite3
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ledgerguard.accounts.api import router as accounts_router
from ledgerguard.agents.api import router as agents_router
from ledgerguard.agents.llm import LlmClient, build_llm
from ledgerguard.app.api_misc import router as misc_router
from ledgerguard.app.bootstrap import prepare_database
from ledgerguard.app.workers import lifespan
from ledgerguard.audit.api import router as audit_router
from ledgerguard.audit.service import default_sender
from ledgerguard.auth.api import router as auth_router
from ledgerguard.common.clock import Clock, SystemClock
from ledgerguard.common.errors import DomainError
from ledgerguard.common.ids import new_id
from ledgerguard.common.ratelimit import RateLimiter
from ledgerguard.common.settings import Settings
from ledgerguard.fraud.api import router as fraud_router
from ledgerguard.fx.api import router as fx_router
from ledgerguard.fx.providers import SimulatedProvider, build_provider
from ledgerguard.ledger.api import router as ledger_router
from ledgerguard.simulation.api import router as simulation_router
from ledgerguard.transfers.api import router as transfers_router

API_PREFIX = "/api/v1"
LOGGER = logging.getLogger("ledgerguard.api")
CORRELATION_PATTERN = re.compile(r"^[A-Za-z0-9._\-]{1,64}$")


def _error(request: Request, status: int, code: str, message: str, details: dict[str, Any] | None = None) -> JSONResponse:
    correlation_id = getattr(request.state, "correlation_id", None) or new_id("cor")
    return JSONResponse(
        {"error": {"code": code, "message": message, "correlation_id": correlation_id, "details": details or {}}},
        status_code=status,
        headers={"X-Correlation-ID": correlation_id},
    )


# ————————————————————————————————————————

def _install_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error(request: Request, error: DomainError) -> JSONResponse:
        return _error(request, error.status, error.code, error.message, error.details)

    # ————————————————————————————————————————

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        return _error(
            request,
            422,
            "validation_failed",
            "Cererea conține date invalide.",
            {"errors": jsonable_encoder(error.errors(), custom_encoder={Exception: str})},
        )

    # ————————————————————————————————————————

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, error: StarletteHTTPException) -> JSONResponse:
        return _error(request, error.status_code, f"http_{error.status_code}", str(error.detail))

    # ————————————————————————————————————————

    @app.exception_handler(sqlite3.OperationalError)
    async def database_error(request: Request, error: sqlite3.OperationalError) -> JSONResponse:
        LOGGER.error("database error: %s", error)
        return _error(request, 503, "database_busy", "Baza de date este ocupată. Reîncearcă.")

    # ————————————————————————————————————————

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, error: Exception) -> JSONResponse:
        LOGGER.exception("unhandled error")
        return _error(request, 500, "internal_error", "Eroare internă.")


# ————————————————————————————————————————

def _install_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def correlation(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        supplied = request.headers.get("X-Correlation-ID", "")
        correlation_id = supplied if CORRELATION_PATTERN.match(supplied) else new_id("cor")
        request.state.correlation_id = correlation_id
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response


# ————————————————————————————————————————

def create_app(
    settings: Settings | None = None,
    clock: Clock | None = None,
    llm: LlmClient | None = None,
    with_ui: bool | None = None,
) -> FastAPI:
    active_settings = settings or Settings.from_env()
    active_clock = clock or SystemClock()
    simulated = SimulatedProvider(active_settings.fx_seed, active_settings.fx_volatility_bps)
    prepare_database(active_settings, active_clock, simulated)
    app = FastAPI(title="LedgerGuard", version="1.0.0", lifespan=lifespan)
    app.state.settings = active_settings
    app.state.clock = active_clock
    app.state.simulated = simulated
    app.state.fx_provider = build_provider(active_settings, simulated)
    app.state.limiter = RateLimiter(active_clock, active_settings.rate_limit_window_seconds)
    app.state.llm = llm or build_llm(active_settings)
    app.state.webhook_sender = default_sender
    _install_middleware(app)
    _install_handlers(app)
    for router in (
        misc_router,
        auth_router,
        accounts_router,
        ledger_router,
        fx_router,
        transfers_router,
        fraud_router,
        agents_router,
        audit_router,
        simulation_router,
    ):
        app.include_router(router, prefix=API_PREFIX)
    if active_settings.ui_enabled if with_ui is None else with_ui:
        from ledgerguard.ui.app import mount_ui

        mount_ui(app)
    return app
