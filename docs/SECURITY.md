# Security

This repository supports research, backtesting, and autonomous **paper** trading.

```text
TRADING_MODE=paper
LIVE_TRADING_ENABLED=false
Live Execution=DISABLED
```

## Secrets

- Copy `.env.example` → `.env` locally. Never commit `.env`.
- Leave API key values empty in `.env.example`.
- Store live exchange credentials outside Git.
- Prefer trading-only keys, withdrawals disabled, and IP allowlisting where supported.
- Dashboard EventBus sanitizes secrets and strips private prompts / chain-of-thought.

## Dashboard exposure

Default bind: `127.0.0.1:8050` (`config/dashboard.yaml`).

Do not bind `0.0.0.0` unless you intentionally expose a local observability UI and understand the risk.
The dashboard has no direct exchange credentials and cannot enable live trading.

## Learning safety

The Phase 8 learning engine cannot:

- enable live trading
- disable the RiskEngine or Kill Switch
- raise hard risk limits
- place arbitrary exchange orders

## Kill Switch

A `STOP` file in the repository root (or configured kill-switch path) remains authoritative for blocking new paper trades.
