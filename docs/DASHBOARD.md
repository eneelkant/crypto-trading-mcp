# Dashboard

Phase 7 observability command center.

```text
URL: http://127.0.0.1:8050
TRADING_MODE=paper
LIVE_TRADING_ENABLED=false
```

## Start

```bash
trader run --no-browser
trader run --demo
trader dashboard
trader dashboard status
trader dashboard open
```

The dashboard is an observability layer. If it crashes, paper trading continues.

## Architecture

```text
Trading / Paper / Backtest engines
        ↓
EventBus
        ↓
FastAPI + WebSocket
        ↓
React UI
```

Browser never talks to exchanges directly.

## Features

- 16-agent monitor + communication timeline
- Portfolio / risk / orders / P&L
- Phase 6 backtests, walk-forward, sensitivity, Monte Carlo, benchmarks, prediction eval
- LLM + MCP activity panels
- Kill switch (reuses Phase 5; LLM cannot deactivate)

## Security

Binds to `127.0.0.1` by default. Secrets, API keys, private prompts, and chain-of-thought are sanitized from events.

## Phase 8 Learning Panels

Tabs: Learning overview, Memory, Calibration, Models, Proposals, Drift, Audit.
API: `/api/learning/*`. Events stream via existing WebSocket.
