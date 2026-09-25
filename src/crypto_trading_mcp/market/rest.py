from __future__ import annotations

from typing import Any

from crypto_trading_mcp.market.base import MarketDataProvider
from crypto_trading_mcp.market.data import PublicCCXTMarketData
from crypto_trading_mcp.market.models import Candle, MarketSnapshot, OrderBook, Ticker


class RestMarketDataProvider(MarketDataProvider):
    """REST market data via existing public CCXT layer."""

    name = "rest_ccxt"

    def __init__(self, inner: PublicCCXTMarketData | None = None) -> None:
        self.inner = inner or PublicCCXTMarketData()

    def get_ticker(self, symbol: str, exchange_id: str | None = None) -> Ticker:
        return self.inner.get_ticker(symbol, exchange_id=exchange_id)

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 120,
        exchange_id: str | None = None,
    ) -> list[Candle]:
        return self.inner.get_ohlcv(symbol, timeframe=timeframe, limit=limit, exchange_id=exchange_id)

    def get_orderbook(
        self, symbol: str, limit: int = 20, exchange_id: str | None = None
    ) -> OrderBook:
        return self.inner.get_orderbook(symbol, limit=limit, exchange_id=exchange_id)

    def get_snapshot(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 120,
        exchange_id: str | None = None,
    ) -> MarketSnapshot:
        return self.inner.get_snapshot(
            symbol, timeframe=timeframe, limit=limit, exchange_id=exchange_id
        )

    def health(self) -> dict[str, Any]:
        return {"provider": self.name, "ok": True, "transport": "rest"}
