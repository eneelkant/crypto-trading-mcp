"""Brier-score recalibration bounded by OKF / hard risk limits."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from crypto_trading_mcp.learning.brier import rolling_brier


@dataclass
class RecalibrationEvent:
    timestamp: str
    brier_score: float
    threshold: float
    previous_kelly_multiplier: float
    new_kelly_multiplier: float
    previous_confidence_weight: float
    new_confidence_weight: float
    model_version: str
    reversible: bool = True
    weakens_hard_risk_limits: bool = False


@dataclass
class BrierRecalibrator:
    """If BS > threshold: reduce confidence weightings and Kelly to 0.25x of base.

    Equal and below threshold: no degradation from this path.
    Never weakens hard risk limits.
    """

    threshold: float = 0.25
    base_kelly_multiplier: float = 0.25
    degraded_kelly_multiplier: float = 0.0625  # 0.25 * 0.25
    base_confidence_weight: float = 1.0
    degraded_confidence_weight: float = 0.5
    model_version: str = "okf_calibration_v1"
    history: list[tuple[float, int]] = field(default_factory=list)
    events: list[RecalibrationEvent] = field(default_factory=list)
    kelly_multiplier: float = 0.25
    confidence_weight: float = 1.0
    degraded: bool = False

    def update(self, predicted: float, outcome: int) -> dict[str, Any]:
        self.history.append((float(predicted), int(outcome)))
        brier = rolling_brier(self.history)
        if brier is None:
            return self.status()
        # Strict greater-than: equal to threshold does not degrade.
        if brier > self.threshold:
            prev_k = self.kelly_multiplier
            prev_c = self.confidence_weight
            # Apply OKF shrivel; never raise multipliers.
            new_k = min(self.kelly_multiplier, self.degraded_kelly_multiplier)
            new_c = min(self.confidence_weight, self.degraded_confidence_weight)
            if not self.degraded or new_k < prev_k or new_c < prev_c:
                event = RecalibrationEvent(
                    timestamp=datetime.now(UTC).isoformat(),
                    brier_score=brier,
                    threshold=self.threshold,
                    previous_kelly_multiplier=prev_k,
                    new_kelly_multiplier=new_k,
                    previous_confidence_weight=prev_c,
                    new_confidence_weight=new_c,
                    model_version=self.model_version,
                )
                self.events.append(event)
            self.kelly_multiplier = new_k
            self.confidence_weight = new_c
            self.degraded = True
        else:
            # Recovery path: restore base (bounded / reversible).
            self.kelly_multiplier = self.base_kelly_multiplier
            self.confidence_weight = self.base_confidence_weight
            self.degraded = False
        return self.status()

    def status(self) -> dict[str, Any]:
        brier = rolling_brier(self.history)
        return {
            "brier_score": brier,
            "threshold": self.threshold,
            "degraded": self.degraded,
            "kelly_multiplier": self.kelly_multiplier,
            "confidence_weight": self.confidence_weight,
            "model_version": self.model_version,
            "events": [
                {
                    "timestamp": e.timestamp,
                    "brier_score": e.brier_score,
                    "previous_kelly_multiplier": e.previous_kelly_multiplier,
                    "new_kelly_multiplier": e.new_kelly_multiplier,
                    "previous_confidence_weight": e.previous_confidence_weight,
                    "new_confidence_weight": e.new_confidence_weight,
                    "model_version": e.model_version,
                    "reversible": e.reversible,
                    "weakens_hard_risk_limits": e.weakens_hard_risk_limits,
                }
                for e in self.events
            ],
            "weakens_hard_risk_limits": False,
            "llm_can_override": False,
            "comparison": (
                "above"
                if brier is not None and brier > self.threshold
                else "equal"
                if brier is not None and brier == self.threshold
                else "below"
                if brier is not None
                else "unknown"
            ),
        }
