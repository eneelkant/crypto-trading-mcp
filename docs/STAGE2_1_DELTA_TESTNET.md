# Stage 2.1 — Real Delta Exchange India TESTNET Validation

```text
TRADING_MODE=paper
LIVE_TRADING_ENABLED=false
Live Execution (production)=DISABLED
Default stage=STAGE_1_LOCAL_PAPER (unchanged)
Stage 2 cloud-paper / Stage 2.1 testnet = opt-in
```

## Purpose

Validate the Delta India **TESTNET** path end-to-end without enabling production trading.

## Endpoints

| Role | URL |
|------|-----|
| Testnet (default) | `https://cdn-ind.testnet.deltaex.org` |
| Also allowed | `https://testnet-api.delta.exchange`, `https://testnet-api.india.delta.exchange` |
| Production (rejected) | `https://api.india.delta.exchange`, `https://api.delta.exchange` |

## Credentials (environment only)

Prefer environment variables (values never committed):

- `DELTA_ENV` → `testnet`
- `DELTA_TESTNET_API_KEY`
- `DELTA_TESTNET_API_SECRET`
- `DELTA_TESTNET_API_BASE_URL` → `https://cdn-ind.testnet.deltaex.org`

Fallback names (still testnet-only when `DELTA_ENV=testnet`):

- `DELTA_API_KEY`
- `DELTA_API_SECRET`
- `DELTA_API_BASE_URL` → `https://cdn-ind.testnet.deltaex.org`

Never commit values. Never use production credentials. Withdrawal permission is forbidden.

## Runner

```bash
python -c "from crypto_trading_mcp.sandbox.testnet_validation import run_stage21_validation; \
import json; print(json.dumps(run_stage21_validation(force_harness=True), indent=2))"
```

Without credentials the runner uses `LocalDeltaSandboxHarness` and reports:

- `REAL_DELTA_TESTNET_CREDENTIALS=NOT_CONFIGURED`
- order lifecycle as **HARNESS/MOCK** (not real exchange)

With credentials present and `allow_real_testnet_http`, authenticated calls use the real testnet host. Results are labelled **REAL_TESTNET**.

## Pipeline

```text
Order Intent → RiskEngine → Stage gates → KillSwitch
  → ExecutionPolicy / sandbox execution → Delta TESTNET adapter
  → reconcile / idempotency
```

Production host selection fails closed.

## WebSocket

Harness/mock WS tests remain. Real Delta testnet WebSocket is reported `NOT_TESTED` unless explicitly exercised against the live testnet WS endpoint.
