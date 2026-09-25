from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Sequence


def _holding_hours(trade: dict[str, Any]) -> float | None:
    entry = trade.get("entry_time")
    exit_ = trade.get("exit_time")
    if not entry or not exit_:
        return None
    try:
        e = datetime.fromisoformat(str(entry).replace("Z", "+00:00"))
        x = datetime.fromisoformat(str(exit_).replace("Z", "+00:00"))
        return max(0.0, (x - e).total_seconds() / 3600.0)
    except ValueError:
        return None


def compute_performance(
    trades: Sequence[dict[str, Any]],
    *,
    starting_equity: float = 10_000.0,
) -> dict[str, Any]:
    pnls = [float(t.get("net_pnl") or 0.0) for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross = sum(float(t.get("gross_pnl") or 0.0) for t in trades)
    fees = sum(float(t.get("fees") or 0.0) for t in trades)
    slip = sum(float(t.get("slippage") or 0.0) for t in trades)
    tax = sum(float(t.get("tax_friction") or 0.0) for t in trades)
    net = sum(pnls)
    after_fee = gross - fees
    after_tax = net - tax
    win_rate = (len(wins) / len(pnls)) if pnls else 0.0
    gross_wins = sum(wins)
    gross_losses = abs(sum(losses))
    profit_factor = (gross_wins / gross_losses) if gross_losses > 0 else None
    equity = starting_equity
    peak = starting_equity
    max_dd = 0.0
    curve: list[float] = []
    for p in pnls:
        equity += p
        curve.append(equity)
        peak = max(peak, equity)
        dd = (peak - equity) / peak if peak else 0.0
        max_dd = max(max_dd, dd)
    turnover = sum(
        abs(float(t.get("quantity") or 0) * float(t.get("exit") or t.get("entry") or 0))
        for t in trades
    )
    holdings = [h for h in (_holding_hours(t) for t in trades) if h is not None]
    avg_hold = (sum(holdings) / len(holdings)) if holdings else None
    # Sharpe / Sortino on per-trade returns (paper approximation; not live performance claims).
    rets = [p / starting_equity for p in pnls] if starting_equity else []
    sharpe = None
    sortino = None
    if len(rets) >= 2:
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
        std = math.sqrt(var) if var > 0 else 0.0
        sharpe = (mean / std) if std > 0 else None
        downside = [min(0.0, r - 0.0) for r in rets]
        dvar = sum(d**2 for d in downside) / (len(downside) - 1)
        dstd = math.sqrt(dvar) if dvar > 0 else 0.0
        sortino = (mean / dstd) if dstd > 0 else None
    return {
        "trade_count": len(trades),
        "number_of_trades": len(trades),
        "win_rate": win_rate,
        "gross_pnl": gross,
        "fees": fees,
        "slippage": slip,
        "tax_friction": tax,
        "simulated_tds": tax,
        "net_pnl": net,
        "after_fee_pnl": after_fee,
        "after_simulated_tax_pnl": after_tax,
        "return": (net / starting_equity) if starting_equity else 0.0,
        "return_pct": ((net / starting_equity) * 100.0) if starting_equity else 0.0,
        "max_drawdown": max_dd,
        "maximum_drawdown": max_dd,
        "daily_loss": None,
        "profit_factor": profit_factor,
        "average_trade": (net / len(pnls)) if pnls else 0.0,
        "average_winner": (sum(wins) / len(wins)) if wins else 0.0,
        "average_loser": (sum(losses) / len(losses)) if losses else 0.0,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "turnover": turnover,
        "gross_turnover": turnover,
        "exposure": None,
        "holding_period_hours": avg_hold,
        "average_holding_period": avg_hold,
        "disclaimer": (
            "Paper metrics only. Positive paper results do not imply a strategy is profitable live."
        ),
    }


def group_performance(
    trades: Sequence[dict[str, Any]],
    key: str,
    starting_equity: float = 10_000.0,
) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for trade in trades:
        groups.setdefault(str(trade.get(key) or "unknown"), []).append(trade)
    return {k: compute_performance(v, starting_equity=starting_equity) for k, v in groups.items()}


def benchmark_placeholder(name: str) -> dict[str, Any]:
    """Architecture hook for later Buy&Hold / DCA / SMA comparison (Phase 6+)."""
    return {
        "benchmark": name,
        "implemented": False,
        "note": "Benchmark comparison scaffolding only; no optimization against benchmarks.",
    }
