from __future__ import annotations

import json
from typing import Any

from nicegui import ui

from ledgerguard.common.money import format_minor
from ledgerguard.ui.api_client import new_key, request
from ledgerguard.ui.layout import frame, tid
from ledgerguard.ui.session import STATE_LABELS, risk_color, risk_label

ACTION_LABELS = {"approve": "Aprobă", "block": "Blochează", "escalate": "Escaladează"}
RECOMMENDATION_LABELS = {"approve": "aprobare", "block": "blocare", "escalate": "escaladare"}


@ui.page("/compliance")
async def queue_page() -> None:
    session = frame("Coadă de conformitate", ("compliance", "admin"))
    if session is None:
        return
    body = await request(session, "GET", "/fraud/cases", params={"limit": 100})
    rows = [
        {
            "id": item["id"],
            "transfer_id": item["transfer_id"],
            "score": item["score"],
            "risk": risk_label(item["score"]),
            "color": risk_color(item["score"]),
            "status": {"open": "deschis", "escalated": "escaladat"}.get(item["status"], item["status"]),
            "opened_at": item["opened_at"],
        }
        for item in (body or {}).get("items", [])
    ]
    columns = [
        {"name": "id", "label": "Caz", "field": "id", "align": "left"},
        {"name": "transfer_id", "label": "Transfer", "field": "transfer_id", "align": "left"},
        {"name": "score", "label": "Scor", "field": "score", "sortable": True},
        {"name": "risk", "label": "Risc", "field": "risk"},
        {"name": "status", "label": "Stare", "field": "status"},
        {"name": "opened_at", "label": "Deschis la", "field": "opened_at", "align": "left"},
    ]
    with ui.column().classes("w-full q-pa-md"):
        ui.label("Cazuri în așteptare, sortate după risc").classes("text-h6")
        table = tid(ui.table(columns=columns, rows=rows, row_key="id").classes("w-full"), "queue-table")
        table.add_slot(
            "body-cell-risk",
            '<q-td :props="props"><q-badge :color="props.row.color">{{ props.value }}</q-badge></q-td>',
        )
        table.on("rowClick", lambda event: ui.navigate.to(f"/compliance/case/{event.args[1]['id']}"))


# ————————————————————————————————————————

@ui.page("/compliance/case/{case_id}")
async def case_page(case_id: str) -> None:
    session = frame("Caz de conformitate", ("compliance", "admin"))
    if session is None:
        return
    case = await request(session, "GET", f"/fraud/cases/{case_id}")
    if case is None:
        return
    transfer = case["transfer"]
    evaluation = case.get("evaluation") or {}
    with ui.column().classes("w-full q-pa-md"):
        with ui.row().classes("items-center"):
            ui.label(f"Caz {case['id']}").classes("text-h6")
            tid(ui.badge(f"scor {case['score']} · {risk_label(case['score'])}", color=risk_color(case["score"])), "case-score")
            tid(ui.label(f"stare: {case['status']}"), "case-status")
        ui.label(
            f"Transfer {transfer['id']}: {format_minor(transfer['amount_minor'], transfer['currency'])} "
            f"din {transfer['from_account_id']} către {transfer['to_account_id']} · "
            f"{STATE_LABELS.get(transfer['state'], transfer['state'])}"
        )
        tid(ui.label(f"Descriere (date introduse de client): {transfer['description']}"), "case-description")
        ui.label("Reguli evaluate").classes("text-subtitle1")
        hit_rows = [
            {
                "rule": f"{item['rule_id']} v{item['rule_version']}",
                "triggered": "da" if item["triggered"] else "nu",
                "score": item["score"],
                "measured": json.dumps(item["measured"], ensure_ascii=False),
                "threshold": json.dumps(item["threshold"], ensure_ascii=False),
            }
            for item in evaluation.get("results", [])
        ]
        hit_columns = [
            {"name": "rule", "label": "Regulă", "field": "rule", "align": "left"},
            {"name": "triggered", "label": "Declanșată", "field": "triggered"},
            {"name": "score", "label": "Scor", "field": "score"},
            {"name": "measured", "label": "Valori măsurate", "field": "measured", "align": "left"},
            {"name": "threshold", "label": "Praguri", "field": "threshold", "align": "left"},
        ]
        tid(ui.table(columns=hit_columns, rows=hit_rows, row_key="rule").classes("w-full"), "case-rules")
        report_box = tid(ui.column().classes("w-full"), "case-report")

        def render_report(report: dict[str, Any] | None) -> None:
            report_box.clear()
            with report_box:
                ui.label("Raportul agentului").classes("text-subtitle1")
                if not report:
                    ui.label("Nu există încă un raport.")
                    return
                label = RECOMMENDATION_LABELS.get(report["recommendation"], report["recommendation"])
                tid(ui.label(f"Recomandare: {label} · încredere {int(report['confidence'] * 100)}% · motor {report['engine']}"), "report-recommendation")
                for line in report["rationale"]:
                    ui.label(f"• {line}")
                for item in report["evidence"]:
                    ui.label(f"{item['ref']}: {item['detail']}").classes("text-caption")
                for flag in report.get("flags", []):
                    ui.badge(flag, color="orange")

        render_report(case.get("agent_report"))

        async def analyze() -> None:
            report = await request(session, "POST", f"/fraud/cases/{case_id}/analyze")
            if report is not None:
                render_report(report)

        tid(ui.button("Analizează cu agentul", on_click=analyze), "case-analyze")
        comment = tid(ui.input("Comentariu (obligatoriu)"), "case-comment").classes("w-full")
        status_label = tid(ui.label(""), "case-result")

        async def decide(action: str) -> None:
            if len(comment.value or "") < 3:
                ui.notify("Comentariul este obligatoriu.", type="warning")
                return
            body = await request(
                session,
                "POST",
                f"/fraud/cases/{case_id}/decision",
                json={"action": action, "comment": comment.value},
                key=new_key(),
            )
            if body is not None:
                status_label.text = f"Decizie înregistrată: {ACTION_LABELS[action]}. Stare transfer: {STATE_LABELS.get(body['transfer']['state'])}"

        with ui.row():
            tid(ui.button("Aprobă", on_click=lambda: decide("approve"), color="positive"), "case-approve")
            tid(ui.button("Blochează", on_click=lambda: decide("block"), color="negative"), "case-block")
            tid(ui.button("Escaladează", on_click=lambda: decide("escalate"), color="warning"), "case-escalate")


