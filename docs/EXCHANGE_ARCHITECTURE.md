# Exchange Architecture

```text
ExchangeAdapter
├── MockExchange          (implemented — test alias)
├── PaperExchange         (implemented — Phase 5)
├── CoinbaseAdapter       (future)
├── DeltaExchangeIndiaAdapter (future)
├── PolymarketAdapter     (future)
└── KalshiAdapter         (future)
```

Only `PaperExchange` / `MockExchange` place simulated orders.

Instrument metadata (`config/paper.yaml`) distinguishes:

`CRYPTO | EQUITY | ETF | COMMODITY | FUTURE | PREDICTION_CONTRACT`
