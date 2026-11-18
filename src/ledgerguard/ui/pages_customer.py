from __future__ import annotations

from collections import defaultdict
from typing import Any

from nicegui import app as nicegui_app
from nicegui import ui

from ledgerguard.common.money import format_minor, parse_amount_minor
from ledgerguard.ui.api_client import api, current_session, new_key, request
from ledgerguard.ui.layout import frame, tid
from ledgerguard.ui.session import STATE_LABELS

RESULT_TEXT = {
    "completed": "Transfer finalizat.",
    "under_review": "Transferul a fost trimis spre revizuire.",
    "blocked": "Transferul a fost blocat.",
}


@ui.page("/")
async def index() -> None:
    session = current_session()
    if session is None:
        ui.navigate.to("/login")
        return
    target = {"customer": "/customer", "compliance": "/compliance", "admin": "/admin/rules"}[session.role]
    ui.navigate.to(target)


# ————————————————————————————————————————

@ui.page("/login")
async def login_page() -> None:
    with ui.card().classes("absolute-center w-96"):
        ui.label("Autentificare").classes("text-h5")
        email = tid(ui.input("Email"), "login-email").classes("w-full")
        password = tid(ui.input("Parolă", password=True, password_toggle_button=True), "login-password").classes("w-full")
        message = tid(ui.label(""), "login-error").classes("text-negative")

        async def submit() -> None:
            status, body = await api().call("POST", "/auth/login", json={"email": email.value, "password": password.value})
            if status != 200:
                message.text = body["error"]["message"] if isinstance(body, dict) and "error" in body else "Autentificare eșuată."
                return
            store = nicegui_app.storage.user
            store.update(
                token=body["access_token"], role=body["role"], email=email.value, customer_id=body["customer_id"]
            )
            ui.navigate.to("/")

        tid(ui.button("Intră", on_click=submit), "login-submit")


# ————————————————————————————————————————

def _volume_chart(transfers: list[dict[str, Any]]) -> dict[str, Any]:
    per_day: dict[str, int] = defaultdict(int)
    for item in transfers:
        if item["state"] == "completed":
            per_day[item["created_at"][:10]] += item["amount_ron_minor"] // 100
    days = sorted(per_day)
    return {
        "tooltip": {"trigger": "axis"},
        "xAxis": {"type": "category", "data": days},
        "yAxis": {"type": "value", "name": "RON"},
        "series": [{"type": "bar", "name": "Volum (RON)", "data": [per_day[day] for day in days]}],
    }


# ————————————————————————————————————————

@ui.page("/customer")
async def accounts_page() -> None:
    session = frame("Conturi", ("customer",))
    if session is None:
        return
    accounts = await request(session, "GET", "/accounts")
    transfers = await request(session, "GET", "/transfers", params={"limit": 200})
    rates = await request(session, "GET", "/fx/rates")
    with ui.column().classes("w-full q-pa-md"):
        ui.label("Conturile mele").classes("text-h6")
        rows = [
            {
                "id": item["id"],
                "name": item["name"],
                "currency": item["currency"],
                "balance": format_minor(item["balance_minor"], item["currency"]),
            }
            for item in (accounts or {}).get("items", [])
        ]
        columns = [
            {"name": "id", "label": "Identificator", "field": "id", "align": "left"},
            {"name": "name", "label": "Denumire", "field": "name", "align": "left"},
            {"name": "currency", "label": "Monedă", "field": "currency"},
            {"name": "balance", "label": "Sold", "field": "balance"},
        ]
        tid(ui.table(columns=columns, rows=rows, row_key="id").classes("w-full"), "accounts-table")
        ui.label("Volum transferuri finalizate").classes("text-subtitle1")
        tid(ui.echart(_volume_chart((transfers or {}).get("items", []))).classes("w-full h-64"), "volume-chart")
        ui.label("Cursuri valutare").classes("text-subtitle1")
        rate_rows = [
            {"currency": item["currency"], "rate": item["rate"], "status": "actual" if item["status"] == "fresh" else "expirat"}
            for item in (rates or {}).get("items", [])
        ]
        rate_columns = [
            {"name": "currency", "label": "Monedă", "field": "currency"},
            {"name": "rate", "label": "Curs RON", "field": "rate"},
            {"name": "status", "label": "Stare", "field": "status"},
        ]
        tid(ui.table(columns=rate_columns, rows=rate_rows, row_key="currency"), "rates-table")


# ————————————————————————————————————————

