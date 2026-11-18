from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI

from ledgerguard.agents import service as agents
from ledgerguard.app.wiring import make_ctx
from ledgerguard.audit import service as audit
from ledgerguard.common.context import Actor
from ledgerguard.fx import service as fx
from ledgerguard.transfers import service as transfers

LOGGER = logging.getLogger("ledgerguard.workers")
MAINTENANCE_INTERVAL_SECONDS = 5


def refresh_fx_once(app: FastAPI) -> None:
    ctx = make_ctx(app.state.settings, app.state.clock, "worker-fx", Actor.system("worker:fx"))
    try:
        fx.refresh(ctx, app.state.fx_provider)
    finally:
        ctx.conn.close()


# ————————————————————————————————————————

def maintenance_once(app: FastAPI) -> None:
    ctx = make_ctx(app.state.settings, app.state.clock, "worker-maintenance", Actor.system("worker:maintenance"))
    try:
        transfers.run_due_scheduled(ctx)
        agents.analyze_pending(ctx, app.state.llm)
        audit.deliver_pending(ctx, app.state.webhook_sender)
    finally:
        ctx.conn.close()


# ————————————————————————————————————————

async def fx_loop(app: FastAPI) -> None:
    interval = max(1, app.state.settings.fx_refresh_seconds)
    while True:
        await asyncio.sleep(interval)
        try:
            await asyncio.to_thread(refresh_fx_once, app)
        except Exception:
            LOGGER.exception("fx refresh failed")


# ————————————————————————————————————————

async def maintenance_loop(app: FastAPI) -> None:
    while True:
        await asyncio.sleep(MAINTENANCE_INTERVAL_SECONDS)
        try:
            await asyncio.to_thread(maintenance_once, app)
        except Exception:
            LOGGER.exception("maintenance failed")


# ————————————————————————————————————————

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    tasks: list[asyncio.Task[None]] = []
    if app.state.settings.worker_enabled:
        try:
            await asyncio.to_thread(refresh_fx_once, app)
        except Exception:
            LOGGER.exception("initial fx refresh failed")
        tasks = [asyncio.create_task(fx_loop(app)), asyncio.create_task(maintenance_loop(app))]
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
