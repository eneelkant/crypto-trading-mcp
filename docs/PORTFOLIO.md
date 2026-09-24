# Portfolio

Deterministic accounting portfolio (`PortfolioManager`).

Tracks:

- cash, equity, available cash
- positions (LONG/SHORT conceptual)
- average entry, quantity, market value
- realized / unrealized P&L
- fees
- exposure
- daily P&L
- drawdown

Phase 4 does **not** place exchange orders. Portfolio mutations are for testing/accounting and future paper trading.

## CLI

```bash
trader portfolio
```
