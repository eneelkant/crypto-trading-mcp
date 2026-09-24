from __future__ import annotations

from typing import Sequence

from crypto_trading_mcp.risk.models import RiskReasonCode


def pearson_correlation(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    n = min(len(xs), len(ys))
    if n < 3:
        return None
    x = list(xs[-n:])
    y = list(ys[-n:])
    mx = sum(x) / n
    my = sum(y) / n
    num = sum((a - mx) * (b - my) for a, b in zip(x, y, strict=True))
    denx = sum((a - mx) ** 2 for a in x) ** 0.5
    deny = sum((b - my) ** 2 for b in y) ** 0.5
    if denx == 0 or deny == 0:
        return None
    return num / (denx * deny)


class CorrelationFilter:
    """Reject new exposure when correlation to existing book is too high."""

    def __init__(self, max_correlation: float = 0.85) -> None:
        self.max_correlation = max_correlation

    def evaluate(
        self,
        candidate_returns: Sequence[float],
        existing_returns: dict[str, Sequence[float]],
    ) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        for symbol, series in existing_returns.items():
            corr = pearson_correlation(candidate_returns, series)
            if corr is not None and abs(corr) >= self.max_correlation:
                reasons.append("CORRELATION_LIMIT")
                reasons.append(f"corr:{symbol}:{corr:.3f}")
        return (not reasons), reasons
