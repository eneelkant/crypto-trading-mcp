from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from crypto_trading_mcp.intelligence.sources import IntelligenceRecord, SourceCategory


def annotate_provenance(
    record: IntelligenceRecord,
    *,
    provider: str,
    url: str | None = None,
) -> IntelligenceRecord:
    meta = dict(record.metadata)
    meta["provider"] = provider
    if url:
        meta["url"] = url
    meta["annotated_at"] = datetime.now(UTC).isoformat()
    record.metadata = meta
    record.provenance = provider
    return record


def freshness_seconds(data_timestamp: str | None, now: datetime | None = None) -> float | None:
    if not data_timestamp:
        return None
    now = now or datetime.now(UTC)
    try:
        ts = datetime.fromisoformat(data_timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0.0, (now - ts).total_seconds())


def categorize(name: str) -> SourceCategory:
    key = name.upper().strip()
    try:
        return SourceCategory(key)
    except ValueError:
        return SourceCategory.RESEARCH


def public_provenance_view(record: IntelligenceRecord) -> dict[str, Any]:
    return {
        "source_id": record.source_id,
        "source_type": record.source_type.value,
        "provenance": record.provenance,
        "data_timestamp": record.data_timestamp,
        "freshness_seconds": record.freshness_seconds,
        "confidence": record.confidence,
        "status": record.status,
    }
