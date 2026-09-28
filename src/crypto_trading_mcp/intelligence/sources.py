from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class SourceCategory(str, Enum):
    MARKET_DATA = "MARKET_DATA"
    FUNDAMENTAL_DATA = "FUNDAMENTAL_DATA"
    NEWS = "NEWS"
    SOCIAL = "SOCIAL"
    ON_CHAIN = "ON_CHAIN"
    MACRO = "MACRO"
    RESEARCH = "RESEARCH"
    INTERNAL_MEMORY = "INTERNAL_MEMORY"
    PREDICTION_MARKET = "PREDICTION_MARKET"


class IntelligenceRecord(BaseModel):
    source_id: str = Field(default_factory=lambda: f"SRC-{uuid4().hex[:10]}")
    source_type: SourceCategory
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    data_timestamp: str | None = None
    freshness_seconds: float | None = None
    confidence: float = 0.0
    provenance: str = "unknown"
    content: Any = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    status: str = "AVAILABLE"  # AVAILABLE | UNAVAILABLE | STALE

    def to_context_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_type": self.source_type.value,
            "timestamp": self.timestamp,
            "data_timestamp": self.data_timestamp,
            "freshness_seconds": self.freshness_seconds,
            "confidence": self.confidence,
            "provenance": self.provenance,
            "content": self.content,
            "metadata": self.metadata,
            "status": self.status,
        }


class DataSourceAdapter:
    """Provider interface — vendor-agnostic. Context only; never executes trades."""

    category: SourceCategory
    name: str = "base"

    def fetch(self, symbol: str, **kwargs: Any) -> IntelligenceRecord:
        raise NotImplementedError

    def health(self) -> dict[str, Any]:
        return {"name": self.name, "category": self.category.value, "ok": True}


class UnavailableSourceAdapter(DataSourceAdapter):
    def __init__(self, category: SourceCategory, name: str = "unavailable") -> None:
        self.category = category
        self.name = name

    def fetch(self, symbol: str, **kwargs: Any) -> IntelligenceRecord:
        return IntelligenceRecord(
            source_type=self.category,
            status="UNAVAILABLE",
            confidence=0.0,
            provenance=self.name,
            content=None,
            metadata={
                "symbol": symbol,
                "reason": "No provider configured; refusing to fabricate data",
            },
        )
