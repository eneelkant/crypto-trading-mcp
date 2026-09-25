from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from crypto_trading_mcp.market.models import Candle, MarketSnapshot, OrderBook, Ticker


class MarketDataProvider(ABC):
    """Read-only market data provider. Never authenticates for trading."""

    name: str = "base"

    @abstractmethod
    def get_ticker(self, symbol: str, exchange_id: str | None = None) -> Ticker: ...

    @abstractmethod
    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 120,
        exchange_id: str | None = None,
    ) -> list[Candle]: ...

    @abstractmethod
    def get_orderbook(
        self, symbol: str, limit: int = 20, exchange_id: str | None = None
    ) -> OrderBook: ...

    def get_trades(self, symbol: str, limit: int = 50) -> list[dict[str, Any]]:
        return []

    def get_funding_rate(self, symbol: str) -> float | None:
        return None

    def get_snapshot(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 120,
        exchange_id: str | None = None,
    ) -> MarketSnapshot:
        raise NotImplementedError

    def health(self) -> dict[str, Any]:
        return {"provider": self.name, "ok": True}