# ————————————————————————————————————————

@ui.page("/compliance/graph")
async def graph_page() -> None:
    session = frame("Graf de rețea", ("compliance", "admin"))
    if session is None:
        return
    graph = await request(session, "GET", "/fraud/graph", params={"days": 30})
    graph = graph or {"nodes": [], "edges": [], "clusters": []}
    nodes = [
        {
            "id": item["id"],
            "name": item["id"][-8:],
            "symbolSize": 22 if item["suspicious"] else 14,
            "itemStyle": {"color": "#c62828" if item["suspicious"] else "#78909c"},
        }
        for item in graph["nodes"]
    ]
    links = [
        {
            "source": item["source"],
            "target": item["target"],
            "value": item["count"],
            "lineStyle": {"color": "#c62828" if item["flagged"] else "#90a4ae", "width": 2},
        }
        for item in graph["edges"]
    ]
    options = {
        "tooltip": {},
        "series": [
            {
                "type": "graph",
                "layout": "force",
                "roam": True,
                "label": {"show": True},
                "edgeSymbol": ["none", "arrow"],
                "force": {"repulsion": 200, "edgeLength": 90},
                "data": nodes,
                "links": links,
            }
        ],
    }
    with ui.column().classes("w-full q-pa-md"):
        ui.label("Fluxuri de bani între conturi (ultimele 30 de zile)").classes("text-h6")
        tid(ui.echart(options).classes("w-full h-96"), "network-graph")
        suspicious = [item for item in graph["clusters"]]
        tid(ui.label(f"Clustere suspecte: {len(suspicious)}"), "cluster-count")
        for cluster in suspicious:
            ui.label(" · ".join(item[-8:] for item in cluster)).classes("text-negative")


# ————————————————————————————————————————

@ui.page("/compliance/timetravel")
async def timetravel_page() -> None:
    session = frame("Călătorie în timp", ("compliance", "admin"))
    if session is None:
        return
    with ui.column().classes("w-full q-pa-md"):
        ui.label("Starea sistemului la un moment din trecut").classes("text-h6")
        moment = tid(ui.input("Moment (ISO 8601, ex. 2026-11-18T10:00:00Z)"), "timetravel-at").classes("w-96")
        output = ui.column().classes("w-full")

        async def load() -> None:
            body = await request(session, "GET", "/timetravel", params={"at": moment.value})
            output.clear()
            if body is None:
                return
            with output:
                ui.label("Solduri").classes("text-subtitle1")
                balances = [
                    {
                        "account": item["account_id"],
                        "kind": item["kind"],
                        "balance": format_minor(item["balance_minor"], item["currency"]),
                    }
                    for item in body["balances"]
                ]
                tid(
                    ui.table(
                        columns=[
                            {"name": "account", "label": "Cont", "field": "account", "align": "left"},
                            {"name": "kind", "label": "Tip", "field": "kind"},
                            {"name": "balance", "label": "Sold", "field": "balance"},
                        ],
                        rows=balances,
                        row_key="account",
                    ).classes("w-full"),
                    "timetravel-balances",
                )
                ui.label("Reguli active").classes("text-subtitle1")
                rules = [{"rule": f"{item['id']} v{item['version']}", "effect": item["effect"]} for item in body["rules"]]
                tid(
                    ui.table(
                        columns=[
                            {"name": "rule", "label": "Regulă", "field": "rule", "align": "left"},
                            {"name": "effect", "label": "Efect", "field": "effect"},
                        ],
                        rows=rules,
                        row_key="rule",
                    ),
                    "timetravel-rules",
                )
                ui.label("Decizii").classes("text-subtitle1")
                decisions = [
                    {
                        "transfer": item["transfer_id"],
                        "state": STATE_LABELS.get(item["state_at"], item["state_at"]),
                        "score": item["score"],
                        "triggered": ", ".join(item["triggered"]),
                    }
                    for item in body["decisions"]
                ]
                tid(
                    ui.table(
                        columns=[
                            {"name": "transfer", "label": "Transfer", "field": "transfer", "align": "left"},
                            {"name": "state", "label": "Stare", "field": "state"},
                            {"name": "score", "label": "Scor", "field": "score"},
                            {"name": "triggered", "label": "Reguli declanșate", "field": "triggered", "align": "left"},
                        ],
                        rows=decisions,
                        row_key="transfer",
                    ).classes("w-full"),
                    "timetravel-decisions",
                )

        tid(ui.button("Reconstruiește", on_click=load), "timetravel-load")
