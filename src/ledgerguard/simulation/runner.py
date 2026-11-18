from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from ledgerguard.simulation.metrics import StepOutcome
from ledgerguard.simulation.strategies import AccountSpec, Scenario

Advance = Callable[[int], None]


@dataclass(frozen=True)
class SimResponse:
    status: int
    body: Any


# ————————————————————————————————————————

class SimClient(Protocol):
    def request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        json: Any = None,
        headers: dict[str, str] | None = None,
    ) -> SimResponse: ...


# ————————————————————————————————————————

class HttpxSimClient:
    def __init__(self, client: Any, prefix: str = "/api/v1") -> None:
        self._client = client
        self._prefix = prefix

    # ————————————————————————————————————————

    def request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        json: Any = None,
        headers: dict[str, str] | None = None,
    ) -> SimResponse:
        merged = dict(headers or {})
        if token:
            merged["Authorization"] = f"Bearer {token}"
        response = self._client.request(method, f"{self._prefix}{path}", json=json, headers=merged)
        try:
            body = response.json()
        except ValueError:
            body = None
        return SimResponse(response.status_code, body)


# ————————————————————————————————————————

def _expect(response: SimResponse, statuses: tuple[int, ...], action: str) -> Any:
    if response.status not in statuses:
        raise RuntimeError(f"simulation step failed ({action}): {response.status} {response.body}")
    return response.body


# ————————————————————————————————————————

def _prepare_owner(client: SimClient, admin_token: str, tag: str, owner: str) -> str:
    password = secrets.token_urlsafe(14)
    email = f"sim-{tag}-{owner}@sim.test"
    _expect(
        client.request("POST", "/customers", token=admin_token, json={"name": f"Sim {owner}", "email": email, "password": password}),
        (201,),
        f"customer {owner}",
    )
    login = _expect(client.request("POST", "/auth/login", json={"email": email, "password": password}), (200,), "login")
    return str(login["access_token"])


# ————————————————————————————————————————

def _open_account(
    client: SimClient, admin_token: str, tag: str, spec: AccountSpec, tokens: dict[str, str]
) -> str:
    created = _expect(
        client.request("POST", "/accounts", token=tokens[spec.owner], json={"currency": "RON", "name": spec.key}),
        (201,),
        f"account {spec.key}",
    )
    account_id = str(created["id"])
    if spec.initial_minor > 0:
        _expect(
            client.request(
                "POST",
                f"/accounts/{account_id}/deposit",
                token=admin_token,
                json={"amount_minor": spec.initial_minor, "description": "Fonduri simulare"},
                headers={"Idempotency-Key": f"sim-{tag}-deposit-{spec.key}"},
            ),
            (201,),
            f"deposit {spec.key}",
        )
    return account_id


# ————————————————————————————————————————

def run_scenario(
    client: SimClient, admin_token: str, scenario: Scenario, tag: str, advance: Advance | None
) -> list[StepOutcome]:
    owners = sorted({spec.owner for spec in scenario.accounts})
    tokens = {owner: _prepare_owner(client, admin_token, tag, owner) for owner in owners}
    account_ids: dict[str, str] = {}
    for spec in scenario.accounts:
        if spec.established:
            account_ids[spec.key] = _open_account(client, admin_token, tag, spec, tokens)
    if advance is not None:
        advance(scenario.warmup_seconds)
    for spec in scenario.accounts:
        if not spec.established:
            account_ids[spec.key] = _open_account(client, admin_token, tag, spec, tokens)
    owner_of = {spec.key: spec.owner for spec in scenario.accounts}
    outcomes: list[StepOutcome] = []
    elapsed = 0
    for step in scenario.steps:
        if advance is not None and step.offset_seconds > elapsed:
            advance(step.offset_seconds - elapsed)
        elapsed = max(elapsed, step.offset_seconds)
        response = client.request(
            "POST",
            "/transfers",
            token=tokens[owner_of[step.from_key]],
            json={
                "from_account_id": account_ids[step.from_key],
                "to_account_id": account_ids[step.to_key],
                "amount_minor": step.amount_minor,
                "description": f"sim {step.label}",
            },
            headers={"Idempotency-Key": f"sim-{tag}-step-{step.index}"},
        )
        if response.status == 201 and isinstance(response.body, dict):
            state = str(response.body.get("state"))
        else:
            code = response.body.get("error", {}).get("code", "unknown") if isinstance(response.body, dict) else "unknown"
            state = f"error:{code}"
        outcomes.append(StepOutcome(step.index, step.label, step.malicious, step.offset_seconds, state))
    return outcomes
