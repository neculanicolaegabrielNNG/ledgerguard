from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    ref: str
    detail: str


# ————————————————————————————————————————

class AnalystReport(BaseModel):
    recommendation: Literal["approve", "block", "escalate"]
    rationale: list[str]
    evidence: list[Evidence]
    confidence: float = Field(ge=0.0, le=1.0)
    engine: str
    flags: list[str] = Field(default_factory=list)


# ————————————————————————————————————————

class AssistantReply(BaseModel):
    intent: Literal["balance", "history", "transfer", "help", "unknown"]
    text: str
    proposal: dict[str, Any] | None = None


# ————————————————————————————————————————

class AccountHistoryIn(BaseModel):
    account_id: str = Field(min_length=1, max_length=64)
    limit: int = Field(default=20, ge=1, le=100)


# ————————————————————————————————————————

class TransferRefIn(BaseModel):
    transfer_id: str = Field(min_length=1, max_length=64)


# ————————————————————————————————————————

class LinkedAccountsIn(BaseModel):
    account_id: str = Field(min_length=1, max_length=64)
    depth: int = Field(default=2, ge=1, le=3)


# ————————————————————————————————————————

class FxContextIn(BaseModel):
    currency: str = Field(min_length=3, max_length=3)


# ————————————————————————————————————————

class EmptyIn(BaseModel):
    pass


# ————————————————————————————————————————

class RecentTransfersIn(BaseModel):
    limit: int = Field(default=10, ge=1, le=50)


# ————————————————————————————————————————

class PrepareTransferIn(BaseModel):
    from_account_id: str = Field(min_length=1, max_length=64)
    to_account_id: str = Field(min_length=1, max_length=64)
    amount_minor: int = Field(gt=0, le=10**12)
    description: str = Field(default="Transfer inițiat prin asistent", max_length=200)
