# Market Data

`MarketDataGateway` wraps public REST providers with TTL cache, health tracking,
and stale-data gating. Stale or unavailable data blocks new trades.
