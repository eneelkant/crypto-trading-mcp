# Slippage and Fees

Configuration lives in `config/paper_trading.yaml` (and legacy `config/paper.yaml`).

## Slippage

```yaml
slippage:
  enabled: true
  model: fixed_bps   # fixed_bps | percentage | volatility_adjusted | volume_adjusted
  default_bps: 5
  max_bps: 50
```

Market buy fill:

```text
fill_price = market_price + simulated_slippage
```

Every fill records absolute slippage and bps via `SlippageEngine`.

## Fees

```yaml
fees:
  default_rate: 0.001
  maker_bps: 10
  taker_bps: 20
  by_asset_class: {}
  by_exchange: {}
```

Fees are recorded independently from P&L on the portfolio (`fees_paid`) and on each fill.
Schedules are configurable per asset class and exchange; nothing is hard-coded that cannot
be changed later.

## Reporting

Performance metrics distinguish:

- gross P&L
- after-fee P&L
- net P&L
- after-simulated-tax/TDS P&L
