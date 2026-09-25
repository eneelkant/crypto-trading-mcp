from __future__ import annotations

from crypto_trading_mcp.learning.config import LearningConfig
from crypto_trading_mcp.learning.kelly import bounded_kelly_multiplier


def adapt_position_multiplier(
    *,
    win_probability: float,
    payoff_ratio: float,
    config: LearningConfig,
    calibration_degraded: bool,
) -> float:
    """Learning may reduce sizing multiplier; never increases above configured max."""
    result = bounded_kelly_multiplier(
        win_probability=win_probability,
        payoff_ratio=payoff_ratio,
        config=config,
        calibration_degraded=calibration_degraded,
    )
    return float(result["kelly_multiplier"])
