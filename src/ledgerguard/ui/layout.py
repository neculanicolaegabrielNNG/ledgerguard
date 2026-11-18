from __future__ import annotations

from typing import Any

from nicegui import app as nicegui_app
from nicegui import ui

from ledgerguard.ui.api_client import current_session
from ledgerguard.ui.session import Session

MENU: dict[str, list[tuple[str, str, str]]] = {
    "customer": [
        ("Conturi", "/customer", "nav-accounts"),
        ("Istoric", "/customer/history", "nav-history"),
        ("Transfer", "/customer/transfer", "nav-transfer"),
        ("Asistent", "/customer/chat", "nav-chat"),
    ],
    "compliance": [
        ("Coadă de risc", "/compliance", "nav-queue"),
        ("Graf rețea", "/compliance/graph", "nav-graph"),
        ("Călătorie în timp", "/compliance/timetravel", "nav-timetravel"),
    ],
    "admin": [
        ("Coadă de risc", "/compliance", "nav-queue"),
        ("Graf rețea", "/compliance/graph", "nav-graph"),
        ("Călătorie în timp", "/compliance/timetravel", "nav-timetravel"),
        ("Reguli", "/admin/rules", "nav-rules"),
        ("Audit", "/admin/audit", "nav-audit"),
        ("Cursuri valutare", "/admin/fx", "nav-fx"),
        ("Calitate", "/admin/quality", "nav-quality"),
        ("Simulator", "/admin/simulation", "nav-simulation"),
    ],
}


def tid(element: Any, name: str) -> Any:
    element.props(f"data-testid={name}")
    return element


# ————————————————————————————————————————

def logout() -> None:
    nicegui_app.storage.user.clear()
    ui.navigate.to("/login")


# ————————————————————————————————————————

def frame(title: str, roles: tuple[str, ...]) -> Session | None:
    session = current_session()
    if session is None or session.role not in roles:
        ui.navigate.to("/login")
        return None
    with ui.header().classes("items-center justify-between"):
        tid(ui.label(f"LedgerGuard · {title}").classes("text-h6"), "page-title")
        with ui.row().classes("items-center"):
            tid(ui.label(session.email), "session-email")
            tid(ui.button("Ieșire", on_click=logout).props("flat color=white"), "logout")
    with ui.left_drawer().classes("bg-grey-2"):
        for label, path, test_id in MENU[session.role]:
            tid(ui.link(label, path).classes("block q-pa-sm"), test_id)
    return session
