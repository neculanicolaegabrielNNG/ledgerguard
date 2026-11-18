from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from ledgerguard.accounts import service as accounts
from ledgerguard.agents import repository
from ledgerguard.agents.models import (
    AccountHistoryIn,
    EmptyIn,
    FxContextIn,
    LinkedAccountsIn,
    PrepareTransferIn,
    RecentTransfersIn,
    TransferRefIn,
)
from ledgerguard.audit import service as audit
from ledgerguard.common.clock import iso_after, to_iso
from ledgerguard.common.context import Ctx
from ledgerguard.common.errors import DomainError, forbidden, invalid
from ledgerguard.common.ids import new_id
from ledgerguard.fraud import service as fraud
from ledgerguard.fx import service as fx
from ledgerguard.ledger import service as ledger
from ledgerguard.transfers import service as transfers

OUTPUT_PREVIEW_LIMIT = 2000
MAX_TOOL_CALLS = 12

Handler = Callable[[Ctx, Any], dict[str, Any]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    handler: Handler
    scope: str


# ————————————————————————————————————————

def _untrusted(text: str) -> dict[str, str]:
    return {"untrusted_text": text}


# ————————————————————————————————————————

def _transfer_summary(row: dict[str, Any], account_id: str | None = None) -> dict[str, Any]:
    direction = None
    counterparty = row["to_account_id"]
    if account_id is not None:
        direction = "out" if row["from_account_id"] == account_id else "in"
        counterparty = row["to_account_id"] if direction == "out" else row["from_account_id"]
    return {
        "transfer_id": row["id"],
        "direction": direction,
        "from_account_id": row["from_account_id"],
        "to_account_id": row["to_account_id"],
        "counterparty": counterparty,
        "amount_minor": row["amount_minor"],
        "currency": row["currency"],
        "amount_ron_minor": row["amount_ron_minor"],
        "state": row["state"],
        "created_at": row["created_at"],
        "description": _untrusted(row["description"]),
    }


# ————————————————————————————————————————

def _account_history(ctx: Ctx, args: AccountHistoryIn) -> dict[str, Any]:
    rows = transfers.account_transfers(ctx, args.account_id, args.limit)
    return {
        "account_id": args.account_id,
        "transfers": [_transfer_summary(row, args.account_id) for row in rows],
    }


# ————————————————————————————————————————

def _similar_transactions(ctx: Ctx, args: TransferRefIn) -> dict[str, Any]:
    rows = transfers.similar_transfers(ctx, args.transfer_id)
    return {"transfer_id": args.transfer_id, "similar": [_transfer_summary(row) for row in rows]}


# ————————————————————————————————————————

def _linked_accounts(ctx: Ctx, args: LinkedAccountsIn) -> dict[str, Any]:
    return {"account_id": args.account_id, "linked": fraud.linked_accounts(ctx, args.account_id, args.depth)}


# ————————————————————————————————————————

def _fx_context(ctx: Ctx, args: FxContextIn) -> dict[str, Any]:
    return fx.context(ctx, args.currency)


# ————————————————————————————————————————

def _rule_hits(ctx: Ctx, args: TransferRefIn) -> dict[str, Any]:
    evaluation = fraud.get_evaluation_for_transfer(ctx, args.transfer_id)
    if evaluation is None:
        return {"transfer_id": args.transfer_id, "score": 0, "decision": None, "triggered": []}
    return {
        "transfer_id": args.transfer_id,
        "score": evaluation["score"],
        "decision": evaluation["decision"],
        "triggered": [item for item in evaluation["results"] if item["triggered"]],
    }


# ————————————————————————————————————————

def _list_my_accounts(ctx: Ctx, args: EmptyIn) -> dict[str, Any]:
    page = accounts.list_accounts(ctx, None, None, None, 50)
    return {
        "accounts": [
            {
                "account_id": item["id"],
                "currency": item["currency"],
                "name": item["name"],
                "balance_minor": ledger.balance(ctx, item["id"]),
            }
            for item in page["items"]
        ]
    }


# ————————————————————————————————————————

def _list_my_transfers(ctx: Ctx, args: RecentTransfersIn) -> dict[str, Any]:
    page = transfers.list_transfers(ctx, None, None, None, None, None, None, args.limit)
    return {"transfers": [_transfer_summary(item) for item in page["items"]]}


# ————————————————————————————————————————

def _prepare_transfer(ctx: Ctx, args: PrepareTransferIn) -> dict[str, Any]:
    if ctx.actor.role != "customer" or not ctx.actor.customer_id or not ctx.actor.user_id:
        raise forbidden("Doar clienții pot pregăti transferuri.")
    source = accounts.get_account(ctx, args.from_account_id)
    accounts.authorize_account(ctx, source)
    target = accounts.get_account(ctx, args.to_account_id)
    if target["kind"] != "customer" or source["id"] == target["id"]:
        raise invalid("account_not_transferable", "Destinatar invalid.")
    conversion = fx.quote_conversion(ctx, args.amount_minor, source["currency"], target["currency"])
    limit = ctx.settings.assistant_max_amount_ron_minor
    if conversion.amount_ron_minor > limit:
        raise invalid(
            "assistant_limit_exceeded",
            "Suma depășește limita permisă pentru operațiuni prin asistent.",
            {"limit_ron_minor": limit, "amount_ron_minor": conversion.amount_ron_minor},
        )
    now = ctx.clock.now()
    action_id = new_id("ast")
    payload = {
        "from_account_id": source["id"],
        "to_account_id": target["id"],
        "amount_minor": args.amount_minor,
        "currency": source["currency"],
        "target_currency": target["currency"],
        "target_amount_minor": conversion.target_amount_minor,
        "amount_ron_minor": conversion.amount_ron_minor,
        "description": args.description,
    }
    expires_at = iso_after(now, ctx.settings.assistant_action_ttl_seconds)
    with ctx.transaction():
        repository.insert_action(
            ctx.conn, action_id, ctx.actor.customer_id, ctx.actor.user_id, json.dumps(payload), to_iso(now), expires_at
        )
        audit.record(ctx, "assistant.proposal", "assistant_action", action_id, payload)
    return {"action_id": action_id, "expires_at": expires_at, "summary": payload, "requires_confirmation": True}


# ————————————————————————————————————————

ANALYST_TOOLS: dict[str, ToolSpec] = {
    spec.name: spec
    for spec in (
        ToolSpec(
            "get_account_history",
            "Istoricul recent de transferuri pentru un cont.",
            AccountHistoryIn,
            _account_history,
            "read",
        ),
        ToolSpec(
            "get_similar_transactions",
            "Transferuri similare ale aceluiași client, ca sumă sau destinatar.",
            TransferRefIn,
            _similar_transactions,
            "read",
        ),
        ToolSpec(
            "get_linked_accounts",
            "Conturi legate prin transferuri recente, până la adâncimea indicată.",
            LinkedAccountsIn,
            _linked_accounts,
            "read",
        ),
        ToolSpec("get_fx_context", "Contextul cursului valutar pentru o monedă.", FxContextIn, _fx_context, "read"),
        ToolSpec(
            "get_rule_hits",
            "Regulile antifraudă declanșate pentru un transfer, cu valorile măsurate.",
            TransferRefIn,
            _rule_hits,
            "read",
        ),
    )
}

ASSISTANT_TOOLS: dict[str, ToolSpec] = {
    spec.name: spec
    for spec in (
        ToolSpec("list_my_accounts", "Conturile clientului cu solduri.", EmptyIn, _list_my_accounts, "read"),
        ToolSpec(
            "list_my_recent_transfers",
            "Ultimele transferuri ale clientului.",
            RecentTransfersIn,
            _list_my_transfers,
            "read",
        ),
        ToolSpec(
            "prepare_transfer",
            "Pregătește un transfer care necesită confirmarea explicită a clientului. Nu mută bani.",
            PrepareTransferIn,
            _prepare_transfer,
            "propose",
        ),
    )
}


# ————————————————————————————————————————

def _preview(output: dict[str, Any]) -> str:
    return json.dumps(output, sort_keys=True, default=str)[:OUTPUT_PREVIEW_LIMIT]


# ————————————————————————————————————————

class ToolBox:
    def __init__(self, ctx: Ctx, tools: dict[str, ToolSpec], max_calls: int = MAX_TOOL_CALLS) -> None:
        self._ctx = ctx
        self._tools = tools
        self._max_calls = max_calls
        self.calls = 0
        self.proposals: list[dict[str, Any]] = []

    # ————————————————————————————————————————

    def call(self, name: str, arguments: dict[str, Any], reason: str) -> dict[str, Any]:
        spec = self._tools.get(name)
        if spec is None:
            raise DomainError("tool_not_allowed", "Tool-ul nu este permis acestui agent.", 403, {"tool": name})
        if self.calls >= self._max_calls:
            raise DomainError("tool_call_limit", "Limita de apeluri de tool-uri a fost atinsă.", 429)
        try:
            parsed = spec.input_model.model_validate(arguments)
        except ValidationError as error:
            raise DomainError(
                "tool_input_invalid", "Intrare invalidă pentru tool.", 422, {"errors": error.errors(include_url=False, include_context=False, include_input=False)}
            ) from error
        self.calls += 1
        output = spec.handler(self._ctx, parsed)
        if spec.scope == "propose":
            self.proposals.append(output)
        with self._ctx.transaction():
            audit.record(
                self._ctx,
                "agent.tool_call",
                "tool",
                name,
                {"input": parsed.model_dump(), "output": _preview(output), "reason": reason, "scope": spec.scope},
            )
        return output

    # ————————————————————————————————————————

    def schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "name": spec.name,
                "description": spec.description,
                "input_schema": spec.input_model.model_json_schema(),
            }
            for spec in self._tools.values()
        ]
