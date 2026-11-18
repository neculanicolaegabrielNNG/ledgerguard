from __future__ import annotations

import json as jsonlib
import secrets
import shutil
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from robot.api import logger

from ledgerguard.app.main import create_app
from ledgerguard.app.wiring import make_ctx
from ledgerguard.app.workers import maintenance_once
from ledgerguard.auth import service as auth
from ledgerguard.common.clock import FixedClock, to_iso
from ledgerguard.common.context import Actor
from ledgerguard.common.money import parse_amount_minor
from ledgerguard.common.settings import PROJECT_ROOT, Settings

START = datetime(2026, 3, 2, 9, 0, tzinfo=UTC)
INTEGER_SETTINGS = {
    "rate_limit_login",
    "rate_limit_money",
    "fx_max_age_seconds",
    "fx_max_change_bps",
    "fx_spread_bps",
    "fx_seed",
    "fx_volatility_bps",
    "fraud_review_score",
    "fraud_block_score",
    "assistant_max_amount_ron_minor",
    "assistant_action_ttl_seconds",
}


class ApiLibrary:
    ROBOT_LIBRARY_SCOPE = "GLOBAL"

    def __init__(self) -> None:
        self._directory: Path | None = None
        self._client: TestClient | None = None
        self._clock: FixedClock | None = None
        self._settings: Settings | None = None
        self.app: Any = None
        self.admin_token = ""
        self._compliance_token = ""

    # ————————————————————————————————————————

    def start_system(self, **overrides: str) -> str:
        self.stop_system()
        self._directory = Path(tempfile.mkdtemp(prefix="ledgerguard-"))
        values: dict[str, Any] = {
            "db_path": self._directory / "test.db",
            "data_dir": self._directory,
            "reports_dir": self._directory / "reports",
            "jwt_secret": secrets.token_hex(16),
            "password_iterations": 1_000,
            "worker_enabled": False,
            "ui_enabled": False,
            "anthropic_api_key": None,
            "rate_limit_login": 1_000,
            "rate_limit_money": 10_000,
        }
        for name, raw in overrides.items():
            values[name] = int(raw) if name in INTEGER_SETTINGS else raw
        self._settings = Settings.from_env().with_overrides(**values)
        self._clock = FixedClock(START)
        self.app = create_app(self._settings, self._clock, with_ui=False)
        self._client = TestClient(self.app, raise_server_exceptions=False)
        password = secrets.token_urlsafe(12)
        ctx = make_ctx(self._settings, self._clock, "robot-setup", Actor.system("robot"))
        try:
            auth.create_user(ctx, "admin@test.local", password, "admin", None)
            auth.create_user(ctx, "compliance@test.local", password, "compliance", None)
        finally:
            ctx.conn.close()
        self.admin_token = self.login("admin@test.local", password)
        self._compliance_token = self.login("compliance@test.local", password)
        return str(self._settings.db_path)

    # ————————————————————————————————————————

    def stop_system(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
        if self._directory is not None:
            shutil.rmtree(self._directory, ignore_errors=True)
            self._directory = None

    # ————————————————————————————————————————

    def compliance_token(self) -> str:
        return self._compliance_token

    # ————————————————————————————————————————

    def login(self, email: str, password: str) -> str:
        response = self.api_request("POST", "/auth/login", json={"email": email, "password": password})
        if response["status"] != 200:
            raise AssertionError(f"login failed: {response}")
        return str(response["body"]["access_token"])

    # ————————————————————————————————————————

    def api_request(
        self,
        method: str,
        path: str,
        token: str | None = None,
        json: Any = None,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        assert self._client is not None, "system not started"
        merged = dict(headers or {})
        if token:
            merged["Authorization"] = f"Bearer {token}"
        response = self._client.request(
            method.upper(), f"/api/v1{path}", json=json, headers=merged, params=params
        )
        try:
            body = response.json() if response.content else None
        except ValueError:
            body = None
        return {
            "status": response.status_code,
            "body": body,
            "headers": {name.lower(): value for name, value in response.headers.items()},
        }

    # ————————————————————————————————————————

    def run_maintenance(self) -> None:
        maintenance_once(self.app)

    # ————————————————————————————————————————

    def write_robot_output(self, label: str, *specs: str) -> str:
        assert self._settings is not None
        folder = self._settings.reports_dir / "robot"
        folder.mkdir(parents=True, exist_ok=True)
        tests: list[str] = []
        for spec in specs:
            suite, name, status, message, tags = (spec.split("|") + ["", "", "", "", ""])[:5]
            tag_xml = "".join(f"<tag>{tag}</tag>" for tag in tags.split(",") if tag)
            tests.append(
                f'<test id="s1-t{len(tests) + 1}" name="{name}">{tag_xml}'
                f'<status status="{status}">{message}</status></test>'
            )
        suite_name = (specs[0].split("|")[0] if specs else "Suite")
        document = (
            f'<?xml version="1.0" encoding="UTF-8"?><robot generated="{label}">'
            f'<suite id="s1" name="{suite_name}">{"".join(tests)}<status status="PASS"/></suite></robot>'
        )
        path = folder / "output.xml"
        path.write_text(document, encoding="utf-8")
        return str(path)

    # ————————————————————————————————————————

    def admin_request(
        self,
        method: str,
        path: str,
        json: Any = None,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.api_request(method, path, self.admin_token, json, headers, params)

    # ————————————————————————————————————————

    def compliance_request(
        self,
        method: str,
        path: str,
        json: Any = None,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.api_request(method, path, self._compliance_token, json, headers, params)

    # ————————————————————————————————————————

    def decide_case(self, case_id: str, action: str, comment: str = "Verificat manual") -> dict[str, Any]:
        return self.compliance_request(
            "POST",
            f"/fraud/cases/{case_id}/decision",
            {"action": action, "comment": comment},
            {"Idempotency-Key": self.new_key()},
        )

    # ————————————————————————————————————————

    def raw_request(self, method: str, path: str) -> dict[str, Any]:
        assert self._client is not None, "system not started"
        response = self._client.request(method.upper(), path)
        return {"status": response.status_code, "body": response.json() if response.content else None}

    # ————————————————————————————————————————

    def new_key(self) -> str:
        return f"rf-{secrets.token_hex(10)}"

    # ————————————————————————————————————————

    def minor(self, text: str) -> int:
        return parse_amount_minor(text)

    # ————————————————————————————————————————

    def create_funded_customer(
        self, currency: str = "RON", balance_minor: int = 1_000_000, name: str | None = None
    ) -> dict[str, Any]:
        label = name or f"Client {secrets.token_hex(3)}"
        email = f"{secrets.token_hex(5)}@test.local"
        password = secrets.token_urlsafe(12)
        created = self.api_request(
            "POST",
            "/customers",
            self.admin_token,
            {"name": label, "email": email, "password": password},
        )
        assert created["status"] == 201, created
        token = self.login(email, password)
        customer_id = created["body"]["customer"]["id"]
        account_id = self.open_account(token, currency)
        if int(balance_minor) > 0:
            self.deposit(account_id, int(balance_minor))
        return {
            "customer_id": customer_id,
            "email": email,
            "password": password,
            "token": token,
            "account_id": account_id,
        }

    # ————————————————————————————————————————

    def open_account(self, token: str, currency: str = "RON") -> str:
        response = self.api_request("POST", "/accounts", token, {"currency": currency, "name": f"Cont {currency}"})
        assert response["status"] == 201, response
        return str(response["body"]["id"])

    # ————————————————————————————————————————

    def deposit(self, account_id: str, amount_minor: int) -> dict[str, Any]:
        response = self.api_request(
            "POST",
            f"/accounts/{account_id}/deposit",
            self.admin_token,
            {"amount_minor": int(amount_minor), "description": "Depunere test"},
            {"Idempotency-Key": self.new_key()},
        )
        assert response["status"] == 201, response
        return response

    # ————————————————————————————————————————

    def make_transfer(
        self,
        token: str,
        from_account_id: str,
        to_account_id: str,
        amount_minor: int,
        description: str = "",
        key: str | None = None,
    ) -> dict[str, Any]:
        return self.api_request(
            "POST",
            "/transfers",
            token,
            {
                "from_account_id": from_account_id,
                "to_account_id": to_account_id,
                "amount_minor": int(amount_minor),
                "description": description,
            },
            {"Idempotency-Key": key or self.new_key()},
        )

    # ————————————————————————————————————————

    def account_balance(self, token: str, account_id: str) -> int:
        response = self.api_request("GET", f"/accounts/{account_id}", token)
        assert response["status"] == 200, response
        return int(response["body"]["balance_minor"])

    # ————————————————————————————————————————

    def concurrent_requests(self, requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
        barrier = threading.Barrier(len(requests))

        def run(item: dict[str, Any]) -> dict[str, Any]:
            barrier.wait()
            return self.api_request(
                item["method"], item["path"], item.get("token"), item.get("json"), item.get("headers")
            )

        with ThreadPoolExecutor(max_workers=len(requests)) as pool:
            return list(pool.map(run, requests))

    # ————————————————————————————————————————

    def advance_clock(self, seconds: int) -> str:
        assert self._clock is not None
        return to_iso(self._clock.advance(int(seconds)))

    # ————————————————————————————————————————

    def clock_now(self) -> str:
        assert self._clock is not None
        return to_iso(self._clock.now())

    # ————————————————————————————————————————

    def refresh_fx(self) -> dict[str, Any]:
        return self.api_request("POST", "/fx/refresh", self.admin_token)

    # ————————————————————————————————————————

    def shock_fx(self, currency: str, bps: int) -> dict[str, Any]:
        return self.api_request("POST", "/fx/shock", self.admin_token, {"currency": currency, "bps": int(bps)})

    # ————————————————————————————————————————

    def openapi_schema(self) -> dict[str, Any]:
        assert self.app is not None
        schema: dict[str, Any] = self.app.openapi()
        return schema

    # ————————————————————————————————————————

    def api_contract(self) -> dict[str, Any]:
        path = PROJECT_ROOT / "docs" / "api_contract.json"
        contract: dict[str, Any] = jsonlib.loads(path.read_text(encoding="utf-8"))
        return contract

    # ————————————————————————————————————————

    def contract_violations(self) -> list[str]:
        schema = self.openapi_schema()
        contract = self.api_contract()
        problems: list[str] = []
        for operation in contract["operations"]:
            full_path = f"{contract['prefix']}{operation['path']}"
            declared = schema["paths"].get(full_path, {}).get(operation["method"].lower())
            if declared is None:
                problems.append(f"lipsește {operation['method']} {full_path}")
                continue
            names = {item["name"].lower() for item in declared.get("parameters", [])}
            if operation["idempotent"] and "idempotency-key" not in names:
                problems.append(f"{operation['method']} {full_path} nu declară Idempotency-Key")
            if not operation["idempotent"] and "idempotency-key" in names:
                problems.append(f"{operation['method']} {full_path} declară Idempotency-Key fără să fie în contract")
        documented = {f"{contract['prefix']}{item['path']}" for item in contract["operations"]}
        for path in schema["paths"]:
            if path.startswith(contract["prefix"]) and path not in documented:
                problems.append(f"rută nedocumentată {path}")
        return problems

    # ————————————————————————————————————————

    def log_response(self, response: dict[str, Any]) -> None:
        logger.info(jsonlib.dumps(response, default=str)[:2000])
