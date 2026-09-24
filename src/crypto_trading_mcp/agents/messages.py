from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class Decision(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"
    NO_TRADE = "NO_TRADE"
    HOLD = "HOLD"
    BUY = "BUY"
    SELL = "SELL"


class MessageStatus(StrEnum):
    OK = "ok"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


class AgentMessage(BaseModel):
    """Structured envelope for inter-agent communication."""

    message_id: str = Field(default_factory=lambda: str(uuid4()))
    agent: str
    agent_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    symbol: str | None = None
    decision: str | None = None
    confidence: float = 0.0
    evidence: list[Any] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    model: str = "none"
    provider: str = "none"
    version: str = "1.0.0"
    latency_ms: float = 0.0
    status: MessageStatus = MessageStatus.OK
    payload: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None

    @field_validator("confidence")
    @classmethod
    def _clamp_confidence(cls, value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    def to_audit_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
