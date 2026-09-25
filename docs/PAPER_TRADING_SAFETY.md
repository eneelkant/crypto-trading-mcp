# Paper Trading Safety

```text
TRADING_MODE=paper
LIVE_TRADING_ENABLED=false
REAL MONEY: DISABLED
```

Phase 5 does **not** perform live trading.

## Guarantees

1. `create_exchange("coinbase"|"delta_india"|"polymarket"|"kalshi")` raises
   `LiveExecutionBlocked` while paper mode is active.
2. Future venue adapters are interface-only stubs that reject execution.
3. Paper paths never read Coinbase/Delta/Polymarket/Kalshi credentials or wallet keys.
4. Risk Engine runs before every paper order acceptance; LLM metadata cannot override limits.
5. Kill switch (`STOP` file) rejects new orders and stops autonomous trading.
6. Circuit breaker after `max_consecutive_api_failures` (default 3) halts the paper exchange.
7. Stale market data rejects new orders.

## Kill switch restart

Remove the `STOP` file, then call `PaperTradingEngine.safe_restart()` (CLI:
`trader paper restart`). The LLM cannot deactivate the kill switch.

## Tests

See `tests/unit/test_phase5_safety.py` for the Phase 5 safety matrix (live blocked,
risk rejection, kill switch, stale data, circuit breaker, fees, slippage, stops,
prediction settlement, deterministic replay, no credentials).
