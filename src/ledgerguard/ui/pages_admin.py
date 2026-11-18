from __future__ import annotations

import json
from typing import Any

from nicegui import ui

from ledgerguard.common.money import FOREIGN_CURRENCIES
from ledgerguard.simulation.strategies import STRATEGIES
from ledgerguard.ui.api_client import request
from ledgerguard.ui.layout import frame, tid

ADMIN_ROLES = ("admin",)


def _percent_text(bps: int) -> str:
    sign = "-" if bps < 0 else "+"
    whole, fraction = divmod(abs(bps), 100)
    return f"{sign}{whole}.{fraction:02d}%"


# ————————————————————————————————————————

@ui.page("/admin/rules")
async def rules_page() -> None:
    session = frame("Reguli antifraudă", ADMIN_ROLES)
    if session is None:
        return
    with ui.column().classes("w-full q-pa-md"):
        ui.label("Reguli active și istoricul versiunilor").classes("text-h6")
        history = tid(ui.switch("Arată toate versiunile"), "rules-history")
        columns = [
            {"name": "key", "label": "Regulă", "field": "key", "align": "left"},
            {"name": "name", "label": "Denumire", "field": "name", "align": "left"},
            {"name": "effect", "label": "Efect", "field": "effect"},
            {"name": "priority", "label": "Prioritate", "field": "priority"},
            {"name": "active", "label": "Activă", "field": "active"},
            {"name": "valid_from", "label": "Valabilă din", "field": "valid_from", "align": "left"},
            {"name": "params", "label": "Parametri", "field": "params", "align": "left"},
        ]
        table = tid(ui.table(columns=columns, rows=[], row_key="key").classes("w-full"), "rules-table")

        async def load() -> None:
            body = await request(session, "GET", "/fraud/rules", params={"include_history": str(history.value).lower()})
            table.rows = [
                {
                    "key": f"{item['id']} v{item['version']}",
                    "rule_id": item["id"],
                    "name": item["name"],
                    "effect": item["effect"],
                    "priority": item["priority"],
                    "active": "da" if item["active"] else "nu",
                    "valid_from": item["valid_from"],
                    "params": json.dumps(item["params"], ensure_ascii=False),
                    "params_raw": item["params"],
                }
                for item in (body or {}).get("items", [])
            ]
            table.update()

        history.on_value_change(load)
        ui.label("Modifică o regulă (creează versiune nouă)").classes("text-subtitle1")
        rule_id = tid(ui.input("Identificator regulă (ex. R-VELOCITY)"), "rule-id").classes("w-96")
        params = tid(ui.textarea("Parametri de modificat (JSON, ex. {\"max_count\": 4})"), "rule-params").classes("w-96")
        effect = tid(ui.select(["", "score_add", "review", "block"], value="", label="Efect"), "rule-effect")
        active = tid(ui.select({"": "neschimbat", "true": "activă", "false": "inactivă"}, value="", label="Stare"), "rule-active")

        async def save() -> None:
            payload: dict[str, Any] = {}
            if params.value.strip():
                try:
                    payload["params"] = json.loads(params.value)
                except ValueError:
                    ui.notify("JSON invalid pentru parametri.", type="negative")
                    return
            if effect.value:
                payload["effect"] = effect.value
            if active.value:
                payload["active"] = active.value == "true"
            if not payload:
                ui.notify("Nu ai indicat nicio modificare.", type="warning")
                return
            body = await request(session, "PUT", f"/fraud/rules/{rule_id.value.strip()}", json=payload)
            if body is not None:
                ui.notify(f"Versiune nouă: v{body['version']}")
                await load()

        tid(ui.button("Salvează versiune nouă", on_click=save), "rule-save")
        await load()


# ————————————————————————————————————————

