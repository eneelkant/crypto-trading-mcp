from __future__ import annotations

from typing import Any, Sequence

from crypto_trading_mcp.backtest.models import BacktestWarning


def detect_overfitting_warnings(
    metrics: dict[str, Any],
    risk_metrics: dict[str, Any],
    trades: Sequence[dict[str, Any]],
) -> list[BacktestWarning]:
    warnings: list[BacktestWarning] = []
    trade_count = int(metrics.get("trade_count") or 0)
    if trade_count < 5:
        warnings.append(
            BacktestWarning(
                code="LOW_TRADE_COUNT",
                message="Very low trade count; results may be fragile.",
                details={"trade_count": trade_count},
            )
        )
    if trade_count == 1:
        warnings.append(
            BacktestWarning(
                code="SINGLE_TRADE_DEPENDENCY",
                message="Performance depends on a single trade.",
                details={"trade_count": trade_count},
            )
        )
    max_dd = float(metrics.get("max_drawdown") or metrics.get("maximum_drawdown") or 0.0)
    if max_dd >= 0.25:
        warnings.append(
            BacktestWarning(
                code="LARGE_DRAWDOWN",
                message="Maximum drawdown is large relative to capital.",
                details={"max_drawdown": max_dd},
            )
        )
    turnover = float(metrics.get("turnover") or metrics.get("gross_turnover") or 0.0)
    net = abs(float(metrics.get("net_pnl") or 0.0))
    if turnover > 0 and net > 0 and turnover / max(net, 1e-9) > 50:
        warnings.append(
            BacktestWarning(
                code="HIGH_TURNOVER",
                message="Turnover is high relative to net P&L.",
                details={"turnover": turnover, "net_pnl": net},
            )
        )
    pnls = [float(t.get("net_pnl") or 0.0) for t in trades]
    if pnls:
        total = sum(abs(p) for p in pnls) or 1.0
        top = max(abs(p) for p in pnls)
        if top / total > 0.8:
            warnings.append(
                BacktestWarning(
                    code="RETURN_CONCENTRATION",
                    message="Extreme return concentration in one trade.",
                    details={"top_abs_pnl": top, "sum_abs_pnl": total},
                )
            )
    return warnings


def train_oos_gap_warning(train_return: float, oos_return: float) -> BacktestWarning | None:
    gap = train_return - oos_return
    if gap > 20:  # percentage points
        return BacktestWarning(
            code="TRAIN_OOS_GAP",
            message="Large train vs out-of-sample performance gap.",
            details={"train_return_pct": train_return, "oos_return_pct": oos_return, "gap": gap},
        )
    return None
