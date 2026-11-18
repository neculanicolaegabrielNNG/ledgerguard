from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ledgerguard.common.clock import to_iso
from ledgerguard.common.context import Ctx
from ledgerguard.common.db import fetch_one
from ledgerguard.common.errors import bad_request, conflict

KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:\-]{8,128}$")


@dataclass(frozen=True)
class IdempotentResult:
    status_code: int
    body: dict[str, Any]
    replayed: bool


# ————————————————————————————————————————

def validate_key(key: str | None) -> str:
    if key is None or not key.strip():
        raise bad_request("idempotency_key_required", "Antetul Idempotency-Key este obligatoriu.")
    if not KEY_PATTERN.match(key):
        raise bad_request("idempotency_key_invalid", "Idempotency-Key trebuie să aibă 8-128 caractere sigure.")
    return key


# ————————————————————————————————————————

def request_hash(operation: str, payload: dict[str, Any]) -> str:
    canonical = json.dumps({"op": operation, "payload": payload}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ————————————————————————————————————————

def run_idempotent(
    ctx: Ctx,
    scope: str,
    key: str,
    operation: str,
    payload: dict[str, Any],
    action: Callable[[], tuple[int, dict[str, Any]]],
) -> IdempotentResult:
    digest = request_hash(operation, payload)
    with ctx.transaction():
        stored = fetch_one(
            ctx.conn,
            "SELECT request_hash, status_code, response FROM idempotency_keys WHERE scope = ? AND key = ?",
            (scope, key),
        )
        if stored is not None:
            if stored["request_hash"] != digest:
                raise conflict(
                    "idempotency_key_reuse",
                    "Aceeași Idempotency-Key a fost folosită cu un conținut diferit.",
                )
            return IdempotentResult(int(stored["status_code"]), json.loads(stored["response"]), True)
        status_code, body = action()
        ctx.conn.execute(
            "INSERT INTO idempotency_keys (scope, key, request_hash, status_code, response, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (scope, key, digest, status_code, json.dumps(body, sort_keys=True), to_iso(ctx.clock.now())),
        )
        return IdempotentResult(status_code, body, False)
