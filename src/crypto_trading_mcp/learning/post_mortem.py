from __future__ import annotations

from typing import Any

from crypto_trading_mcp.learning.failure_analysis import classify_trade
from crypto_trading_mcp.learning.models import TradeLearningRecord, TradeOutcome


def run_post_mortem(record: TradeLearningRecord) -> dict[str, Any]:
    """Automatic post-mortem after trade close — structured only."""
    if record.net_pnl > 0:
        record.outcome = TradeOutcome.WIN
    elif record.net_pnl < 0:
        record.outcome = TradeOutcome.LOSS
    else:
        record.outcome = TradeOutcome.BREAKEVEN

    classification = classify_trade(record)
    predicted = record.predicted_probability
    actual = 1 if record.outcome == TradeOutcome.WIN else 0
    brier = None
    if predicted is not None:
        from crypto_trading_mcp.exchange.prediction import brier_score

        brier = brier_score(predicted, actual)
        record.brier_score = brier

    return {
        "trade_id": record.trade_id,
        "outcome": record.outcome.value,
        "classification": classification,
        "brier_score": brier,
        "regime": record.market_regime.value,
        "prediction_correct": (
            None
            if predicted is None
            else ((predicted >= 0.55) == (record.outcome == TradeOutcome.WIN))
        ),
        "execution_quality": record.execution_quality,
        "lesson": record.lesson,
    }
