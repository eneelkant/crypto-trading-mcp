from __future__ import annotations

import math
from typing import Any, Sequence

from crypto_trading_mcp.backtest.models import EquityPoint
from crypto_trading_mcp.performance.metrics import compute_performance


def _streaks(pnls: Sequence[float]) -> tuple[int, int]:
    max_win = max_loss = cur_w = cur_l = 0
    for p in pnls:
        if p > 0:
            cur_w += 1
            cur_l = 0
            max_win = max(max_win, cur_w)
        elif p < 0:
            cur_l += 1
            cur_w = 0
            max_loss = max(max_loss, cur_l)
        else:
            cur_w = cur_l = 0
    return max_win, max_loss


def compute_backtest_metrics(
    *,
    trades: Sequence[dict[str, Any]],
    equity_curve: Sequence[EquityPoint],
    initial_capital: float,
    fees_total: float,
    slippage_total: float,
) -> dict[str, Any]:
    base = compute_performance(trades, starting_equity=initial_capital)
    final_equity = equity_curve[-1].equity if equity_curve else initial_capital
    net = final_equity - initial_capital
    gross = float(base.get("gross_pnl") or 0.0)
    pnls = [float(t.get("net_pnl") or 0.0) for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    long_n = sum(1 for t in trades if str(t.get("side") or t.get("reason_for_entry") or "").upper() in {"LONG", "BUY"})
    # Prefer explicit side on trade records when present
    long_n = sum(1 for t in trades if str(t.get("side", "")).upper() in {"LONG", "BUY"})
    short_n = sum(1 for t in trades if str(t.get("side", "")).upper() in {"SHORT", "SELL"})
    max_win_streak, max_loss_streak = _streaks(pnls)
    # CAGR approx from calendar span on equity curve
    cagr = None
    if len(equity_curve) >= 2:
        try:
            from datetime import datetime

            t0 = datetime.fromisoformat(equity_curve[0].timestamp.replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(equity_curve[-1].timestamp.replace("Z", "+00:00"))
            years = max((t1 - t0).total_seconds() / (365.25 * 24 * 3600), 1e-9)
            if initial_capital > 0 and final_equity > 0:
                cagr = (final_equity / initial_capital) ** (1 / years) - 1
        except Exception:  # noqa: BLE001
            cagr = None
    # Max drawdown duration (points)
    peak = initial_capital
    dd_start = 0
    max_dd_dur = 0
    in_dd = False
    for i, pt in enumerate(equity_curve):
        if pt.equity >= peak:
            peak = pt.equity
            if in_dd:
                max_dd_dur = max(max_dd_dur, i - dd_start)
                in_dd = False
        else:
            if not in_dd:
                dd_start = i
                in_dd = True
    if in_dd:
        max_dd_dur = max(max_dd_dur, len(equity_curve) - dd_start)

    expectancy = (sum(pnls) / len(pnls)) if pnls else 0.0
    return {
        **base,
        "initial_capital": initial_capital,
        "final_equity": final_equity,
        "gross_pnl": gross,
        "fees": fees_total if fees_total else base.get("fees"),
        "slippage": slippage_total if slippage_total else base.get("slippage"),
        "net_pnl": net,
        "return_pct": (net / initial_capital * 100.0) if initial_capital else 0.0,
        "cagr": cagr,
        "loss_rate": (len(losses) / len(pnls)) if pnls else 0.0,
        "expectancy": expectancy,
        "maximum_drawdown_duration_bars": max_dd_dur,
        "long_trades": long_n,
        "short_trades": short_n,
        "largest_winning_trade": max(wins) if wins else 0.0,
        "largest_losing_trade": min(losses) if losses else 0.0,
        "consecutive_wins": max_win_streak,
        "consecutive_losses": max_loss_streak,
        "disclaimer": (
            "Factual metrics for the tested dataset/period only. "
            "Historical backtest results do not guarantee future performance."
        ),
    }


def compute_risk_metrics(
    *,
    equity_curve: Sequence[EquityPoint],
    trades: Sequence[dict[str, Any]],
    risk_rejections: int,
    exposures: Sequence[float] | None = None,
) -> dict[str, Any]:
    exposures = list(exposures or [])
    pnls = [float(t.get("net_pnl") or 0.0) for t in trades]
    daily_losses = sum(1 for p in equity_curve if p.daily_pnl < 0)
    return {
        "maximum_exposure": max(exposures) if exposures else None,
        "average_exposure": (sum(exposures) / len(exposures)) if exposures else None,
        "maximum_position_size": max(
            (abs(float(t.get("quantity") or 0)) for t in trades), default=0.0
        ),
        "largest_losing_trade": min(pnls) if pnls else 0.0,
        "largest_winning_trade": max(pnls) if pnls else 0.0,
        "consecutive_wins": _streaks(pnls)[0],
        "consecutive_losses": _streaks(pnls)[1],
        "daily_loss_events": daily_losses,
        "risk_rejection_count": risk_rejections,
    }


def sharpe_from_returns(returns: Sequence[float]) -> float | None:
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    std = math.sqrt(var) if var > 0 else 0.0
    return (mean / std) if std > 0 else None
