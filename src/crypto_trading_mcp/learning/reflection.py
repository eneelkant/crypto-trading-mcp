from __future__ import annotations

from typing import Any

from crypto_trading_mcp.learning.models import ReflectionRecord, TradeLearningRecord, TradeOutcome


class ReflectionEngine:
    def reflect(self, record: TradeLearningRecord, post_mortem: dict[str, Any]) -> ReflectionRecord:
        expected = (
            f"Predicted win probability {record.predicted_probability}"
            if record.predicted_probability is not None
            else "No explicit probability recorded"
        )
        actual = f"Outcome {record.outcome.value} net_pnl={record.net_pnl}"
        contributors = list(post_mortem.get("classification", {}).get("failure_categories", []))
        contributors += list(post_mortem.get("classification", {}).get("success_categories", []))
        return ReflectionRecord(
            trade_id=record.trade_id,
            what_happened=f"Trade {record.trade_id} closed as {record.outcome.value}",
            what_was_expected=expected,
            what_actually_happened=actual,
            contributors=contributors,
            prediction_correct=post_mortem.get("prediction_correct"),
            execution_correct=record.execution_quality != "POOR",
            regime_correct=True,
            confidence_calibrated=not (
                record.brier_score is not None and record.brier_score > 0.25
            ),
            pattern_to_remember=record.lesson,
            what_should_be_tested=(
                "Calibration and regime filters"
                if record.outcome == TradeOutcome.LOSS
                else "Repeatability of successful setup"
            ),
            evidence={
                "regime": record.market_regime.value,
                "brier_score": record.brier_score,
                "features": {k: v for k, v in record.features.items() if k != "MARKET_REGIME"},
            },
        )
