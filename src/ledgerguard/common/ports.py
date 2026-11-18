from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TransferFact:
    transfer_id: str
    customer_id: str
    from_account_id: str
    to_account_id: str
    amount_ron_minor: int
    created_at: str
    state: str


# ————————————————————————————————————————

class HistoryPort(Protocol):
    def customer_transfers(
        self, customer_id: str, since: str, exclude_id: str | None
    ) -> list[TransferFact]: ...

    def edges_since(self, since: str, exclude_id: str | None) -> list[TransferFact]: ...

    def beneficiary_seen(self, customer_id: str, to_account_id: str, exclude_id: str | None) -> bool: ...

    def account_created_at(self, account_id: str) -> str: ...

    def account_owner(self, account_id: str) -> str | None: ...
