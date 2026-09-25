from __future__ import annotations

import math
from typing import Any, Sequence

from crypto_trading_mcp.exchange.prediction import brier_score


def log_loss(probability: float, outcome: int) -> float:
    p = min(max(probability, 1e-12), 1 - 1e-12)
    return -(outcome * math.log(p) + (1 - outcome) * math.log(1 - p))


def evaluate_prediction_rows(
    rows: Sequence[dict[str, Any]],
    *,
    edge_threshold: float = 0.04,
    max_brier: float = 0.25,
) -> dict[str, Any]:
    """Evaluate prediction-market forecasts separately from trading Sharpe."""
    if not rows:
        return {
            "count": 0,
            "brier_mean": None,
            "log_loss_mean": None,
            "roi": 0.0,
            "edge_threshold": edge_threshold,
            "max_brier_score_calibration": max_brier,
            "disclaimer": "Prediction evaluation only. Not mixed with trading Sharpe.",
        }
    briers = []
    losses = []
    pnl = 0.0
    stake = 0.0
    ensemble_rows = []
    for row in rows:
        p = float(row.get("predicted_probability") or row.get("ensemble_probability") or 0.5)
        market_p = float(row.get("market_probability") or 0.5)
        outcome = int(row.get("outcome") or 0)
        edge = p - market_p
        briers.append(brier_score(p, outcome))
        losses.append(log_loss(p, outcome))
        # Simple paper settlement: buy YES if edge>=threshold
        if abs(edge) >= edge_threshold:
            qty = float(row.get("quantity") or 1.0)
            price = market_p if edge > 0 else (1 - market_p)
            settlement = float(outcome if edge > 0 else 1 - outcome)
            pnl += (settlement - price) * qty
            stake += price * qty
        ensemble_rows.append(
            {
                "model": row.get("model"),
                "weight": row.get("weight"),
                "prediction": p,
                "confidence": row.get("confidence"),
                "ensemble_probability": row.get("ensemble_probability", p),
                "market_probability": market_p,
                "edge": edge,
                "actual_outcome": outcome,
                "brier_score": brier_score(p, outcome),
            }
        )
    mean_brier = sum(briers) / len(briers)
    return {
        "count": len(rows),
        "brier_mean": mean_brier,
        "log_loss_mean": sum(losses) / len(losses),
        "calibration_ok": mean_brier <= max_brier,
        "roi": (pnl / stake) if stake else 0.0,
        "net_pnl": pnl,
        "edge_threshold": edge_threshold,
        "max_brier_score_calibration": max_brier,
        "ensemble": ensemble_rows,
        "TRADING_MODE": "PAPER",
        "REAL_MONEY": "DISABLED",
        "disclaimer": (
            "Prediction-market metrics (Brier/log-loss) are separate from trading Sharpe. "
            "Historical results do not guarantee future performance."
        ),
    }
