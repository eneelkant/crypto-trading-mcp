# Portfolio

Deterministic accounting portfolio (`PortfolioManager`) integrated with `PaperExchange`.

Tracks:

- cash, equity, available cash
- positions (crypto spot, equity/ETF shares, futures abstraction, prediction contracts)
- average entry, quantity, market value
- realized / unrealized P&L
- fees, exposure, daily P&L, drawdown

## Strategy books

`PaperTradingEngine.strategy_book_report()` reports overall portfolio plus per-strategy and per-asset-class views.

## CLI

```bash
trader portfolio
trader paper positions
trader paper performance
```
