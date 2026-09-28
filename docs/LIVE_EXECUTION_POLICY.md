# Live Execution Policy

`LiveExecutionPolicy` + `LiveTradingGate` fail closed.

Only `trading_mode=live` AND `LIVE_TRADING_ENABLED=true` AND Stage 5/6 AND all deterministic gates can approve.

Paper + any flag combination → live impossible.

Reason codes include credential, permission, stale data, exchange down, risk failure, reconciliation, kill switch, daily loss, drawdown, limits, duplicate, clock skew, invalid order, stage not allowed, cloud-paper isolation.