@ui.page("/admin/audit")
async def audit_page() -> None:
    session = frame("Audit", ADMIN_ROLES)
    if session is None:
        return
    state: dict[str, Any] = {"cursor": None}
    with ui.column().classes("w-full q-pa-md"):
        ui.label("Jurnal de audit").classes("text-h6")
        with ui.row():
            text = tid(ui.input("Căutare text"), "audit-q")
            action = tid(ui.input("Acțiune (exact)"), "audit-action")
            entity = tid(ui.input("Tip entitate"), "audit-entity")
            correlation = tid(ui.input("Correlation ID"), "audit-correlation")
        columns = [
            {"name": "at", "label": "Moment", "field": "at", "align": "left"},
            {"name": "actor", "label": "Actor", "field": "actor", "align": "left"},
            {"name": "action", "label": "Acțiune", "field": "action", "align": "left"},
            {"name": "entity", "label": "Entitate", "field": "entity", "align": "left"},
            {"name": "payload", "label": "Detalii", "field": "payload", "align": "left"},
        ]
        table = tid(ui.table(columns=columns, rows=[], row_key="seq").classes("w-full"), "audit-table")

        async def load(reset: bool) -> None:
            if reset:
                state["cursor"] = None
            body = await request(
                session,
                "GET",
                "/audit",
                params={
                    "q": text.value,
                    "action": action.value,
                    "entity_type": entity.value,
                    "correlation_id": correlation.value,
                    "cursor": state["cursor"],
                    "limit": 50,
                },
            )
            if body is None:
                return
            rows = [
                {
                    "seq": item["seq"],
                    "at": item["at"],
                    "actor": f"{item['actor']} ({item['actor_role']})",
                    "action": item["action"],
                    "entity": f"{item['entity_type']}:{item['entity_id']}",
                    "payload": json.dumps(item["payload"], ensure_ascii=False)[:300],
                }
                for item in body["items"]
            ]
            table.rows = rows if reset else [*table.rows, *rows]
            table.update()
            state["cursor"] = body["next_cursor"]

        # ————————————————————————————————————————

        async def search() -> None:
            await load(True)

        # ————————————————————————————————————————

        async def more() -> None:
            await load(False)

        with ui.row():
            tid(ui.button("Caută", on_click=search), "audit-search")
            tid(ui.button("Încarcă mai multe", on_click=more), "audit-more")
        await load(True)


# ————————————————————————————————————————

@ui.page("/admin/fx")
async def fx_page() -> None:
    session = frame("Cursuri valutare", ADMIN_ROLES)
    if session is None:
        return
    rates = await request(session, "GET", "/fx/rates")
    alerts = await request(session, "GET", "/fx/alerts", params={"limit": 20})
    series = []
    axis: list[str] = []
    for currency in FOREIGN_CURRENCIES:
        body = await request(session, "GET", "/fx/rates/history", params={"currency": currency, "limit": 100})
        points = list(reversed((body or {}).get("items", [])))
        axis = [item["valid_from"][11:19] for item in points] or axis
        series.append({"type": "line", "name": currency, "showSymbol": False, "data": [item["rate"] for item in points]})
    with ui.column().classes("w-full q-pa-md"):
        ui.label("Evoluția cursului (RON pentru o unitate)").classes("text-h6")
        tid(
            ui.echart(
                {
                    "tooltip": {"trigger": "axis"},
                    "legend": {},
                    "xAxis": {"type": "category", "data": axis},
                    "yAxis": {"type": "value", "scale": True},
                    "series": series,
                }
            ).classes("w-full h-72"),
            "fx-chart",
        )
        rate_rows = [
            {
                "currency": item["currency"],
                "rate": item["rate"],
                "source": item["source"],
                "valid_from": item["valid_from"],
                "status": "actual" if item["status"] == "fresh" else "expirat",
            }
            for item in (rates or {}).get("items", [])
        ]
        tid(
            ui.table(
                columns=[
                    {"name": "currency", "label": "Monedă", "field": "currency"},
                    {"name": "rate", "label": "Curs", "field": "rate"},
                    {"name": "source", "label": "Sursă", "field": "source"},
                    {"name": "valid_from", "label": "Actualizat", "field": "valid_from", "align": "left"},
                    {"name": "status", "label": "Stare", "field": "status"},
                ],
                rows=rate_rows,
                row_key="currency",
            ).classes("w-full"),
            "fx-table",
        )
        ui.label("Alerte de curs").classes("text-subtitle1")
        alert_rows = [
            {
                "id": item["id"],
                "currency": item["currency"],
                "change": _percent_text(item["change_bps"]),
                "created_at": item["created_at"],
            }
            for item in (alerts or {}).get("items", [])
        ]
        tid(
            ui.table(
                columns=[
                    {"name": "currency", "label": "Monedă", "field": "currency"},
                    {"name": "change", "label": "Variație respinsă", "field": "change"},
                    {"name": "created_at", "label": "Moment", "field": "created_at", "align": "left"},
                ],
                rows=alert_rows,
                row_key="id",
            ).classes("w-full"),
            "fx-alerts",
        )
        ui.label("Comenzi simulator de curs").classes("text-subtitle1")
        with ui.row():
            currency = tid(ui.select(list(FOREIGN_CURRENCIES), value="USD", label="Monedă"), "fx-currency")
            bps = tid(ui.number("Șoc (puncte de bază)", value=500, format="%.0f"), "fx-bps")

        async def shock() -> None:
            body = await request(
                session, "POST", "/fx/shock", json={"currency": currency.value, "bps": int(bps.value)}
            )
            if body is not None:
                ui.notify("Șoc aplicat la furnizorul simulat.")

        # ————————————————————————————————————————

        async def refresh() -> None:
            body = await request(session, "POST", "/fx/refresh")
            if body is not None:
                ui.notify(f"Aplicate: {len(body['applied'])}, respinse: {len(body['rejected'])}")
                ui.navigate.reload()

        # ————————————————————————————————————————

        async def freeze(value: bool) -> None:
            if await request(session, "POST", "/fx/freeze", json={"frozen": value}) is not None:
                ui.notify("Curs înghețat." if value else "Curs reluat.")

        with ui.row():
            tid(ui.button("Aplică șoc", on_click=shock), "fx-shock")
            tid(ui.button("Actualizează acum", on_click=refresh), "fx-refresh")
            tid(ui.button("Îngheață", on_click=lambda: freeze(True)), "fx-freeze")
            tid(ui.button("Reia", on_click=lambda: freeze(False)), "fx-unfreeze")


