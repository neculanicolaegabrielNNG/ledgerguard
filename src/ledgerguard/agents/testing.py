from __future__ import annotations

import json
import random
import re
import secrets
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from ledgerguard.accounts import service as accounts
from ledgerguard.agents import repository
from ledgerguard.app import workflows
from ledgerguard.audit import service as audit
from ledgerguard.auth import service as auth
from ledgerguard.common.clock import to_iso
from ledgerguard.common.context import Actor, Ctx
from ledgerguard.common.errors import DomainError
from ledgerguard.common.ids import new_id
from ledgerguard.common.pagination import build_page, clamp_limit, decode_seq
from ledgerguard.fraud import service as fraud
from ledgerguard.simulation.strategies import STRATEGIES

FIRST_NAMES = ("Andrei", "Maria", "Ioana", "Mihai", "Elena", "Radu", "Ana", "Vlad", "Carmen", "Dan")
LAST_NAMES = ("Popescu", "Ionescu", "Marin", "Dumitru", "Stan", "Georgescu", "Matei", "Rusu", "Toma", "Neagu")
INFRA_PATTERN = re.compile(r"database is locked|timeout|timed out|connection|temporar|rate_limited", re.IGNORECASE)
RULE_TAG = re.compile(r"^rule:(?P<type>[a-z_]+)$")


def generate_synthetic_data(
    ctx: Ctx, seed: int, customers: int, transfers_per_customer: int, password: str | None
) -> dict[str, Any]:
    rng = random.Random(seed)
    secret = password or secrets.token_urlsafe(12)
    batch = ctx.correlation_id[-8:]
    owners: list[tuple[dict[str, Any], dict[str, Any], str]] = []
    for index in range(customers):
        name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
        email = f"synthetic-{batch}-{index}@example.test"
        with ctx.transaction():
            customer = accounts.create_customer(ctx, name)
            user = auth.create_user(ctx, email, secret, "customer", customer["id"])
            account = accounts.create_account(ctx, customer["id"], "RON", "Cont curent")
            workflows.deposit(ctx, account["id"], rng.randint(200_000, 1_000_000), "Depunere sintetică")
        owners.append((user, account, email))
    attempted = completed = flagged = 0
    for user, account, email in owners:
        runner = ctx.as_actor(Actor(user["id"], "customer", account["customer_id"], email))
        for _ in range(transfers_per_customer):
            target = rng.choice([item[1] for item in owners if item[1]["id"] != account["id"]] or [account])
            if target["id"] == account["id"]:
                continue
            attempted += 1
            try:
                detail = workflows.create_transfer_detail(
                    runner, account["id"], target["id"], rng.randint(1_000, 20_000), "Transfer sintetic"
                )
            except DomainError:
                continue
            if detail["state"] == "completed":
                completed += 1
            else:
                flagged += 1
    with ctx.transaction():
        audit.record(
            ctx,
            "quality.synthetic_data",
            "dataset",
            batch,
            {"seed": seed, "customers": customers, "attempted": attempted},
        )
    return {
        "seed": seed,
        "customers": [item[2] for item in owners],
        "password": secret,
        "transfers_attempted": attempted,
        "transfers_completed": completed,
        "transfers_flagged": flagged,
    }


# ————————————————————————————————————————

def _store(ctx: Ctx, kind: str, title: str, detail: dict[str, Any]) -> bool:
    return repository.insert_proposal(
        ctx.conn, new_id("prp"), kind, title, json.dumps(detail, sort_keys=True), to_iso(ctx.clock.now())
    )


# ————————————————————————————————————————

def propose_scenarios(ctx: Ctx, seed: int, count: int) -> dict[str, int]:
    created = 0
    with ctx.transaction():
        for index in range(count):
            strategy = STRATEGIES[index % len(STRATEGIES)]
            detail = {"strategy": strategy, "seed": seed + index, "expectation": "cel puțin o tranzacție semnalată"}
            created += int(_store(ctx, "scenario", f"scenariu:{strategy}:seed{seed + index}", detail))
    return {"created": created, "total": repository.count_proposals(ctx.conn)}


# ————————————————————————————————————————

def propose_from_openapi(ctx: Ctx, schema: dict[str, Any]) -> dict[str, int]:
    created = 0
    with ctx.transaction():
        for path, operations in sorted(schema.get("paths", {}).items()):
            if not path.startswith("/api/v1"):
                continue
            for method, operation in sorted(operations.items()):
                if method not in {"get", "post", "put", "delete"}:
                    continue
                label = f"{method.upper()} {path}"
                names = {item.get("name", "").lower() for item in operation.get("parameters", [])}
                if "authorization" in names:
                    created += int(_store(ctx, "api_case", f"{label}: 401 fără token", {"expect_status": 401}))
                if "idempotency-key" in names:
                    created += int(
                        _store(ctx, "api_case", f"{label}: 400 fără Idempotency-Key", {"expect_status": 400})
                    )
                if "{" in path:
                    created += int(
                        _store(ctx, "api_case", f"{label}: 404 pentru identificator inexistent", {"expect_status": 404})
                    )
                if "requestBody" in operation:
                    created += int(_store(ctx, "api_case", f"{label}: 422 pentru corp gol", {"expect_status": 422}))
    return {"created": created, "total": repository.count_proposals(ctx.conn)}


