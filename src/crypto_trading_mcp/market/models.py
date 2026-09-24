from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class Ticker:
    exchange: str
    symbol: str
    last: float
    bid: float | None
    ask: float | None
    quote_volume: float | None
    fetched_at: datetime

    @property
    def age_seconds(self) -> float:
        return max(0.0, (datetime.now(UTC) - self.fetched_at).total_seconds())

    def to_dict(self) -> dict[str, Any]:
        return {
            "exchange": self.exchange,
            "symbol": self.symbol,
            "last": self.last,
            "bid": self.bid,
            "ask": self.ask,
            "quote_volume": self.quote_volume,
            "fetched_at": self.fetched_at.isoformat(),
            "age_seconds": self.age_seconds,
        }


@dataclass(frozen=True)
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }


@dataclass(frozen=True)
class OrderBookLevel:
    price: float
    amount: float


@dataclass(frozen=True)
class OrderBook:
    exchange: str
    symbol: str
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]
    fetched_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "exchange": self.exchange,
            "symbol": self.symbol,
            "bids": [{"price": b.price, "amount": b.amount} for b in self.bids],
            "asks": [{"price": a.price, "amount": a.amount} for a in self.asks],
            "fetched_at": self.fetched_at.isoformat(),
        }


@dataclass
class MarketSnapshot:
    symbol: str
    timeframe: str
    exchange_id: str
    ticker: Ticker | None
    candles: list[Candle]
    orderbook: OrderBook | None
    fetched_at: datetime
    stale: bool
    max_age_seconds: float
    error: str | None = None

    @property
    def available(self) -> bool:
        return self.ticker is not None and bool(self.candles) and self.error is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "exchange_id": self.exchange_id,
            "ticker": self.ticker.to_dict() if self.ticker else None,
            "candles": [c.to_dict() for c in self.candles],
            "orderbook": self.orderbook.to_dict() if self.orderbook else None,
            "fetched_at": self.fetched_at.isoformat(),
            "stale": self.stale,
            "max_age_seconds": self.max_age_seconds,
            "available": self.available,
            "error": self.error,
        }


class MarketDataService(Protocol):
    def get_ticker(self, symbol: str, exchange_id: str | None = None) -> Ticker: ...

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 120,
        exchange_id: str | None = None,
    ) -> list[Candle]: ...

    def get_orderbook(
        self,
        symbol: str,
        limit: int = 20,
        exchange_id: str | None = None,
    ) -> OrderBook: ...

    def get_snapshot(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 120,
        exchange_id: str | None = None,
    ) -> MarketSnapshot: ...
