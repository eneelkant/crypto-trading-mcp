from __future__ import annotations

from crypto_trading_mcp.learning.config import LearningConfig


def kelly_fraction(p: float, b: float) -> float:
    """f* = (p*b - q) / b ; b is win/loss payoff ratio."""
    if b <= 0:
        return 0.0
    q = 1.0 - p
    raw = (p * b - q) / b
    return max(0.0, raw)


def bounded_kelly_multiplier(
    *,
    win_probability: float,
    payoff_ratio: float,
    config: LearningConfig,
    calibration_degraded: bool = False,
) -> dict[str, float | bool]:
    full = kelly_fraction(win_probability, payoff_ratio)
    base = config.kelly_degraded_fraction if calibration_degraded else config.kelly_base_fraction
    # fractional kelly
    fractional = full * base
    # Learning may reduce but never exceed configured max multiplier of 1.0 relative scale
    multiplier = min(config.kelly_max_multiplier, max(config.kelly_min_multiplier, base if full <= 0 else min(1.0, fractional / max(full, 1e-9) if full > 0 else base)))
    # Simpler deterministic mapping: use base or degraded as multiplier directly when full kelly computed
    multiplier = config.kelly_degraded_fraction if calibration_degraded else config.kelly_base_fraction
    multiplier = min(config.kelly_max_multiplier, max(config.kelly_min_multiplier, multiplier))
    return {
        "full_kelly": full,
        "fractional_kelly": full * multiplier,
        "kelly_multiplier": multiplier,
        "calibration_degraded": calibration_degraded,
        "can_override_risk_limits": False,
    }
