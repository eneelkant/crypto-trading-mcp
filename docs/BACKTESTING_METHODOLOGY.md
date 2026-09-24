# Backtesting Methodology

## Execution assumptions

- Same PaperExchange fill, fee, slippage, stop, and portfolio rules as paper trading
- Decisions on **closed candles** only (`closed_candle_only: true`)
- At timestamp T, only candles with timestamp ≤ T are visible

## Lookahead prevention

```text
Candle T
→ indicators from candles ≤ T
→ signal
→ risk + plan
→ paper order/fill
→ advance to T+1
```

Future OHLC, indicators, labels, sentiment, or fundamentals must not influence T.

## Costs

When enabled, reports separate:

- Gross P&L
- Fees
- Slippage
- Net P&L

Primary results use net figures when transaction costs are enabled.

## Tax / India simulation

Uses Phase 5 compliance simulation. Default for backtests:

```text
tax_enabled=false
```

unless explicitly configured. Outputs are not legal advice.

## Reproducibility

Identical data, strategy config, risk config, backtest config, and seed must produce
identical signals, orders, fills, equity curve, and metrics.

## Disclaimer

Historical backtest results do not guarantee future performance.
This phase measures and reports — it does not auto-optimize or trade live.
