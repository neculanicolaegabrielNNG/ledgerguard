from __future__ import annotations

import uuid
from typing import Any

import httpx
from fastapi import FastAPI
from nicegui import app as nicegui_app
from nicegui import ui

from ledgerguard.ui.session import Session

HOLDER: dict[str, "UiApi"] = {}


class UiApi:
    def __init__(self, app: FastAPI) -> None:
        self._client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://ledgerguard.local", timeout=60.0
        )

    # ————————————————————————————————————————

    async def call(
        self,
        method: str,
        path: str,
        token: str | None = None,
        json: Any = None,
        params: dict[str, Any] | None = None,
        key: str | None = None,
    ) -> tuple[int, Any]:
        headers: dict[str, str] = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if key:
            headers["Idempotency-Key"] = key
        clean = {name: value for name, value in (params or {}).items() if value not in (None, "")}
        response = await self._client.request(method, f"/api/v1{path}", json=json, params=clean, headers=headers)
        try:
            body = response.json() if response.content else None
        except ValueError:
            body = None
        return response.status_code, body


# ————————————————————————————————————————

def api() -> UiApi:
    return HOLDER["api"]


# ————————————————————————————————————————

def new_key() -> str:
    return uuid.uuid4().hex


# ————————————————————————————————————————

def current_session() -> Session | None:
    store = nicegui_app.storage.user
    token = store.get("token")
    if not token:
        return None
    return Session(
        token=str(token),
        role=str(store.get("role", "")),
        email=str(store.get("email", "")),
        customer_id=store.get("customer_id"),
    )


# ————————————————————————————————————————

async def request(
    session: Session,
    method: str,
    path: str,
    json: Any = None,
    params: dict[str, Any] | None = None,
    key: str | None = None,
    quiet: bool = False,
) -> Any | None:
    status, body = await api().call(method, path, session.token, json, params, key)
    if status >= 400:
        if status == 401:
            nicegui_app.storage.user.clear()
            ui.navigate.to("/login")
            return None
        if not quiet:
            message = body["error"]["message"] if isinstance(body, dict) and "error" in body else f"Eroare {status}"
            ui.notify(message, type="negative")
        return None
    return body if body is not None else {}
