# Backtesting

Phase 6 historical backtesting reuses the Phase 5 **PaperExchange** execution path.

```text
TRADING_MODE=paper
LIVE_TRADING_ENABLED=false
```

Historical backtest results do not guarantee future performance.

## Architecture

```text
Historical Data
 → Backtest Engine
 → Strategy signals (closed candles only)
 → Risk Engine
 → Trade Planner
 → PaperExchange
 → Fill Engine
 → Portfolio
 → Performance Metrics
```

No live adapters are called. `execution_model` must remain `paper_exchange`.

## Configuration

`config/backtesting.yaml` controls capital, fees/slippage inclusion, lookahead guards,
walk-forward windows, baselines, and prediction evaluation thresholds.

## CLI

```bash
trader backtest BTC/USD
trader backtest BTC/USD --strategy MOMENTUM_BREAKOUT_CRYPTO
trader backtest BTC/USD --start 2025-01-01 --end 2026-01-01
trader backtest BTC/USD --json
trader walk-forward BTC/USD
trader backtests
trader backtest-report <backtest_id>
trader benchmark BTC/USD
trader prediction-backtest
```

## MCP

`run_backtest`, `run_walk_forward`, `get_backtest_result`, `get_backtest_report`,
`compare_backtests`, `run_benchmark`, `run_prediction_backtest`

## Limitations

- Offline fixtures / CSV / JSON / mock providers in Phase 6
- LLM agent mode optional and cached; default is deterministic
- No automatic strategy optimization or live deployment
