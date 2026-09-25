from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from crypto_trading_mcp.config.settings import REPO_ROOT
from crypto_trading_mcp.market.base import MarketDataProvider
from crypto_trading_mcp.market.cache import TTLCache
from crypto_trading_mcp.market.data import MockMarketData, PublicCCXTMarketData
from crypto_trading_mcp.market.health import MarketDataHealth
from crypto_trading_mcp.market.models import Candle, MarketSnapshot, OrderBook, Ticker
from crypto_trading_mcp.market.normalizer import enrich_record
from crypto_trading_mcp.market.rest import RestMarketDataProvider
from crypto_trading_mcp.market.websocket import WebSocketMarketFeed


def load_market_data_config(path: Path | None = None) -> dict[str, Any]:
    path = path or (REPO_ROOT / "config" / "market_data.yaml")
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data.get("market_data") or {}


class MarketDataGateway:
    """Unified market-data gateway with cache, health, and stale-data gating."""

    def __init__(
        self,
        provider: MarketDataProvider | PublicCCXTMarketData | MockMarketData | None = None,
        *,
        config: dict[str, Any] | None = None,
        websocket: WebSocketMarketFeed | None = None,
    ) -> None:
        cfg = config if config is not None else load_market_data_config()
        self.config = cfg
        max_age = float(cfg.get("max_age_seconds", 120))
        if provider is None:
            provider = RestMarketDataProvider(
                PublicCCXTMarketData(
                    default_exchange_id=str(cfg.get("default_exchange_id", "kraken")),
                    allowed_exchanges=set(cfg.get("allowed_exchanges") or []),
                    max_age_seconds=max_age,
                )
            )
        elif isinstance(provider, (PublicCCXTMarketData, MockMarketData)):
            provider = RestMarketDataProvider(provider) if isinstance(provider, PublicCCXTMarketData) else _MockAdapter(provider)
        self.provider = provider
        self.health = MarketDataHealth(max_age_seconds=max_age)
        self.cache = TTLCache(ttl_seconds=float(cfg.get("cache_ttl_seconds", 5)))
        self.websocket = websocket or WebSocketMarketFeed(
            enabled=bool(cfg.get("websocket_enabled", False))
        )
        self.stale_blocks_new_trades = bool(cfg.get("stale_blocks_new_trades", True))

    def get_ticker(self, symbol: str, exchange_id: str | None = None) -> Ticker:
        key = f"ticker:{exchange_id}:{symbol}"
        try:
            ticker = self.cache.get_or_set(
                key, lambda: self.provider.get_ticker(symbol, exchange_id=exchange_id)
            )
            self.health.mark_ok()
            return ticker
        except Exception as exc:  # noqa: BLE001
            self.health.mark_error(str(exc))
            raise

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 120,
        exchange_id: str | None = None,
    ) -> list[Candle]:
        key = f"ohlcv:{exchange_id}:{symbol}:{timeframe}:{limit}"
        try:
            candles = self.cache.get_or_set(
                key,
                lambda: self.provider.get_ohlcv(
                    symbol, timeframe=timeframe, limit=limit, exchange_id=exchange_id
                ),
            )
            self.health.mark_ok()
            return candles
        except Exception as exc:  # noqa: BLE001
            self.health.mark_error(str(exc))
            raise

    def get_order_book(
        self, symbol: str, limit: int = 20, exchange_id: str | None = None
    ) -> OrderBook:
        return self.provider.get_orderbook(symbol, limit=limit, exchange_id=exchange_id)

    def get_snapshot(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 120,
        exchange_id: str | None = None,
    ) -> MarketSnapshot:
        snap = self.provider.get_snapshot(
            symbol, timeframe=timeframe, limit=limit, exchange_id=exchange_id
        )
        if snap.error:
            self.health.mark_error(snap.error)
        elif snap.stale:
            self.health.mark_error("stale_market_data")
        else:
            self.health.mark_ok()
        return snap

    def allows_new_trade(self, snapshot: MarketSnapshot) -> bool:
        if not self.stale_blocks_new_trades:
            return snapshot.available and not snapshot.error
        return self.health.snapshot_allows_new_trade(snapshot)

    def status(self) -> dict[str, Any]:
        return enrich_record(
            {
                "gateway": "MarketDataGateway",
                "provider": getattr(self.provider, "name", type(self.provider).__name__),
                "health": self.health.status(),
                "websocket": self.websocket.status(),
                "stale_blocks_new_trades": self.stale_blocks_new_trades,
                "TRADING_MODE": "paper",
                "LIVE_TRADING_ENABLED": False,
            },
            symbol="SYSTEM",
            source="gateway",
        )


class _MockAdapter(MarketDataProvider):
    name = "mock"

    def __init__(self, inner: MockMarketData) -> None:
        self.inner = inner

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
