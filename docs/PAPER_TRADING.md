# Paper Trading

## Safety

```text
TRADING MODE: PAPER
REAL MONEY: DISABLED
TRADING_MODE=paper
LIVE_TRADING_ENABLED=false
```

No Coinbase / Delta / Polymarket / Kalshi authenticated execution in Phase 5.

## Architecture

```text
Market Data
 → Strategy Selection
 → Analysis / Consensus (optional)
 → Trade Planner
 → Compliance Policy
 → Correlation Filter
 → Risk Engine
 → PaperExchange
 → Portfolio / Monitoring / Performance
```

## Components

| Module | Role |
|--------|------|
| `exchange/paper.py` | Deterministic matching, fees, slippage, stops/TP |
| `exchange/prediction.py` | Prediction-contract book + settlement |
| `paper/engine.py` | Autonomous paper loop |
| `paper/replay.py` | Deterministic replay |
| `compliance/policy.py` | Compliance + tax simulation |
| `performance/metrics.py` | Portfolio/strategy metrics |

## CLI

```bash
trader paper status
trader paper start
trader paper stop
trader paper run BTC/USD
trader paper run SPY
trader paper run GLD
trader paper positions
trader paper orders
trader paper trades
trader paper performance
trader paper reset
trader paper markets
trader paper predict ELECTION1
```

## Kill switch

Presence of a `STOP` file in the repo root activates the kill switch and blocks new paper trades.
