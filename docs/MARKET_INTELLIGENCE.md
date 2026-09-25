# Market Intelligence

## Scope (Phase 3)

Public/read-only market data + deterministic indicators + Market Intelligence agent.

Live trading remains disabled:

```env
TRADING_MODE=paper
LIVE_TRADING_ENABLED=false
```

## Market data service

Interface: `MarketDataService` (`get_ticker`, `get_ohlcv`, `get_orderbook`, `get_snapshot`).

Implementations:

| Implementation | Purpose |
|----------------|---------|
| `PublicCCXTMarketData` | Public CCXT data only (allowlisted exchanges, no API keys) |
| `MockMarketData` | Deterministic fixtures for tests |

Security:

- Exchange ids must be in the allowlist.
- Clients are constructed **without** credentials.
- User/tool parameters must never attach API keys.

## Deterministic indicators

Module: `crypto_trading_mcp.market.indicators`

Computed in Python (not by the LLM):

- SMA, EMA
- RSI
- MACD (line, signal, histogram)
- ATR
- Bollinger Bands
- Realized volatility
- Volume metrics
- Support / resistance (lookback highs/lows)

The LLM may only **interpret** these values.

## Market Intelligence Agent

**ID:** `market_intelligence`

### Inputs

- Symbol, timeframe, exchange id
- Market snapshot from `MarketDataService`

### Outputs

- symbol, timeframe, current price
- volatility, volume
- market regime (deterministic seed + optional LLM note)
- technical summary
- indicator bundle
- data freshness
- confidence

### Failure behavior

| Condition | Result |
|-----------|--------|
| Missing market data | `status=UNAVAILABLE`, `decision=NO_TRADE` |
| Stale ticker (age > max_age_seconds) | `status=STALE`, `decision=NO_TRADE` |
| LLM unavailable | Continues with deterministic summary; lowered reliance on narrative |

### Data freshness

`MarketSnapshot.stale` is true when ticker age exceeds `MARKET_DATA_MAX_AGE_SECONDS` (default 120). Downstream consensus must fail closed to `NO_TRADE` when critical market inputs are stale or unavailable.
