from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from crypto_trading_mcp.learning.brier import rolling_brier, rolling_log_loss
from crypto_trading_mcp.learning.config import LearningConfig


@dataclass
class CalibrationTracker:
    config: LearningConfig
    history: list[tuple[float, int]] = field(default_factory=list)
    by_strategy: dict[str, list[tuple[float, int]]] = field(default_factory=dict)
    by_regime: dict[str, list[tuple[float, int]]] = field(default_factory=dict)

    def update(
        self,
        predicted: float,
        outcome: int,
        *,
        strategy_id: str | None = None,
        regime: str | None = None,
    ) -> dict[str, Any]:
        pair = (float(predicted), int(outcome))
        self.history.append(pair)
        window = self.config.rolling_window_trades
        if strategy_id:
            self.by_strategy.setdefault(strategy_id, []).append(pair)
            self.by_strategy[strategy_id] = self.by_strategy[strategy_id][-window:]
        if regime:
            self.by_regime.setdefault(regime, []).append(pair)
            self.by_regime[regime] = self.by_regime[regime][-window:]
        self.history = self.history[-window:]
        brier = rolling_brier(self.history)
        degraded = brier is not None and brier > self.config.max_acceptable_brier_score
        return {
            "brier_score": brier,
            "log_loss": rolling_log_loss(self.history),
            "prediction_count": len(self.history),
            "degraded": degraded,
            "threshold": self.config.max_acceptable_brier_score,
            "status": "DEGRADED" if degraded else "OK",
        }

    def status(self) -> dict[str, Any]:
        brier = rolling_brier(self.history)
        return {
            "brier_score": brier,
            "log_loss": rolling_log_loss(self.history),
            "prediction_count": len(self.history),
            "threshold": self.config.max_acceptable_brier_score,
            "status": "DEGRADED"
            if brier is not None and brier > self.config.max_acceptable_brier_score
            else "OK",
            "by_strategy": {
                k: rolling_brier(v) for k, v in self.by_strategy.items()
            },
            "by_regime": {k: rolling_brier(v) for k, v in self.by_regime.items()},
        }
