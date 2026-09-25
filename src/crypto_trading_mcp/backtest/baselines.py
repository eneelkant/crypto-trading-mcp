from __future__ import annotations

from typing import Any, Sequence

from crypto_trading_mcp.backtest.models import NormalizedCandle
from crypto_trading_mcp.market.indicators import sma


def buy_and_hold(candles: Sequence[NormalizedCandle], *, initial_capital: float = 100_000.0) -> dict[str, Any]:
    if len(candles) < 2:
        return {"benchmark": "BUY_AND_HOLD", "net_pnl": 0.0, "return_pct": 0.0, "trades": 1}
    qty = initial_capital / candles[0].close
    final = qty * candles[-1].close
    net = final - initial_capital
    return {
        "benchmark": "BUY_AND_HOLD",
        "initial_capital": initial_capital,
        "final_equity": final,
        "net_pnl": net,
        "return_pct": (net / initial_capital) * 100.0,
        "trade_count": 1,
        "disclaimer": "Baseline comparison only. Not a profitability claim.",
    }


def dca(
    candles: Sequence[NormalizedCandle],
    *,
    initial_capital: float = 100_000.0,
    steps: int = 10,
) -> dict[str, Any]:
    if not candles:
        return {"benchmark": "DCA", "net_pnl": 0.0, "return_pct": 0.0}
    steps = max(1, min(steps, len(candles)))
    slice_idx = [int(i * (len(candles) - 1) / (steps - 1)) for i in range(steps)] if steps > 1 else [0]
    budget = initial_capital / steps
    qty = 0.0
    spent = 0.0
    for idx in slice_idx:
        px = candles[idx].close
        qty += budget / px
        spent += budget
    final = qty * candles[-1].close
    net = final - spent
    return {
        "benchmark": "DCA",
        "initial_capital": initial_capital,
        "final_equity": final,
        "net_pnl": net,
        "return_pct": (net / initial_capital) * 100.0,
        "trade_count": steps,
        "disclaimer": "Baseline comparison only. Not a profitability claim.",
    }


def simple_moving_average(
    candles: Sequence[NormalizedCandle],
    *,
    initial_capital: float = 100_000.0,
    period: int = 20,
) -> dict[str, Any]:
    if len(candles) <= period:
        return {"benchmark": "SIMPLE_MOVING_AVERAGE", "net_pnl": 0.0, "return_pct": 0.0, "trade_count": 0}
    closes = [c.close for c in candles]
    series = sma(closes, period)
    cash = initial_capital
    qty = 0.0
    trades = 0
    for i in range(period, len(candles)):
        mid = series[i]
        prev = series[i - 1]
        if mid is None or prev is None:
            continue
        px = candles[i].close
        # Cross above → buy; cross below → sell
        if prev <= closes[i - 1] and mid > px and qty == 0 and cash > 0:
            qty = cash / px
            cash = 0.0
            trades += 1
        elif prev >= closes[i - 1] and mid < px and qty > 0:
            cash = qty * px
            qty = 0.0
            trades += 1
    final = cash + qty * candles[-1].close
    net = final - initial_capital
    return {
        "benchmark": "SIMPLE_MOVING_AVERAGE",
        "initial_capital": initial_capital,
        "final_equity": final,
        "net_pnl": net,
        "return_pct": (net / initial_capital) * 100.0,
        "trade_count": trades,
        "disclaimer": "Baseline comparison only. Not a profitability claim.",
    }


def run_baselines(
    candles: Sequence[NormalizedCandle],
    *,
    initial_capital: float = 100_000.0,
) -> dict[str, Any]:
    return {
        "BUY_AND_HOLD": buy_and_hold(candles, initial_capital=initial_capital),
        "DCA": dca(candles, initial_capital=initial_capital),
        "SIMPLE_MOVING_AVERAGE": simple_moving_average(candles, initial_capital=initial_capital),
        "TRADING_MODE": "PAPER",
        "REAL_MONEY": "DISABLED",
        "note": "Baselines reported independently for comparison; strategies are not optimized against them.",
    }
