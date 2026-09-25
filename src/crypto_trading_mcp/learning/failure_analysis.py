from __future__ import annotations

from typing import Any

from crypto_trading_mcp.learning.models import (
    FailureCategory,
    SuccessCategory,
    TradeLearningRecord,
    TradeOutcome,
)


def classify_trade(record: TradeLearningRecord) -> dict[str, Any]:
    """Distinguish bad prediction vs bad execution vs regime vs normal variance."""
    failures: list[FailureCategory] = []
    successes: list[SuccessCategory] = []
    predicted = record.predicted_probability
    outcome_win = record.outcome == TradeOutcome.WIN
    predicted_win = predicted is not None and predicted >= 0.55

    if record.slippage and record.entry_price and record.slippage / max(record.entry_price, 1e-9) > 0.005:
        failures.append(FailureCategory.HIGH_SLIPPAGE)

    if predicted is not None:
        if predicted_win and not outcome_win:
            failures.append(FailureCategory.BAD_PREDICTION)
        elif (not predicted_win) and outcome_win:
            # unexpected win — not a failure
            successes.append(SuccessCategory.GOOD_EXECUTION)
        elif predicted_win and outcome_win:
            successes.append(SuccessCategory.GOOD_PREDICTION)

    if record.execution_quality == "POOR":
        failures.append(FailureCategory.BAD_TIMING_OR_EXECUTION)

    if record.drift_state == "REGIME_SHIFT":
        failures.append(FailureCategory.MARKET_REGIME_SHIFT)

    if record.features.get("EXTERNAL_SHOCK"):
        failures.append(FailureCategory.EXTERNAL_SHOCK)

    if not failures and record.outcome == TradeOutcome.LOSS:
        failures.append(FailureCategory.NORMAL_VARIANCE)

    if not failures and not successes and record.outcome == TradeOutcome.WIN:
        successes.append(SuccessCategory.GOOD_EXECUTION)

    if record.market_regime.value in {"TRENDING_UP", "TRENDING_DOWN", "BREAKOUT"} and outcome_win:
        successes.append(SuccessCategory.REGIME_ALIGNED)

    if not failures and not successes:
        failures.append(FailureCategory.UNKNOWN)

    lesson_parts = []
    if FailureCategory.BAD_PREDICTION in failures:
        lesson_parts.append("Prediction disagreed with outcome; review calibration.")
    if FailureCategory.HIGH_SLIPPAGE in failures:
        lesson_parts.append("Execution slippage elevated relative to entry.")
    if FailureCategory.NORMAL_VARIANCE in failures:
        lesson_parts.append("Loss consistent with normal variance; not labeled strategy failure.")
    if SuccessCategory.GOOD_PREDICTION in successes:
        lesson_parts.append("Prediction aligned with outcome.")
    lesson = " ".join(lesson_parts) or "Recorded for memory."

    record.failure_categories = failures
    record.success_categories = successes
    record.lesson = lesson
    return {
        "failure_categories": [f.value for f in failures],
        "success_categories": [s.value for s in successes],
        "lesson": lesson,
    }
