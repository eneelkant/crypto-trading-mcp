# Exchange Architecture

```text
ExchangeAdapter
├── MockExchange
├── PaperExchange          # Phase 5 execution path
├── CoinbaseAdapter        # interface / future only
├── DeltaExchangeIndiaAdapter  # interface / future only
├── PolymarketAdapter      # interface / future only
└── KalshiAdapter          # interface / future only
```

## Package layout

```text
src/crypto_trading_mcp/exchange/
  base.py          # ABC + future live stubs
  models.py        # instruments, orders, fills
  paper.py         # deterministic paper venue
  mock.py
  fees.py
  slippage.py
  order_book.py
  settlement.py
  trailing.py
  prediction.py
  factory.py       # create_exchange(); paper-safe resolution
  exceptions.py
  config.py
```

## Factory safety

`create_exchange()` refuses live venue names when `TRADING_MODE=paper` or
`LIVE_TRADING_ENABLED=false`. Paper environments never accidentally resolve to a live
adapter.

## Instruments

Normalized `InstrumentMeta` covers CRYPTO, EQUITY, ETF, COMMODITY, FUTURE, and
PREDICTION_CONTRACT with tick/lot sizes, multiplier, margin, shortable flag,
trading hours, expiration, and settlement type.

## Phase 5 scope

Phase 5 does **not** perform live trading. Authenticated execution endpoints are not
called.

## Phase 9

Coinbase and Delta India adapters are available for public/read testing.
Live order submission remains blocked while LIVE_TRADING_ENABLED=false.
