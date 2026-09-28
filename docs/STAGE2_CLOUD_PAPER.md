# Stage 2 — Cloud Paper

```text
TRADING_MODE=paper
LIVE_TRADING_ENABLED=false
Live Execution=DISABLED
Current stage: STAGE_2_CLOUD_PAPER
```

## Selected sandbox venue

**Delta Exchange India — TESTNET**

| Field | Value |
|-------|-------|
| Venue | `delta_india` |
| Environment | `TESTNET` / `SANDBOX` |
| Default base URL | `https://cdn-ind.testnet.deltaex.org` |
| Also allowed | `https://testnet-api.delta.exchange`, `https://testnet-api.india.delta.exchange` |
| Rejected (Stage 2) | `https://api.india.delta.exchange`, `https://api.delta.exchange` |
| Auth | HMAC-SHA256 (`api-key`, `timestamp`, `signature`) |
| Env vars | `DELTA_API_KEY`, `DELTA_API_SECRET`, `DELTA_API_BASE_URL` |
| Withdrawals | Forbidden |

### Why Delta India

Compared with Coinbase in this repository, Delta already has complete HMAC signing,
balances, positions, open orders, order history, cancel, and cancel-all surfaces wired
through `DeltaExchangeIndiaAdapter`. Stage 2 wraps it with endpoint allowlisting and a
TESTNET environment.

### Supported operations

authenticate, health_check, get_account, get_balances, get_positions, get_open_orders,
get_order_status, submit_order, cancel_order, cancel_all_orders, REST market data.

### WebSocket

Optional sandbox WS client with reconnect/backoff/stale/duplicate protection.
Default URL: `wss://cdn-ind.testnet.deltaex.org/ws`.

### Limitations / testing reality

- CI and local validation use `LocalDeltaSandboxHarness` (transport mock) when real
  Delta testnet credentials are not configured.
- Live Delta testnet connectivity without credentials is **NOT TESTED**.
- Production endpoints/credentials are rejected while Stage 2 is active.

## Local cloud-paper

```bash
# App-level Stage 2 runtime (SQLite + harness)
python -c "from crypto_trading_mcp.sandbox import Stage2CloudPaperRuntime as R; r=R(); print(r.start()); print(r.run_cycle()); print(r.recover()); print(r.shutdown())"

# Docker compose (requires Docker)
docker compose -f deploy/docker-compose.cloud-paper.yml up --build
# Health: http://127.0.0.1:8080/health
```

## Safety

- Paper mode only; live gate fail-closed
- No production credentials in Git
- Durable kill switch in SQLite/Postgres store
- Ambiguous submits → reconcile before retry
- Stage manager does not auto-advance to Stage 3
