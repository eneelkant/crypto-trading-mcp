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

## Current phase (4)

- Strategy reference + knowledge layer (PO3/VWAP multi-model)
- Deterministic strategy features + confluence
- Risk Engine, Portfolio Manager, Trade Planner
- Circuit breakers + kill switch
- `trader risk|portfolio|propose`
- **Still no trade execution / Coinbase trading / wallet ops**

Defaults:

```env
TRADING_MODE=paper
LIVE_TRADING_ENABLED=false
LLM_PROVIDER=mock
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
trader analyze BTC/USD
trader propose BTC-USD
```

## Tests

```bash
pytest
```

## Docs

- `docs/ARCHITECTURE_AUDIT.md`
- `docs/AGENTS.md`
- `docs/MARKET_INTELLIGENCE.md`
- `docs/ANALYSIS_AGENTS.md`
- `docs/STRATEGIES.md`
- `docs/RISK_MANAGEMENT.md`
- `docs/PORTFOLIO.md`
- `docs/TRADE_PLANNING.md`
