# Performance Metrics

Backtests report factual measurements for the tested dataset and period.

## Trading metrics

Initial capital, final equity, gross/net P&L, return %, CAGR (when span allows),
win/loss rate, profit factor, Sharpe, Sortino, max drawdown / duration, average trade,
expectancy, fees, slippage, turnover, trade counts, holding period, exposure,
daily/monthly aggregates where equity points permit.

## Risk metrics

Maximum/average exposure, largest win/loss, consecutive wins/losses, daily loss events,
risk rejection count.

## Prediction markets

Brier score, log loss, calibration, edge, ROI — **not** mixed with trading Sharpe.

## Language

Reports must not claim:

```text
best strategy / guaranteed profitable / will make money / safe strategy
```

Example factual line:

```text
Net return: X% | Maximum drawdown: Y% | Sharpe: Z | Trade count: N
```

Historical backtest results do not guarantee future performance.
