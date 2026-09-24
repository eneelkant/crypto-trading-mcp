# Crypto Trading MCP

Experimental multi-agent crypto **market analysis** platform with an MCP server.

```text
This software is experimental trading infrastructure.

Cryptocurrency trading involves substantial risk.

Past performance and backtesting do not guarantee future results.

Live trading is disabled by default.

Autonomous trading can result in financial loss.

Users are responsible for determining whether and how to use live trading.
```

## Current phase (5)

- Unified **PaperExchange** with fees, slippage, trailing stops, prediction settlement
- Autonomous paper loop: agents → consensus → risk → trade plan → paper fill → P&L
- Sessions, SQLite/in-memory persistence, deterministic market-data replay
- `trader paper …` CLI + paper-safe MCP tools
- **Still no live/authenticated execution**

Defaults:

```env
TRADING_MODE=paper
LIVE_TRADING_ENABLED=false
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

## Run MCP server

```bash
python -m crypto_trading_mcp
```

## CLI

```bash
trader status
trader agents
trader risk
trader portfolio
trader trades
trader performance
trader analyze BTC/USD
trader propose BTC-USD
trader paper start
trader paper run BTC/USD --price 50000
trader paper portfolio
trader paper performance
trader paper replay
```

## Tests

```bash
pytest -q
```

## Docs

- `docs/PAPER_TRADING.md`
- `docs/PAPER_TRADING_SAFETY.md`
- `docs/EXCHANGE_ARCHITECTURE.md`
- `docs/ORDER_LIFECYCLE.md`
- `docs/SLIPPAGE_AND_FEES.md`
- `docs/PREDICTION_MARKETS.md`
- `docs/OPERATIONS.md`
- `docs/ARCHITECTURE_AUDIT.md`
- `docs/AGENTS.md`
- `docs/STRATEGIES.md`
- `docs/RISK_MANAGEMENT.md`
- `docs/PORTFOLIO.md`
- `docs/TRADE_PLANNING.md`
