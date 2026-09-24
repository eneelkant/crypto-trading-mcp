from __future__ import annotations

from typing import Any, Sequence


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
    win_rate = (len(wins) / len(pnls)) if pnls else 0.0
    gross_wins = sum(wins)
    gross_losses = abs(sum(losses))
    profit_factor = (gross_wins / gross_losses) if gross_losses > 0 else None
    # Simple equity curve drawdown
    equity = starting_equity
    peak = starting_equity
    max_dd = 0.0
    for p in pnls:
        equity += p
        peak = max(peak, equity)
        dd = (peak - equity) / peak if peak else 0.0
        max_dd = max(max_dd, dd)
    turnover = sum(abs(float(t.get("quantity") or 0) * float(t.get("exit") or t.get("entry") or 0)) for t in trades)
    return {
        "trade_count": len(trades),
        "win_rate": win_rate,
        "gross_pnl": gross,
        "fees": fees,
        "slippage": slip,
        "tax_friction": tax,
        "net_pnl": net,
        "return": (net / starting_equity) if starting_equity else 0.0,
        "max_drawdown": max_dd,
        "profit_factor": profit_factor,
        "average_trade": (net / len(pnls)) if pnls else 0.0,
        "turnover": turnover,
        "exposure": None,
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
