"""Pre-trade failure-memory gate (OKF): block if failure match confidence > threshold."""

from __future__ import annotations

from typing import Any, Sequence

from crypto_trading_mcp.learning.config import LearningConfig
from crypto_trading_mcp.learning.embeddings import cosine_similarity, embed_features
from crypto_trading_mcp.learning.features import feature_vector
from crypto_trading_mcp.learning.models import TradeLearningRecord, TradeOutcome


class PreTradeMemoryGate:
    """Deterministic memory check before trade progresses toward execution.

    Uses cosine similarity over feature embeddings (same as Phase 8 retrieval).
    If memory service is unavailable → fail closed when configured.
    LLMs cannot override a block.
    """

    def __init__(
        self,
        *,
        block_confidence: float = 0.80,
        fail_closed_when_unavailable: bool = True,
        config: LearningConfig | None = None,
    ) -> None:
        self.block_confidence = block_confidence
        self.fail_closed_when_unavailable = fail_closed_when_unavailable
        self.config = config or LearningConfig()

    def evaluate(
        self,
        query_features: dict[str, Any] | None,
        records: Sequence[TradeLearningRecord] | None,
        *,
        memory_available: bool = True,
    ) -> dict[str, Any]:
        if not memory_available or records is None or query_features is None:
            if self.fail_closed_when_unavailable:
                return {
                    "allowed": False,
                    "reason_code": "FAILURE_MEMORY_UNAVAILABLE",
                    "match_confidence": None,
                    "matched_memory_id": None,
                    "fail_closed": True,
                    "llm_can_override": False,
                }
            return {
                "allowed": True,
                "reason_code": "FAILURE_MEMORY_UNAVAILABLE_FAIL_OPEN",
                "match_confidence": None,
                "matched_memory_id": None,
                "fail_closed": False,
                "llm_can_override": False,
            }

        q = embed_features(feature_vector(query_features))
        best_sim = 0.0
        best_id: str | None = None
        best_trade: str | None = None
        for rec in records:
            if rec.outcome != TradeOutcome.LOSS:
                continue
            sim = cosine_similarity(q, embed_features(feature_vector(rec.features)))
            if sim > best_sim:
                best_sim = sim
                best_id = rec.memory_id
                best_trade = rec.trade_id

        if best_sim > self.block_confidence:
            return {
                "allowed": False,
                "reason_code": "FAILURE_MEMORY_MATCH_BLOCK",
                "match_confidence": round(best_sim, 6),
                "matched_memory_id": best_id,
                "matched_trade_id": best_trade,
                "threshold": self.block_confidence,
                "llm_can_override": False,
                "similarity_method": "cosine_feature_embedding",
                "note": (
                    "Block is based on cosine similarity of feature embeddings; "
                    "not claimed as semantic NLP accuracy."
                ),
            }
        return {
            "allowed": True,
            "reason_code": "FAILURE_MEMORY_OK",
            "match_confidence": round(best_sim, 6) if best_id else 0.0,
            "matched_memory_id": best_id,
            "threshold": self.block_confidence,
            "llm_can_override": False,
            "similarity_method": "cosine_feature_embedding",
        }
