from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from ledgerguard.common.clock import Clock
from ledgerguard.common.ports import HistoryPort
from ledgerguard.common.settings import Settings


@dataclass(frozen=True)
class Actor:
    user_id: str | None
    role: str
    customer_id: str | None
    label: str

    # ————————————————————————————————————————

    @staticmethod
    def system(label: str = "system") -> Actor:
        return Actor(None, "system", None, label)

    # ————————————————————————————————————————

    @staticmethod
    def anonymous() -> Actor:
        return Actor(None, "anonymous", None, "anonymous")


# ————————————————————————————————————————

class TxState:
    def __init__(self) -> None:
        self.depth = 0


# ————————————————————————————————————————

class Ctx:
    def __init__(
        self,
        conn: sqlite3.Connection,
        clock: Clock,
        settings: Settings,
        correlation_id: str,
        actor: Actor,
        history: HistoryPort | None = None,
        tx: TxState | None = None,
    ) -> None:
        self.conn = conn
        self.clock = clock
        self.settings = settings
        self.correlation_id = correlation_id
        self.actor = actor
        self.history = history
        self._tx = tx or TxState()

    # ————————————————————————————————————————

    def as_actor(self, actor: Actor) -> Ctx:
        return Ctx(
            self.conn, self.clock, self.settings, self.correlation_id, actor, self.history, self._tx
        )

    # ————————————————————————————————————————

    @contextmanager
    def transaction(self) -> Iterator[None]:
        state = self._tx
        if state.depth > 0:
            state.depth += 1
            try:
                yield
            finally:
                state.depth -= 1
            return
        self.conn.execute("BEGIN IMMEDIATE")
        state.depth = 1
        try:
            yield
        except BaseException:
            state.depth = 0
            self.conn.execute("ROLLBACK")
            raise
        state.depth = 0
        self.conn.execute("COMMIT")
