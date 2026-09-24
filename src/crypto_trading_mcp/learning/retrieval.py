from __future__ import annotations

from typing import Any

from crypto_trading_mcp.learning.config import LearningConfig
from crypto_trading_mcp.learning.embeddings import cosine_similarity, embed_features
from crypto_trading_mcp.learning.features import feature_vector
from crypto_trading_mcp.learning.models import LearningContext, MarketRegime, TradeLearningRecord, TradeOutcome


def build_learning_context(
    query_features: dict[str, Any],
    records: list[TradeLearningRecord],
    *,
    config: LearningConfig,
    regime: MarketRegime = MarketRegime.UNKNOWN,
    brier_status: str = "UNKNOWN",
    drift_status: str = "OK",
) -> LearningContext:
    q = embed_features(feature_vector(query_features))
    scored: list[tuple[float, TradeLearningRecord]] = []
    for rec in records:
        sim = cosine_similarity(q, embed_features(feature_vector(rec.features)))
        if sim >= config.similarity_threshold:
            scored.append((sim, rec))
    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[: config.max_retrieved_cases]
    failures = [r for _, r in top if r.outcome == TradeOutcome.LOSS]
    successes = [r for _, r in top if r.outcome == TradeOutcome.WIN]
    fail_patterns: list[str] = []
    for r in failures:
        fail_patterns.extend(c.value for c in r.failure_categories)
    success_patterns: list[str] = []
    for r in successes:
        success_patterns.extend(c.value for c in r.success_categories)
    avg = None
    if top:
        avg = sum(r.net_pnl for _, r in top) / len(top)
    hist_conf = None
    if top:
        probs = [r.predicted_probability for _, r in top if r.predicted_probability is not None]
        hist_conf = sum(probs) / len(probs) if probs else None
    return LearningContext(
        similar_case_count=len(top),
        similar_failure_count=len(failures),
        similar_success_count=len(successes),
        common_failure_patterns=sorted(set(fail_patterns)),
        common_success_patterns=sorted(set(success_patterns)),
        average_outcome=avg,
        historical_confidence=hist_conf,
        recommended_caution=len(failures) > len(successes) and len(failures) > 0,
        regime=regime,
        brier_status=brier_status,
        drift_status=drift_status,
        cases=[
            {
                "memory_id": r.memory_id,
                "trade_id": r.trade_id,
                "similarity": round(sim, 4),
                "outcome": r.outcome.value,
                "lesson": r.lesson,
                "net_pnl": r.net_pnl,
            }
            for sim, r in top
        ],
    )
