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

- Deterministic **PaperExchange** (multi-asset + prediction contracts)
- Autonomous paper loop: compliance → risk → paper fill
- Tax/turnover simulation, correlation filter, replay
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