# ————————————————————————————————————————

def list_proposals(ctx: Ctx, kind: str | None, cursor: str | None, limit: int) -> dict[str, Any]:
    size = clamp_limit(limit)
    rows = repository.list_proposals(ctx.conn, kind, decode_seq(cursor), size)
    page = build_page(rows, size)
    page["items"] = [{**item, "detail": json.loads(item["detail"])} for item in page["items"]]
    return page


# ————————————————————————————————————————

def _walk(suite: ET.Element, parents: list[str], out: list[dict[str, Any]]) -> None:
    path = [*parents, suite.get("name", "")]
    for test in suite.findall("test"):
        status = test.find("status")
        out.append(
            {
                "suite": ".".join(path),
                "test": test.get("name", ""),
                "status": status.get("status", "FAIL") if status is not None else "FAIL",
                "message": ((status.text or "") if status is not None else "").strip(),
                "tags": [tag.text or "" for tag in test.findall("tag")],
            }
        )
    for child in suite.findall("suite"):
        _walk(child, path, out)


# ————————————————————————————————————————

def parse_robot_output(path: Path) -> tuple[str, list[dict[str, Any]]]:
    root = ET.parse(path).getroot()
    results: list[dict[str, Any]] = []
    for suite in root.findall("suite"):
        _walk(suite, [], results)
    return root.get("generated", ""), results


# ————————————————————————————————————————

def ingest_robot_output(ctx: Ctx, path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"ingested": 0, "run_label": None}
    label, results = parse_robot_output(path)
    with ctx.transaction():
        if label in repository.known_run_labels(ctx.conn):
            return {"ingested": 0, "run_label": label}
        now = to_iso(ctx.clock.now())
        for item in results:
            repository.insert_test_run(
                ctx.conn,
                label,
                item["suite"],
                item["test"],
                item["status"] if item["status"] in {"PASS", "FAIL", "SKIP"} else "FAIL",
                item["message"][:2000],
                json.dumps(item["tags"]),
                now,
            )
    return {"ingested": len(results), "run_label": label}


# ————————————————————————————————————————

def classify_failure(message: str, previous: list[str]) -> tuple[str, str, str]:
    if INFRA_PATTERN.search(message):
        return "flaky", "medium", "Mesajul indică o cauză de infrastructură sau de sincronizare, nu o regresie de logică."
    if "PASS" in previous and "FAIL" in previous:
        return "flaky", "medium", "Rezultate mixte în rulările anterioare pentru același test."
    if previous and all(item == "PASS" for item in previous):
        return "real_bug", "high", "Test stabil care eșuează prima dată: probabilă regresie în cod."
    if previous and all(item == "FAIL" for item in previous):
        return "real_bug", "high", "Eșec constant în rulări succesive: defect reproductibil."
    return "real_bug", "low", "Fără istoric suficient; eșecul este tratat ca defect până la dovada contrară."


# ————————————————————————————————————————

def triage(ctx: Ctx, path: Path) -> list[dict[str, Any]]:
    label, results = parse_robot_output(path)
    verdicts: list[dict[str, Any]] = []
    for item in results:
        if item["status"] != "FAIL":
            continue
        previous = [
            row["status"]
            for row in repository.history_of_test(ctx.conn, item["suite"], item["test"], 10)
            if row["run_label"] != label
        ]
        verdict, confidence, reason = classify_failure(item["message"], previous)
        verdicts.append(
            {
                "suite": item["suite"],
                "test": item["test"],
                "verdict": verdict,
                "confidence": confidence,
                "reason": reason,
                "message": item["message"][:300],
            }
        )
    return verdicts


# ————————————————————————————————————————

def quality_panel(ctx: Ctx, path: Path) -> dict[str, Any]:
    summary: dict[str, Any] = {"available": path.exists(), "total": 0, "passed": 0, "failed": 0, "suites": {}}
    covered: dict[str, int] = {}
    if path.exists():
        _, results = parse_robot_output(path)
        for item in results:
            summary["total"] += 1
            key = "passed" if item["status"] == "PASS" else "failed"
            summary[key] += 1
            suite = summary["suites"].setdefault(item["suite"], {"passed": 0, "failed": 0})
            suite[key] += 1
            for tag in item["tags"]:
                matched = RULE_TAG.match(tag)
                if matched and item["status"] == "PASS":
                    covered[matched.group("type")] = covered.get(matched.group("type"), 0) + 1
    coverage = [
        {"rule_id": rule.id, "type": rule.type, "passing_tests": covered.get(rule.type, 0)}
        for rule in fraud.active_rules(ctx)
    ]
    return {
        "tests": summary,
        "rule_coverage": coverage,
        "rules_covered": sum(1 for item in coverage if item["passing_tests"] > 0),
        "rules_total": len(coverage),
        "proposals": repository.count_proposals(ctx.conn),
    }
