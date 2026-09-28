# Production Market Data

Default public REST via CCXT (Kraken). Coinbase/Delta public endpoints available through adapters.

WebSocket production handling is implemented as a reconnecting feed hook (`market.websocket`). Enable only after soak tests.

Extended feeds (funding, OI, liquidations) are interface-ready via `ExtendedMarketDataProvider` and return unavailable until vendor adapters are configured.

Live trading remains disabled.
