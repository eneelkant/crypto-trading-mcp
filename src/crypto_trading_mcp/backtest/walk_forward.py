from __future__ import annotations

from typing import Any

from crypto_trading_mcp.backtest.config import BacktestConfig, load_backtest_config, walk_forward_settings
from crypto_trading_mcp.backtest.engine import BacktestEngine
from crypto_trading_mcp.backtest.models import DataPartition, NormalizedCandle
from crypto_trading_mcp.backtest.splits import walk_forward_windows


class WalkForwardValidator:
    """Walk-forward validation without optimizing on OOS."""

    def __init__(self, engine: BacktestEngine | None = None, config: BacktestConfig | None = None) -> None:
        self.config = config or load_backtest_config()
        self.engine = engine or BacktestEngine(config=self.config)
        self.settings = walk_forward_settings(self.config)

    def run(
        self,
        candles: list[NormalizedCandle],
        *,
        strategy_id: str,
        symbol: str | None = None,
        timeframe: str | None = None,
    ) -> dict[str, Any]:
        windows = walk_forward_windows(
            candles,
            training_days=int(self.settings["training_days"]),
            validation_days=int(self.settings["validation_days"]),
            test_days=int(self.settings["test_days"]),
            step_days=int(self.settings["step_days"]),
        )
        folds: list[dict[str, Any]] = []
        for i, win in enumerate(windows):
            fold: dict[str, Any] = {"fold": i}
            for key, part in (
                ("train", DataPartition.TRAIN),
                ("validation", DataPartition.VALIDATION),
                ("out_of_sample", DataPartition.OUT_OF_SAMPLE),
            ):
                split = win[key if key != "out_of_sample" else "out_of_sample"]
                # Prevent leakage: each partition run is isolated.
                result = self.engine.run(
                    candles=list(split.candles),
                    strategy_id=strategy_id,
                    symbol=symbol,
                    timeframe=timeframe,
                    partition=part,
                )
                fold[key] = {
                    "partition": part.value,
                    "start": split.start.isoformat(),
                    "end": split.end.isoformat(),
                    "backtest_id": result.identity.backtest_id,
                    "metrics": {
                        "net_pnl": result.metrics.get("net_pnl"),
                        "return_pct": result.metrics.get("return_pct"),
                        "max_drawdown": result.metrics.get("max_drawdown"),
                        "sharpe_ratio": result.metrics.get("sharpe_ratio"),
                        "trade_count": result.metrics.get("trade_count"),
                    },
                    "structural_hash": result.structural_hash,
                }
            folds.append(fold)
        return {
            "strategy_id": strategy_id,
            "folds": folds,
            "settings": self.settings,
            "note": (
                "Validation metrics are not out-of-sample. "
                "Do not optimize parameters using the OOS window."
            ),
            "TRADING_MODE": "PAPER",
            "REAL_MONEY": "DISABLED",
            "disclaimer": "Historical walk-forward results do not guarantee future performance.",
        }
