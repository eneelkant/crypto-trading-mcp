from __future__ import annotations

from typing import Any

from crypto_trading_mcp.backtest.engine import BacktestEngine
from crypto_trading_mcp.backtest.models import NormalizedCandle


def parameter_sensitivity(
    engine: BacktestEngine,
    candles: list[NormalizedCandle],
    *,
    strategy_id: str = "momentum_breakout_crypto",
    lookbacks: list[int] | None = None,
    atr_multipliers: list[float] | None = None,
) -> list[dict[str, Any]]:
    """Nearby parameter sweeps for fragility detection — does not auto-select best."""
    lookbacks = lookbacks or [18, 20, 22]
    atr_multipliers = atr_multipliers or [1.8, 2.0, 2.2]
    rows: list[dict[str, Any]] = []
    for lb in lookbacks:
        for atr_m in atr_multipliers:
            result = engine.run(
                candles=candles,
                strategy_id=strategy_id,
                signal_params={"lookback": lb, "atr_mult": atr_m, "volume_mult": 1.0},
            )
            rows.append(
                {
                    "parameter": "donchian_lookback+atr_mult",
                    "value": {"lookback": lb, "atr_mult": atr_m},
                    "trade_count": result.metrics.get("trade_count"),
                    "return_pct": result.metrics.get("return_pct"),
                    "drawdown": result.metrics.get("max_drawdown"),
                    "sharpe": result.metrics.get("sharpe_ratio"),
                    "profit_factor": result.metrics.get("profit_factor"),
                    "backtest_id": result.identity.backtest_id,
                    "note": "Sensitivity only; best parameter is not auto-selected.",
                }
            )
    return rows
