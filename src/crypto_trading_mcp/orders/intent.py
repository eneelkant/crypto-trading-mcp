from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class IntentStatus(str, Enum):
    DRAFT = "DRAFT"
    PERSISTED = "PERSISTED"
    SUBMITTING = "SUBMITTING"
    SUBMITTED = "SUBMITTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class OrderIntent(BaseModel):
    intent_id: str = Field(default_factory=lambda: f"INT-{uuid4().hex[:12]}")
    idempotency_key: str
    strategy_id: str
    strategy_version: str = "1.0.0"
    agent_decision_id: str | None = None
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    exchange: str
    symbol: str
    side: str
    quantity: float
    price: float | None = None
    order_type: str = "MARKET"
    risk_decision: dict[str, Any] = Field(default_factory=dict)
    portfolio_state_ref: str | None = None
    execution_stage: str = "STAGE_1_LOCAL_PAPER"
    status: IntentStatus = IntentStatus.DRAFT
    reason_codes: list[str] = Field(default_factory=list)
    exchange_order_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        data = self.model_dump()
        data["status"] = self.status.value
        # Never persist secrets in metadata
        meta = dict(data.get("metadata") or {})
        for k in list(meta):
            lk = str(k).lower()
            if any(s in lk for s in ("secret", "api_key", "token", "password")):
                meta[k] = "[REDACTED]"
        data["metadata"] = meta
        return data


class OrderSubmission(BaseModel):
    intent_id: str
    submitted_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    request_fingerprint: str
    accepted: bool = False
    exchange_order_id: str | None = None
    raw_status: str | None = None


class OrderStatusRecord(BaseModel):
    intent_id: str
    exchange_order_id: str | None = None
    status: str
    checked_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    details: dict[str, Any] = Field(default_factory=dict)


class FillRecord(BaseModel):
    intent_id: str
    fill_id: str = Field(default_factory=lambda: f"FILL-{uuid4().hex[:10]}")
    quantity: float
    price: float
    fee: float = 0.0
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class CancelRequest(BaseModel):
    intent_id: str
    reason: str = "operator"
    requested_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class CancelResult(BaseModel):
    intent_id: str
    success: bool
    reason_codes: list[str] = Field(default_factory=list)
    completed_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
