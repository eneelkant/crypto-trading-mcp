# Paper Trading

## Safety

```text
TRADING MODE: PAPER
REAL MONEY: DISABLED
TRADING_MODE=paper
LIVE_TRADING_ENABLED=false
```

No Coinbase / Delta / Polymarket / Kalshi authenticated execution in Phase 5.
See also `PAPER_TRADING_SAFETY.md`.

## Architecture

```text
Market Data
 → Market Intelligence / Technical / Trend / Sentiment / On-Chain / Macro
 → Strategy
 → Bull / Bear / Consensus
 → Risk Manager
 → Portfolio Manager
 → Trade Planner
 → Paper Exchange
 → Fill Engine
 → Portfolio Update
 → Performance Monitoring
 → Reflection/Learning hooks
```

Paper path: **proposal → deterministic validation → paper execution**.
No `WAITING_FOR_HUMAN_APPROVAL` required state.

## Components

| Module | Role |
|--------|------|
| `exchange/paper.py` | Matching, fees, slippage, stops/TP, trailing |
| `exchange/fees.py` / `slippage.py` | Configurable engines |
| `exchange/prediction.py` | Prediction-contract book + settlement |
| `paper/engine.py` | Autonomous paper loop |
| `paper/session.py` | Paper sessions |
| `paper/persistence.py` | In-memory / SQLite store |
| `paper/replay.py` | `MarketDataReplay` + deterministic replay |
| `compliance/policy.py` | Compliance + tax simulation |
| `performance/metrics.py` | Portfolio/strategy metrics |

## Configuration

Primary: `config/paper_trading.yaml` (falls back to `config/paper.yaml`).

## CLI

```bash
trader paper status|start|stop|reset|restart
trader paper run BTC/USD
trader paper trades|orders|portfolio|performance
trader paper replay
trader paper predict ELECTION1
```

## MCP tools

```text
run_paper_trade
get_paper_status
get_paper_orders
get_paper_trades
get_paper_portfolio
get_paper_performance
reset_paper_account
```

## Kill switch

Presence of a `STOP` file in the repo root activates the kill switch and blocks new
paper trades. Restart with `trader paper restart` after removal.

## Limitations

Paper results are simulated. Positive paper P&L does **not** mean a strategy is
profitable in live markets. Tax/TDS outputs are configuration-driven simulations only.
