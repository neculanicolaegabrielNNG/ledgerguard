from __future__ import annotations

from importlib import import_module

from fastapi import FastAPI
from nicegui import ui

from ledgerguard.ui.api_client import HOLDER, UiApi

PAGE_MODULES = (
    "ledgerguard.ui.pages_customer",
    "ledgerguard.ui.pages_compliance",
    "ledgerguard.ui.pages_admin",
)


def mount_ui(app: FastAPI) -> None:
    HOLDER["api"] = UiApi(app)
    for name in PAGE_MODULES:
        import_module(name)
    ui.run_with(app, storage_secret=app.state.settings.ui_storage_secret)
