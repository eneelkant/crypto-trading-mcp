# Market Data Architecture

Components: `MarketDataGateway`, REST provider, `WebSocketMarketFeed`, `MarketDataCache` (TTL), `MarketDataHealth`, `MarketDataFreshness`, normalizer, optional `ExtendedMarketDataProvider` (funding/OI/liquidations).

Rules:
- Stale or unavailable market data → NO NEW LIVE ORDERS (`LiveTradingGate` + gateway `allows_new_trade`).
- Exchange health failure → NO NEW LIVE ORDERS.
- WebSocket: reconnect/backoff, duplicate message detection; disabled by default.
- Provenance via normalizer enrichment (`source`, timestamps).
