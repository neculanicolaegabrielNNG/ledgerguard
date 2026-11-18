from __future__ import annotations

from ledgerguard.accounts import service as accounts
from ledgerguard.common.clock import Clock
from ledgerguard.common.context import Actor, Ctx
from ledgerguard.common.db import Row, connect
from ledgerguard.common.ports import TransferFact
from ledgerguard.common.settings import Settings
from ledgerguard.transfers import service as transfers


def _fact(row: Row) -> TransferFact:
    return TransferFact(
        transfer_id=row["id"],
        customer_id=row["customer_id"],
        from_account_id=row["from_account_id"],
        to_account_id=row["to_account_id"],
        amount_ron_minor=int(row["amount_ron_minor"]),
        created_at=row["created_at"],
        state=row["state"],
    )


# ————————————————————————————————————————

class SqlHistory:
    def __init__(self, ctx: Ctx) -> None:
        self._ctx = ctx

    # ————————————————————————————————————————

    def customer_transfers(self, customer_id: str, since: str, exclude_id: str | None) -> list[TransferFact]:
        return [_fact(row) for row in transfers.fact_rows(self._ctx, customer_id, since, exclude_id)]

    # ————————————————————————————————————————

    def edges_since(self, since: str, exclude_id: str | None) -> list[TransferFact]:
        return [_fact(row) for row in transfers.fact_rows(self._ctx, None, since, exclude_id)]

    # ————————————————————————————————————————

    def beneficiary_seen(self, customer_id: str, to_account_id: str, exclude_id: str | None) -> bool:
        return transfers.beneficiary_seen(self._ctx, customer_id, to_account_id, exclude_id)

    # ————————————————————————————————————————

    def account_created_at(self, account_id: str) -> str:
        return str(accounts.get_account(self._ctx, account_id)["created_at"])

    # ————————————————————————————————————————

    def account_owner(self, account_id: str) -> str | None:
        owner = accounts.get_account(self._ctx, account_id)["customer_id"]
        return str(owner) if owner else None


# ————————————————————————————————————————

def make_ctx(settings: Settings, clock: Clock, correlation_id: str, actor: Actor) -> Ctx:
    ctx = Ctx(connect(settings.db_path), clock, settings, correlation_id, actor)
    ctx.history = SqlHistory(ctx)
    return ctx


# ————————————————————————————————————————

def attach_history(ctx: Ctx) -> Ctx:
    ctx.history = SqlHistory(ctx)
    return ctx
