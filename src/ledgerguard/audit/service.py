from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

from ledgerguard.audit import repository
from ledgerguard.common.clock import normalize_instant, to_iso
from ledgerguard.common.context import Ctx
from ledgerguard.common.db import Row
from ledgerguard.common.errors import bad_request, not_found
from ledgerguard.common.ids import new_id
from ledgerguard.common.pagination import build_page, clamp_limit, decode_seq

WebhookSender = Callable[[str, bytes, dict[str, str]], int]

KNOWN_EVENTS = ("transfer.blocked", "fx.alert", "transfer.under_review", "*")


def record(ctx: Ctx, action: str, entity_type: str, entity_id: str, payload: dict[str, Any]) -> int:
    return repository.insert_log(
        ctx.conn,
        to_iso(ctx.clock.now()),
        ctx.correlation_id,
        ctx.actor.label,
        ctx.actor.role,
        action,
        entity_type,
        entity_id,
        json.dumps(payload, sort_keys=True, default=str),
    )


# ————————————————————————————————————————

def _present(row: Row) -> Row:
    return {**row, "payload": json.loads(row["payload"])}


# ————————————————————————————————————————

def search(
    ctx: Ctx,
    filters: dict[str, str | None],
    text: str | None,
    cursor: str | None,
    limit: int,
) -> dict[str, Any]:
    size = clamp_limit(limit)
    normalized = dict(filters)
    for key in ("date_from", "date_to"):
        if normalized.get(key):
            normalized[key] = normalize_instant(str(normalized[key]))
    rows = repository.search_logs(ctx.conn, normalized, text, decode_seq(cursor), size)
    page = build_page(rows, size)
    page["items"] = [_present(item) for item in page["items"]]
    return page


# ————————————————————————————————————————

def emit_event(ctx: Ctx, event: str, payload: dict[str, Any]) -> int:
    created = 0
    now = to_iso(ctx.clock.now())
    body = json.dumps(
        {"event": event, "at": now, "correlation_id": ctx.correlation_id, "data": payload},
        sort_keys=True,
        default=str,
    )
    for hook in repository.list_webhooks(ctx.conn, active_only=True):
        subscribed = json.loads(hook["events"])
        if event in subscribed or "*" in subscribed:
            repository.insert_delivery(ctx.conn, new_id("whd"), hook["id"], event, body, now)
            created += 1
    return created


# ————————————————————————————————————————

def create_webhook(ctx: Ctx, url: str, events: list[str]) -> Row:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise bad_request("invalid_webhook_url", "Adresa webhook trebuie să fie http sau https.")
    unknown = [item for item in events if item not in KNOWN_EVENTS]
    if unknown or not events:
        raise bad_request("invalid_webhook_events", "Evenimente necunoscute sau lipsă.", {"events": unknown})
    webhook_id = new_id("whk")
    secret = secrets.token_hex(24)
    with ctx.transaction():
        repository.insert_webhook(
            ctx.conn, webhook_id, url, json.dumps(events), secret, to_iso(ctx.clock.now()), ctx.actor.label
        )
        record(ctx, "webhook.created", "webhook", webhook_id, {"url": url, "events": events})
    return {"id": webhook_id, "url": url, "events": events, "secret": secret, "active": True}


# ————————————————————————————————————————

def list_webhooks(ctx: Ctx) -> list[Row]:
    return [
        {"id": hook["id"], "url": hook["url"], "events": json.loads(hook["events"]), "active": bool(hook["active"])}
        for hook in repository.list_webhooks(ctx.conn, active_only=False)
    ]


# ————————————————————————————————————————

def delete_webhook(ctx: Ctx, webhook_id: str) -> None:
    with ctx.transaction():
        if repository.get_webhook(ctx.conn, webhook_id) is None:
            raise not_found("webhook", webhook_id)
        repository.deactivate_webhook(ctx.conn, webhook_id)
        record(ctx, "webhook.deleted", "webhook", webhook_id, {})


# ————————————————————————————————————————

def list_deliveries(ctx: Ctx, cursor: str | None, limit: int) -> dict[str, Any]:
    size = clamp_limit(limit)
    rows = repository.list_deliveries(ctx.conn, decode_seq(cursor), size)
    page = build_page(rows, size)
    page["items"] = [{**item, "payload": json.loads(item["payload"])} for item in page["items"]]
    return page


# ————————————————————————————————————————

def sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


# ————————————————————————————————————————

def default_sender(url: str, body: bytes, headers: dict[str, str]) -> int:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return int(response.status)
    except urllib.error.HTTPError as error:
        return int(error.code)
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0


# ————————————————————————————————————————

def deliver_pending(ctx: Ctx, sender: WebhookSender, limit: int = 50) -> int:
    delivered = 0
    for item in repository.pending_deliveries(ctx.conn, limit):
        body = item["payload"].encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "X-LedgerGuard-Event": item["event"],
            "X-LedgerGuard-Signature": sign(item["secret"], body),
        }
        code = sender(item["url"], body, headers)
        status = "delivered" if 200 <= code < 300 else "pending"
        if status == "pending" and item["attempts"] + 1 >= 5:
            status = "failed"
        repository.mark_delivery(ctx.conn, item["id"], status, code or None, to_iso(ctx.clock.now()))
        delivered += 1 if status == "delivered" else 0
    return delivered
