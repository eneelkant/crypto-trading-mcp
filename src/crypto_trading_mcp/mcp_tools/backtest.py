"""Phase 6 backtest MCP tools — simulation/read-only only."""

from __future__ import annotations

from typing import Any

from crypto_trading_mcp.backtest.baselines import run_baselines
from crypto_trading_mcp.backtest.data import generate_synthetic_candles
from crypto_trading_mcp.backtest.engine import BacktestEngine
from crypto_trading_mcp.backtest.prediction import evaluate_prediction_rows
from crypto_trading_mcp.backtest.reporting import summarize_result, write_json_report
from crypto_trading_mcp.backtest.store import BacktestStore
from crypto_trading_mcp.backtest.walk_forward import WalkForwardValidator
from crypto_trading_mcp.config.settings import get_settings
from crypto_trading_mcp.exchange.exceptions import LiveExecutionBlocked


class BacktestToolSurface:
    def __init__(self, store: BacktestStore | None = None) -> None:
        self.store = store or BacktestStore()
        self.engine = BacktestEngine()

    def _assert_paper(self) -> None:
        settings = get_settings()
        if settings.trading_mode != "paper" or settings.live_trading_enabled:
            raise LiveExecutionBlocked("Backtest tools require paper mode with live disabled")

    def run_backtest(
        self,
        symbol: str,
        *,
        strategy_id: str = "momentum_breakout_crypto",
        timeframe: str = "1h",
        bars: int = 120,
    ) -> dict[str, Any]:
        self._assert_paper()
        candles = generate_synthetic_candles(symbol=symbol.upper(), timeframe=timeframe, n=bars)
        result = self.engine.run(
            candles=candles,
            strategy_id=strategy_id,
            symbol=symbol.upper(),
            timeframe=timeframe,
            signal_params={"volume_mult": 1.0},
        )
        self.store.save_result(result)
        write_json_report(result)
        return summarize_result(result)

    def run_walk_forward(
        self,
        symbol: str,
        *,
        strategy_id: str = "momentum_breakout_crypto",
        timeframe: str = "1h",
        bars: int = 120,
    ) -> dict[str, Any]:
        self._assert_paper()
        candles = generate_synthetic_candles(symbol=symbol.upper(), timeframe=timeframe, n=bars)
        return WalkForwardValidator(self.engine).run(
            candles, strategy_id=strategy_id, symbol=symbol.upper(), timeframe=timeframe
        )

    def get_backtest_result(self, backtest_id: str) -> dict[str, Any]:
        return self.store.get_run(backtest_id) or {"error": "NOT_FOUND", "backtest_id": backtest_id}

    def get_backtest_report(self, backtest_id: str) -> dict[str, Any]:
        return self.get_backtest_result(backtest_id)

    def compare_backtests(self, backtest_ids: list[str]) -> dict[str, Any]:
        rows = []
        for bid in backtest_ids:
            payload = self.store.get_run(bid)
            if not payload:
                rows.append({"backtest_id": bid, "error": "NOT_FOUND"})
                continue
            identity = payload.get("identity") or {}
            metrics = payload.get("metrics") or {}
            rows.append(
                {
                    "backtest_id": bid,
                    "strategy_id": identity.get("strategy_id"),
                    "return_pct": metrics.get("return_pct"),
                    "max_drawdown": metrics.get("max_drawdown"),
                    "sharpe_ratio": metrics.get("sharpe_ratio"),
                    "trade_count": metrics.get("trade_count"),
                    "partition": identity.get("partition"),
                }
            )
        return {
            "comparisons": rows,
            "note": "Factual metric comparison only; no ranking as best/safe/guaranteed.",
            "TRADING_MODE": "PAPER",
        }

    def run_benchmark(self, symbol: str, *, timeframe: str = "1h", bars: int = 120) -> dict[str, Any]:
        self._assert_paper()
        candles = generate_synthetic_candles(symbol=symbol.upper(), timeframe=timeframe, n=bars)
        return run_baselines(candles)

    def run_prediction_backtest(self, rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        self._assert_paper()
        rows = rows or [
            {
                "predicted_probability": 0.62,
                "ensemble_probability": 0.62,
                "market_probability": 0.55,
                "outcome": 1,
                "quantity": 10,
                "model": "ensemble",
                "weight": 1.0,
                "confidence": 0.7,
            }
        ]
        return evaluate_prediction_rows(rows)