# ————————————————————————————————————————

@ui.page("/admin/quality")
async def quality_page() -> None:
    session = frame("Panou de calitate", ADMIN_ROLES)
    if session is None:
        return
    panel = await request(session, "GET", "/quality/panel")
    panel = panel or {"tests": {"available": False, "total": 0, "passed": 0, "failed": 0, "suites": {}}, "rule_coverage": [], "proposals": 0, "rules_covered": 0, "rules_total": 0}
    tests = panel["tests"]
    with ui.column().classes("w-full q-pa-md"):
        ui.label("Starea testelor").classes("text-h6")
        if tests["available"]:
            tid(ui.label(f"Total {tests['total']} · trecute {tests['passed']} · căzute {tests['failed']}"), "quality-summary")
        else:
            tid(ui.label("Nu există rezultate Robot. Rulează scripts/test.ps1."), "quality-summary")
        suite_rows = [{"suite": name, "passed": value["passed"], "failed": value["failed"]} for name, value in tests["suites"].items()]
        tid(
            ui.table(
                columns=[
                    {"name": "suite", "label": "Suită", "field": "suite", "align": "left"},
                    {"name": "passed", "label": "Trecute", "field": "passed"},
                    {"name": "failed", "label": "Căzute", "field": "failed"},
                ],
                rows=suite_rows,
                row_key="suite",
            ).classes("w-full"),
            "quality-suites",
        )
        tid(ui.label(f"Reguli acoperite: {panel['rules_covered']} din {panel['rules_total']}"), "quality-coverage")
        tid(
            ui.table(
                columns=[
                    {"name": "rule_id", "label": "Regulă", "field": "rule_id", "align": "left"},
                    {"name": "type", "label": "Tip", "field": "type", "align": "left"},
                    {"name": "passing_tests", "label": "Teste trecute", "field": "passing_tests"},
                ],
                rows=panel["rule_coverage"],
                row_key="rule_id",
            ).classes("w-full"),
            "quality-rules",
        )
        ui.label("Agentul de testare").classes("text-subtitle1")
        with ui.row():
            seed = tid(ui.number("Seed", value=1, format="%.0f"), "quality-seed")
            customers = tid(ui.number("Clienți sintetici", value=5, format="%.0f"), "quality-customers")
        output = tid(ui.label(""), "quality-output")

        async def synthetic() -> None:
            body = await request(
                session,
                "POST",
                "/quality/synthetic",
                json={"seed": int(seed.value), "customers": int(customers.value), "transfers_per_customer": 3},
            )
            if body is not None:
                output.text = (
                    f"Generat: {len(body['customers'])} clienți, {body['transfers_completed']} transferuri finalizate, "
                    f"{body['transfers_flagged']} semnalate."
                )

        # ————————————————————————————————————————

        async def propose() -> None:
            body = await request(session, "POST", "/quality/proposals", json={"seed": int(seed.value), "count": 8})
            if body is not None:
                output.text = f"Propuneri noi: {body['scenarios_created']} scenarii, {body['api_cases_created']} cazuri API."
                await load_proposals()

        # ————————————————————————————————————————

        async def triage() -> None:
            body = await request(session, "POST", "/quality/triage")
            if body is not None:
                lines = [f"{item['test']}: {item['verdict']} ({item['reason']})" for item in body["verdicts"]]
                output.text = "\n".join(lines) if lines else "Niciun test căzut în ultima rulare."

        with ui.row():
            tid(ui.button("Generează date sintetice", on_click=synthetic), "quality-synthetic")
            tid(ui.button("Propune teste noi", on_click=propose), "quality-propose")
            tid(ui.button("Triază eșecurile", on_click=triage), "quality-triage")
        proposals_table = tid(
            ui.table(
                columns=[
                    {"name": "kind", "label": "Tip", "field": "kind"},
                    {"name": "title", "label": "Propunere", "field": "title", "align": "left"},
                ],
                rows=[],
                row_key="id",
            ).classes("w-full"),
            "quality-proposals",
        )

        async def load_proposals() -> None:
            body = await request(session, "GET", "/quality/proposals", params={"limit": 50})
            proposals_table.rows = [
                {"id": item["id"], "kind": item["kind"], "title": item["title"]} for item in (body or {}).get("items", [])
            ]
            proposals_table.update()

        await load_proposals()


