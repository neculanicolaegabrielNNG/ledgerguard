from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from ledgerguard.audit import service as audit
from ledgerguard.common.clock import to_iso
from ledgerguard.common.context import Ctx
from ledgerguard.common.db import Row
from ledgerguard.common.errors import invalid, not_found
from ledgerguard.common.ids import new_id
from ledgerguard.common.pagination import build_page, clamp_limit, decode_seq
from ledgerguard.simulation import repository
from ledgerguard.simulation.metrics import compute_metrics
from ledgerguard.simulation.runner import Advance, SimClient, run_scenario
from ledgerguard.simulation.strategies import STRATEGIES, build_scenario


def _view(row: Row) -> Row:
    return {**row, "metrics": json.loads(row["metrics"]), "steps": json.loads(row["steps"])}


# ————————————————————————————————————————

def run(
    ctx: Ctx,
    client: SimClient,
    admin_token: str,
    strategy: str,
    seed: int,
    benign_count: int,
    advance: Advance | None,
) -> Row:
    if strategy not in STRATEGIES:
        raise invalid("unknown_strategy", "Strategie necunoscută.", {"strategies": list(STRATEGIES)})
    scenario = build_scenario(strategy, seed, benign_count)
    run_id = new_id("sim")
    outcomes = run_scenario(client, admin_token, scenario, run_id[-12:], advance)
    metrics = compute_metrics(outcomes)
    with ctx.transaction():
        repository.insert_run(
            ctx.conn,
            run_id,
            strategy,
            seed,
            benign_count,
            json.dumps(metrics, sort_keys=True),
            json.dumps([asdict(item) for item in outcomes]),
            ctx.actor.label,
            to_iso(ctx.clock.now()),
        )
        audit.record(ctx, "simulation.run", "simulation", run_id, {"strategy": strategy, "seed": seed, **metrics})
    return get_run(ctx, run_id)


# ————————————————————————————————————————

def get_run(ctx: Ctx, run_id: str) -> Row:
    found = repository.get_run(ctx.conn, run_id)
    if found is None:
        raise not_found("simulation_run", run_id)
    return _view(found)


# ————————————————————————————————————————

def list_runs(ctx: Ctx, cursor: str | None, limit: int) -> dict[str, Any]:
    size = clamp_limit(limit)
    page = build_page(repository.list_runs(ctx.conn, decode_seq(cursor), size), size)
    page["items"] = [{**_view(item), "steps": []} for item in page["items"]]
    return page
