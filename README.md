# Crypto Trading MCP

Experimental multi-agent crypto market analysis and **autonomous paper trading** platform with MCP, CLI, dashboard, backtesting, and self-learning.

```text
This repository currently supports research, backtesting and autonomous PAPER trading.

Live execution is disabled by default.

Cryptocurrency trading involves substantial risk.
Past performance and backtesting do not guarantee future results.
Autonomous trading can result in financial loss.
Users are responsible for determining whether and how to use live trading.
```

## Current status (Phases 1–9 + production readiness foundations)

- Multi-agent analysis, risk, portfolio, planner, paper exchange, backtest, dashboard, learning
- Coinbase + Delta India adapters (auth/read architecture; production orders not enabled)
- Market-data gateway, WebSocket reconnect hooks, freshness gates
- Credential providers + withdrawal ban + secret redaction
- Durable order intent ledger (SQLite; Postgres interface)
- Reconciliation, live execution gate, trading stages (default Stage 1 local paper)
- Live kill-switch cancel-all hooks, alerting interfaces, cloud-paper packaging
- RAG/intelligence context layer with prompt-injection containment
- **PAPER TRADING: ENABLED**
- **LIVE TRADING: DISABLED** (not production-live ready)

Defaults:

```env
TRADING_MODE=paper
LIVE_TRADING_ENABLED=false
```

Dashboard default bind: `127.0.0.1:8050`.

Production readiness docs: `docs/LIVE_TRADING_READINESS.md`, `docs/TRADING_STAGES.md`,
`docs/LIVE_EXECUTION_POLICY.md`, `docs/CLOUD_DEPLOYMENT.md`.

Cloud-paper (still cannot live trade): `deploy/docker-compose.cloud-paper.yml`.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Optional Phase 8 ML backends (XGBoost / scikit-learn). Without them, learning uses a
deterministic logistic fallback:

```bash
pip install -e ".[ml]"
```

## Run paper command center

```bash
# build UI once (optional if using API-only / fallback HTML)
cd dashboard_ui && npm install && npm run build && cd ..

trader run --demo                 # paper + dashboard + one learning demo cycle (auto-opens browser)
trader run --no-browser --demo   # same without browser
```

Dashboard: `http://127.0.0.1:8050`

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
trader backtest BTC/USD --strategy momentum_breakout_crypto
trader walk-forward BTC/USD
trader learning status
trader learning memory
trader learning calibration
trader learning brier
trader learning models
trader learning proposals
trader dashboard status
trader market status
trader exchange list
trader cycle start --max-cycles 1 --foreground
trader cycle status
trader live-status
trader kill-switch
```

## MCP server

```bash
python -m crypto_trading_mcp
```

## Tests

```bash
pytest -q
```

## Security

See `docs/SECURITY.md`. Never commit `.env` or real API keys. Prefer trading-only
exchange keys with withdrawals disabled if you ever configure live credentials locally.

## Docs

- `docs/SECURITY.md` / `docs/SECRETS_MANAGEMENT.md` / `docs/EXCHANGE_CREDENTIALS.md`
- `docs/LIVE_TRADING_READINESS.md` / `docs/LIVE_TRADING_TEST_PLAN.md`
- `docs/ARCHITECTURE.md` → `docs/ARCHITECTURE_AUDIT.md`
- `docs/AGENTS.md` / `docs/RAG_ARCHITECTURE.md` / `docs/DATA_SOURCES.md`
- `docs/LLM_PROVIDERS.md` / `docs/LOCAL_MAC_SETUP.md` / `docs/MCP_TOOLS.md`
- `docs/PAPER_TRADING.md` / `docs/AUTONOMOUS_TRADING.md`
- `docs/BACKTESTING.md` / `docs/WALK_FORWARD.md`
- `docs/DASHBOARD.md` / `docs/OBSERVABILITY.md`
- `docs/SELF_LEARNING.md` / `docs/LEARNING.md`
- `docs/RISK_MANAGEMENT.md` / `docs/LIVE_EXECUTION_POLICY.md`
- `docs/OPERATIONS.md` / `docs/TROUBLESHOOTING.md` / `docs/24X7_OPERATIONS.md`
