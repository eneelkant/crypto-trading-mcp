from __future__ import annotations

import random
from typing import Any, Sequence


def monte_carlo_trade_resample(
    trade_pnls: Sequence[float],
    *,
    iterations: int = 500,
    seed: int = 42,
    starting_equity: float = 100_000.0,
) -> dict[str, Any]:
    """Optional resampling of historical trade outcomes (simulation, not prediction)."""
    if not trade_pnls:
        return {
            "enabled": True,
            "iterations": 0,
            "note": "No trades to resample",
            "label": "simulation_not_prediction",
        }
    rng = random.Random(seed)
    finals: list[float] = []
    max_dds: list[float] = []
    losing_streaks: list[int] = []
    n = len(trade_pnls)
    for _ in range(iterations):
        sample = [rng.choice(list(trade_pnls)) for _ in range(n)]
        equity = starting_equity
        peak = starting_equity
        max_dd = 0.0
        streak = best_streak = 0
        for p in sample:
            equity += p
            peak = max(peak, equity)
            dd = (peak - equity) / peak if peak else 0.0
            max_dd = max(max_dd, dd)
            if p < 0:
                streak += 1
                best_streak = max(best_streak, streak)
            else:
                streak = 0
        finals.append(equity)
        max_dds.append(max_dd)
        losing_streaks.append(best_streak)
    finals_sorted = sorted(finals)
    return {
        "enabled": True,
        "iterations": iterations,
        "seed": seed,
        "label": "simulation_not_prediction",
        "final_equity": {
            "p05": finals_sorted[int(0.05 * (iterations - 1))],
            "p50": finals_sorted[int(0.50 * (iterations - 1))],
            "p95": finals_sorted[int(0.95 * (iterations - 1))],
            "mean": sum(finals) / iterations,
        },
        "max_drawdown": {
            "mean": sum(max_dds) / iterations,
            "p95": sorted(max_dds)[int(0.95 * (iterations - 1))],
        },
        "losing_streak": {
            "mean": sum(losing_streaks) / iterations,
            "max": max(losing_streaks),
        },
        "disclaimer": "Monte Carlo resampling is a simulation of historical trade outcomes, not a forecast.",
    }
