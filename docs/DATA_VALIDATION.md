# Data Validation

Historical candles are normalized to:

```text
timestamp, symbol, timeframe, open, high, low, close, volume
```

## Rejected conditions

- duplicate timestamps
- unsorted series (after normalization)
- invalid OHLC (high < low, wick inconsistencies)
- negative volume or prices
- empty datasets

The backtest fails safely with `HistoricalDataError` when data is invalid.

## Providers (Phase 6)

| Provider | Status |
|----------|--------|
| MockHistoricalDataProvider | implemented |
| CSV / JSON | implemented |
| Parquet | optional if pandas present |
| CCXT / Coinbase / Yahoo stubs | interface only — no credentials |

Unavailable datasets are **not fabricated**.

## Timezones

Timestamps are normalized to UTC.
