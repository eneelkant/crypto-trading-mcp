from __future__ import annotations

from crypto_trading_mcp.exchange.prediction import brier_score


def rolling_brier(pairs: list[tuple[float, int]]) -> float | None:
    """pairs: (predicted_probability, outcome 0/1)."""
    if not pairs:
        return None
    return sum(brier_score(p, o) for p, o in pairs) / len(pairs)


def log_loss(probability: float, outcome: int) -> float:
    import math

    p = min(max(probability, 1e-12), 1 - 1e-12)
    return -(outcome * math.log(p) + (1 - outcome) * math.log(1 - p))


def rolling_log_loss(pairs: list[tuple[float, int]]) -> float | None:
    if not pairs:
        return None
    return sum(log_loss(p, o) for p, o in pairs) / len(pairs)
