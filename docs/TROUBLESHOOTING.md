# Troubleshooting

## Dashboard will not open

```bash
trader dashboard status
curl -s http://127.0.0.1:8050/api/health
trader run --no-browser --demo
```

Build UI assets if needed: `cd dashboard_ui && npm install && npm run build`.

## Paper engine refuses to start

Confirm `.env`:

```env
TRADING_MODE=paper
LIVE_TRADING_ENABLED=false
```

Remove a root `STOP` file if the kill switch is intentionally active.

## Learning retraining backend

If XGBoost/sklearn are missing, Phase 8 uses a deterministic logistic fallback.
Install optional extras with `pip install -e ".[ml]"` when desired.

## Secrets in events

Event payloads are sanitized. If something unexpected appears, file an issue and
rotate any real credential immediately — never commit `.env`.
