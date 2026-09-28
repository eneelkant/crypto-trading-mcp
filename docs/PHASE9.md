# Phase 9 — Production Trading Infrastructure

PAPER TRADING: ENABLED  
LIVE TRADING: DISABLED

Phase 9 adds:

- MarketDataGateway (cache, health, stale gating)
- Coinbase + Delta Exchange India adapters (live orders blocked)
- Continuous autonomous PAPER loop
- Order idempotency
- Cycle state machine
- CLI/MCP production surface

Defaults remain:

```text
TRADING_MODE=paper
LIVE_TRADING_ENABLED=false
```
