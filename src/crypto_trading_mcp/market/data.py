from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import ccxt

from crypto_trading_mcp.market.models import (
    Candle,
    MarketSnapshot,
    OrderBook,
    OrderBookLevel,
    Ticker,
)

# Public market-data only. Do not attach API keys here.
DEFAULT_ALLOWED_EXCHANGES = frozenset(
    {"kraken", "coinbase", "binance", "bitstamp", "gemini"}
)


class MarketDataError(RuntimeError):
    pass


class PublicCCXTMarketData:
    """Read-only public market data via CCXT. Never authenticates."""

    def __init__(
        self,
        *,
        default_exchange_id: str = "kraken",
        allowed_exchanges: set[str] | frozenset[str] | None = None,
        max_age_seconds: float = 120.0,
    ) -> None:
        self.default_exchange_id = default_exchange_id.lower()
        self.allowed_exchanges = frozenset(
            e.lower() for e in (allowed_exchanges or DEFAULT_ALLOWED_EXCHANGES)
        )
        self.max_age_seconds = max_age_seconds
        self._clients: dict[str, Any] = {}

    def _client(self, exchange_id: str | None) -> Any:
        name = (exchange_id or self.default_exchange_id).lower()
        if name not in self.allowed_exchanges:
            raise MarketDataError(
                f"Exchange '{name}' is not in the public allowlist: "
                f"{sorted(self.allowed_exchanges)}"
            )
        if name not in ccxt.exchanges:
            raise MarketDataError(f"Unsupported exchange: {name}")
        if name not in self._clients:
            # Explicitly public: no apiKey/secret.
            self._clients[name] = getattr(ccxt, name)(
                {
                    "enableRateLimit": True,
                    "apiKey": None,
                    "secret": None,
                    "password": None,
                }
            )
        return self._clients[name]

    def get_ticker(self, symbol: str, exchange_id: str | None = None) -> Ticker:
        exchange = self._client(exchange_id)
        try:
            raw = exchange.fetch_ticker(symbol.upper())
        except ccxt.BaseError as exc:
            raise MarketDataError(str(exc)) from exc
        return Ticker(
            exchange=(exchange_id or self.default_exchange_id).lower(),
            symbol=str(raw.get("symbol") or symbol.upper()),
            last=float(raw["last"]),
            bid=float(raw["bid"]) if raw.get("bid") is not None else None,
            ask=float(raw["ask"]) if raw.get("ask") is not None else None,
            quote_volume=float(raw["quoteVolume"])
            if raw.get("quoteVolume") is not None
            else None,
            fetched_at=datetime.now(UTC),
        )

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 120,
        exchange_id: str | None = None,
    ) -> list[Candle]:
        exchange = self._client(exchange_id)
        try:
            rows = exchange.fetch_ohlcv(symbol.upper(), timeframe=timeframe, limit=limit)
        except ccxt.BaseError as exc:
            raise MarketDataError(str(exc)) from exc
        candles: list[Candle] = []
        for row in rows:
            ts, open_, high, low, close, volume = row[:6]
            candles.append(
                Candle(
                    timestamp=datetime.fromtimestamp(ts / 1000, tz=UTC),
                    open=float(open_),
                    high=float(high),
                    low=float(low),
                    close=float(close),
                    volume=float(volume),
                )
            )
        return candles

    def get_orderbook(
        self,
        symbol: str,
        limit: int = 20,
        exchange_id: str | None = None,
    ) -> OrderBook:
        exchange = self._client(exchange_id)
        try:
            raw = exchange.fetch_order_book(symbol.upper(), limit=limit)
        except ccxt.BaseError as exc:
            raise MarketDataError(str(exc)) from exc
        return OrderBook(
            exchange=(exchange_id or self.default_exchange_id).lower(),
            symbol=symbol.upper(),
            bids=[OrderBookLevel(float(p), float(a)) for p, a in raw.get("bids", [])],
            asks=[OrderBookLevel(float(p), float(a)) for p, a in raw.get("asks", [])],
            fetched_at=datetime.now(UTC),
        )

    def get_snapshot(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 120,
        exchange_id: str | None = None,
    ) -> MarketSnapshot:
        fetched_at = datetime.now(UTC)
        try:
            ticker = self.get_ticker(symbol, exchange_id)
            candles = self.get_ohlcv(symbol, timeframe, limit, exchange_id)
            try:
                orderbook = self.get_orderbook(symbol, exchange_id=exchange_id)
            except MarketDataError:
                orderbook = None
            stale = ticker.age_seconds > self.max_age_seconds
            return MarketSnapshot(
                symbol=symbol.upper(),
                timeframe=timeframe,
                exchange_id=(exchange_id or self.default_exchange_id).lower(),
                ticker=ticker,
                candles=candles,
                orderbook=orderbook,
                fetched_at=fetched_at,
                stale=stale,
                max_age_seconds=self.max_age_seconds,
            )
        except MarketDataError as exc:
            return MarketSnapshot(
                symbol=symbol.upper(),
                timeframe=timeframe,
                exchange_id=(exchange_id or self.default_exchange_id).lower(),
                ticker=None,
                candles=[],
                orderbook=None,
                fetched_at=fetched_at,
                stale=True,
                max_age_seconds=self.max_age_seconds,
                error=str(exc),
            )