# ————————————————————————————————————————

@ui.page("/admin/simulation")
async def simulation_page() -> None:
    session = frame("Simulator atacator contra apărător", ADMIN_ROLES)
    if session is None:
        return
    with ui.column().classes("w-full q-pa-md"):
        ui.label("Simulator").classes("text-h6")
        with ui.row():
            strategy = tid(ui.select(list(STRATEGIES), value=STRATEGIES[0], label="Strategie"), "sim-strategy")
            seed = tid(ui.number("Seed", value=1, format="%.0f"), "sim-seed")
            benign = tid(ui.number("Tranzacții legitime", value=10, format="%.0f"), "sim-benign")
        columns = [
            {"name": "strategy", "label": "Strategie", "field": "strategy", "align": "left"},
            {"name": "seed", "label": "Seed", "field": "seed"},
            {"name": "caught", "label": "Prinse", "field": "caught"},
            {"name": "missed", "label": "Ratate", "field": "missed"},
            {"name": "false_alarms", "label": "Alarme false", "field": "false_alarms"},
            {"name": "steps", "label": "Pași până la detecție", "field": "steps"},
            {"name": "seconds", "label": "Secunde până la detecție", "field": "seconds"},
        ]
        table = tid(ui.table(columns=columns, rows=[], row_key="id").classes("w-full"), "sim-table")
        chart = tid(
            ui.echart(
                {
                    "tooltip": {},
                    "legend": {},
                    "xAxis": {"type": "category", "data": []},
                    "yAxis": {"type": "value"},
                    "series": [],
                }
            ).classes("w-full h-64"),
            "sim-chart",
        )

        async def load() -> None:
            body = await request(session, "GET", "/simulation/runs", params={"limit": 20})
            runs = list(reversed((body or {}).get("items", [])))
            table.rows = [
                {
                    "id": item["id"],
                    "strategy": item["strategy"],
                    "seed": item["seed"],
                    "caught": item["metrics"]["malicious_caught"],
                    "missed": item["metrics"]["malicious_missed"],
                    "false_alarms": item["metrics"]["false_alarms"],
                    "steps": item["metrics"]["steps_to_detection"],
                    "seconds": item["metrics"]["seconds_to_detection"],
                }
                for item in reversed(runs)
            ]
            table.update()
            chart.options["xAxis"]["data"] = [f"{item['strategy']} #{item['seed']}" for item in runs]
            chart.options["series"] = [
                {"type": "bar", "name": "Prinse", "data": [item["metrics"]["malicious_caught"] for item in runs]},
                {"type": "bar", "name": "Ratate", "data": [item["metrics"]["malicious_missed"] for item in runs]},
                {"type": "bar", "name": "Alarme false", "data": [item["metrics"]["false_alarms"] for item in runs]},
            ]
            chart.update()

        # ————————————————————————————————————————

        async def run() -> None:
            ui.notify("Simularea rulează.")
            body = await request(
                session,
                "POST",
                "/simulation/runs",
                json={"strategy": strategy.value, "seed": int(seed.value), "benign_count": int(benign.value)},
            )
            if body is not None:
                ui.notify("Simulare încheiată.")
                await load()

        tid(ui.button("Pornește simularea", on_click=run), "sim-run")
        await load()
