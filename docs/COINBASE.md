# Coinbase Adapter

Public market-data interface is available. Authenticated order submission raises
`LiveExecutionBlocked` unless `TRADING_MODE=live` and `LIVE_TRADING_ENABLED=true`.
Credentials via `COINBASE_API_KEY` / `COINBASE_API_SECRET` only.
