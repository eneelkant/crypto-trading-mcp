from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from crypto_trading_mcp.learning.config import LearningConfig
from crypto_trading_mcp.learning.models import DriftType


@dataclass
class DriftMonitor:
    config: LearningConfig
    events: list[dict[str, Any]] = field(default_factory=list)
    baseline_brier: float | None = None
    baseline_winrate: float | None = None
    recent_brier: float | None = None
    recent_winrate: float | None = None

    def update(
        self,
        *,
        brier: float | None = None,
        winrate: float | None = None,
        feature_shift: float | None = None,
    ) -> list[dict[str, Any]]:
        if not self.config.drift_enabled:
            return []
        detected: list[dict[str, Any]] = []
        if brier is not None:
            if self.baseline_brier is None:
                self.baseline_brier = brier
            self.recent_brier = brier
            if (
                self.baseline_brier is not None
                and brier - self.baseline_brier >= self.config.brier_degrade_delta
            ):
                detected.append(self._event(DriftType.CALIBRATION_DRIFT, {"brier": brier}))
        if winrate is not None:
            if self.baseline_winrate is None:
                self.baseline_winrate = winrate
            self.recent_winrate = winrate
            if (
                self.baseline_winrate is not None
                and self.baseline_winrate - winrate >= self.config.winrate_degrade_delta
            ):
                detected.append(
                    self._event(DriftType.PERFORMANCE_DRIFT, {"winrate": winrate})
                )
        if feature_shift is not None and feature_shift > 0.35:
            detected.append(self._event(DriftType.FEATURE_DRIFT, {"shift": feature_shift}))
        self.events.extend(detected)
        return detected

    def _event(self, drift_type: DriftType, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "drift_type": drift_type.value,
            "payload": payload,
            "action": "WARN_REDUCE_RISK",
            "can_increase_risk": False,
        }

    def status(self) -> dict[str, Any]:
        latest = self.events[-1] if self.events else None
        return {
            "ok": latest is None,
            "latest": latest,
            "count": len(self.events),
            "baseline_brier": self.baseline_brier,
            "recent_brier": self.recent_brier,
        }
