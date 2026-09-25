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

## Current phase (8)

- **16-agent** analysis / consensus / risk / execution / reflection roster
- Multi-LLM provider abstraction (`mock` default; OpenAI / Anthropic / Gemini via env)
- Deterministic technical analysis + strategy engine
- Bull / Bear / Consensus pipeline
- Deterministic **RiskEngine** + Kill Switch + circuit breakers
- PaperExchange / PaperTradingEngine (fees, slippage, portfolio)
- Backtesting, walk-forward, Monte Carlo, sensitivity, prediction-market evaluation
- Live observability dashboard at `http://127.0.0.1:8050`
- Self-learning: post-mortem, failure/success memory, similarity context, Brier/calibration,
  Kelly adaptation, regime detection, optional ML retraining, champion/challenger, proposals, drift
- MCP tools + `trader` CLI
- **No live/authenticated execution**

Defaults:

```env
TRADING_MODE=paper
LIVE_TRADING_ENABLED=false
```

Dashboard default bind: `127.0.0.1:8050`.

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

- `docs/SECURITY.md`
- `docs/ARCHITECTURE.md` → `docs/ARCHITECTURE_AUDIT.md`
- `docs/AGENTS.md`
- `docs/LLM_PROVIDERS.md`
- `docs/LOCAL_MAC_SETUP.md`
- `docs/MCP_TOOLS.md`
- `docs/PAPER_TRADING.md` / `docs/AUTONOMOUS_TRADING.md`
- `docs/BACKTESTING.md` / `docs/WALK_FORWARD.md`
- `docs/DASHBOARD.md` / `docs/OBSERVABILITY.md`
- `docs/SELF_LEARNING.md` / `docs/LEARNING.md`
- `docs/RISK_MANAGEMENT.md`
- `docs/OPERATIONS.md` / `docs/TROUBLESHOOTING.md`