@ui.page("/customer/history")
async def history_page() -> None:
    session = frame("Istoric", ("customer",))
    if session is None:
        return
    accounts = await request(session, "GET", "/accounts")
    options = {"": "Toate conturile"}
    options.update({item["id"]: f"{item['name']} ({item['currency']})" for item in (accounts or {}).get("items", [])})
    states = {"": "Toate stările", **STATE_LABELS}
    with ui.column().classes("w-full q-pa-md"):
        with ui.row():
            account_filter = tid(ui.select(options, value="", label="Cont"), "history-account")
            state_filter = tid(ui.select(states, value="", label="Stare"), "history-state")
            date_from = tid(ui.input("De la (YYYY-MM-DD)"), "history-from")
            date_to = tid(ui.input("Până la (YYYY-MM-DD)"), "history-to")
        columns = [
            {"name": "created_at", "label": "Data", "field": "created_at", "align": "left"},
            {"name": "from", "label": "Din", "field": "from", "align": "left"},
            {"name": "to", "label": "Către", "field": "to", "align": "left"},
            {"name": "amount", "label": "Sumă", "field": "amount"},
            {"name": "state", "label": "Stare", "field": "state"},
            {"name": "description", "label": "Descriere", "field": "description", "align": "left"},
        ]
        table = tid(ui.table(columns=columns, rows=[], row_key="id").classes("w-full"), "history-table")

        async def load() -> None:
            body = await request(
                session,
                "GET",
                "/transfers",
                params={
                    "account_id": account_filter.value,
                    "state": state_filter.value,
                    "date_from": date_from.value,
                    "date_to": date_to.value,
                    "limit": 100,
                },
            )
            table.rows = [
                {
                    "id": item["id"],
                    "created_at": item["created_at"],
                    "from": item["from_account_id"],
                    "to": item["to_account_id"],
                    "amount": format_minor(item["amount_minor"], item["currency"]),
                    "state": STATE_LABELS.get(item["state"], item["state"]),
                    "description": item["description"],
                }
                for item in (body or {}).get("items", [])
            ]
            table.update()

        tid(ui.button("Filtrează", on_click=load), "history-apply")
        await load()


# ————————————————————————————————————————

@ui.page("/customer/transfer")
async def transfer_page() -> None:
    session = frame("Transfer", ("customer",))
    if session is None:
        return
    accounts = await request(session, "GET", "/accounts")
    items = (accounts or {}).get("items", [])
    options = {
        item["id"]: f"{item['name']} · {format_minor(item['balance_minor'], item['currency'])}" for item in items
    }
    with ui.column().classes("w-full q-pa-md max-w-xl"):
        ui.label("Transfer nou").classes("text-h6")
        source = tid(ui.select(options, label="Din contul"), "transfer-from").classes("w-full")
        target = tid(ui.input("Contul destinatar (identificator)"), "transfer-to").classes("w-full")
        amount = tid(ui.input("Sumă (ex. 125.50)"), "transfer-amount").classes("w-full")
        description = tid(ui.input("Descriere"), "transfer-description").classes("w-full")
        result = tid(ui.label(""), "transfer-result")

        async def review() -> None:
            if not source.value or not target.value or not amount.value:
                ui.notify("Completează contul sursă, destinatarul și suma.", type="warning")
                return
            try:
                minor = parse_amount_minor(amount.value)
            except ValueError:
                ui.notify("Suma este invalidă.", type="negative")
                return
            quote = await request(
                session,
                "GET",
                "/transfers/quote",
                params={"from_account_id": source.value, "to_account_id": target.value.strip(), "amount_minor": minor},
            )
            if quote is None:
                return
            with ui.dialog() as dialog, ui.card():
                ui.label("Confirmă transferul").classes("text-h6")
                ui.label(f"Se debitează {format_minor(quote['source_amount_minor'], quote['source_currency'])}")
                ui.label(f"Se creditează {format_minor(quote['target_amount_minor'], quote['target_currency'])}")
                with ui.row():
                    tid(ui.button("Anulează", on_click=lambda: dialog.submit(False)), "transfer-cancel")
                    tid(ui.button("Confirmă", on_click=lambda: dialog.submit(True)), "transfer-confirm")
            if not await dialog:
                return
            body = await request(
                session,
                "POST",
                "/transfers",
                json={
                    "from_account_id": source.value,
                    "to_account_id": target.value.strip(),
                    "amount_minor": minor,
                    "description": description.value or "",
                },
                key=new_key(),
            )
            if body is not None:
                result.text = RESULT_TEXT.get(body["state"], body["state"])

        tid(ui.button("Verifică și confirmă", on_click=review), "transfer-review")


# ————————————————————————————————————————

@ui.page("/customer/chat")
async def chat_page() -> None:
    session = frame("Asistent", ("customer",))
    if session is None:
        return
    with ui.column().classes("w-full q-pa-md max-w-2xl"):
        ui.label("Asistent client").classes("text-h6")
        log = tid(ui.column().classes("w-full"), "chat-log")
        entry = tid(ui.input("Scrie un mesaj").classes("w-full"), "chat-input")

        async def send() -> None:
            message = entry.value
            if not message:
                return
            entry.value = ""
            with log:
                ui.chat_message(message, name="Tu", sent=True)
            reply = await request(session, "POST", "/assistant/chat", json={"message": message})
            if reply is None:
                return
            with log:
                ui.chat_message(reply["text"], name="Asistent")
                proposal = reply.get("proposal")
                if proposal:
                    action_id = proposal["action_id"]
                    with ui.row():

                        async def confirm(action_id: str = action_id) -> None:
                            body = await request(
                                session, "POST", f"/assistant/actions/{action_id}/confirm", key=new_key()
                            )
                            if body is not None:
                                ui.notify(RESULT_TEXT.get(body["transfer"]["state"], "Operațiune înregistrată."))

                        # ————————————————————————————————————————

                        async def reject(action_id: str = action_id) -> None:
                            if await request(session, "POST", f"/assistant/actions/{action_id}/reject") is not None:
                                ui.notify("Operațiunea a fost respinsă.")

                        tid(ui.button("Confirmă", on_click=confirm), "chat-confirm")
                        tid(ui.button("Respinge", on_click=reject), "chat-reject")

        tid(ui.button("Trimite", on_click=send), "chat-send")