class MockMarketData:
    """Deterministic in-memory market data for tests."""

    def __init__(
        self,
        *,
        candles: list[Candle] | None = None,
        ticker: Ticker | None = None,
        orderbook: OrderBook | None = None,
        max_age_seconds: float = 120.0,
        force_stale: bool = False,
        fail: bool = False,
    ) -> None:
        self.max_age_seconds = max_age_seconds
        self.force_stale = force_stale
        self.fail = fail
        now = datetime.now(UTC)
        if candles is None:
            candles = _synthetic_uptrend(now)
        self.candles = candles
        last = candles[-1].close
        self.ticker = ticker or Ticker(
            exchange="mock",
            symbol="BTC/USD",
            last=last,
            bid=last * 0.999,
            ask=last * 1.001,
            quote_volume=1_000_000.0,
            fetched_at=now - timedelta(seconds=500) if force_stale else now,
        )
        self.orderbook = orderbook or OrderBook(
            exchange="mock",
            symbol="BTC/USD",
            bids=[OrderBookLevel(last * 0.999, 1.0)],
            asks=[OrderBookLevel(last * 1.001, 1.0)],
            fetched_at=now,
        )

    def get_ticker(self, symbol: str, exchange_id: str | None = None) -> Ticker:
        if self.fail:
            raise MarketDataError("mock market data unavailable")
        return self.ticker

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 120,
        exchange_id: str | None = None,
    ) -> list[Candle]:
        if self.fail:
            raise MarketDataError("mock market data unavailable")
        return self.candles[-limit:]

    def get_orderbook(
        self,
        symbol: str,
        limit: int = 20,
        exchange_id: str | None = None,
    ) -> OrderBook:
        if self.fail:
            raise MarketDataError("mock market data unavailable")
        return self.orderbook

    def get_snapshot(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 120,
        exchange_id: str | None = None,
    ) -> MarketSnapshot:
        fetched_at = datetime.now(UTC)
        if self.fail:
            return MarketSnapshot(
                symbol=symbol.upper(),
                timeframe=timeframe,
                exchange_id=exchange_id or "mock",
                ticker=None,
                candles=[],
                orderbook=None,
                fetched_at=fetched_at,
                stale=True,
                max_age_seconds=self.max_age_seconds,
                error="mock market data unavailable",
            )
        ticker = self.get_ticker(symbol, exchange_id)
        candles = self.get_ohlcv(symbol, timeframe, limit, exchange_id)
        stale = self.force_stale or ticker.age_seconds > self.max_age_seconds
        return MarketSnapshot(
            symbol=symbol.upper(),
            timeframe=timeframe,
            exchange_id=exchange_id or "mock",
            ticker=ticker,
            candles=candles,
            orderbook=self.get_orderbook(symbol, exchange_id=exchange_id),
            fetched_at=fetched_at,
            stale=stale,
            max_age_seconds=self.max_age_seconds,
        )


def _synthetic_uptrend(now: datetime, n: int = 120) -> list[Candle]:
    candles: list[Candle] = []
    price = 100.0
    for i in range(n):
        open_ = price
        close = price + 0.4
        high = close + 0.2
        low = open_ - 0.1
        candles.append(
            Candle(
                timestamp=now - timedelta(hours=n - i),
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=1000 + i,
            )
        )
        price = close
    return candles
