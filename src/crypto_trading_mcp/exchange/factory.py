from __future__ import annotations

from typing import Any, Literal

from crypto_trading_mcp.config.settings import get_settings
from crypto_trading_mcp.exchange.base import (
    ExchangeAdapter,
    KalshiAdapter,
    PolymarketAdapter,
)
from crypto_trading_mcp.exchange.coinbase import CoinbaseAdapter
from crypto_trading_mcp.exchange.delta_india import DeltaExchangeIndiaAdapter
from crypto_trading_mcp.exchange.exceptions import LiveExecutionBlocked
from crypto_trading_mcp.exchange.mock import MockExchange
from crypto_trading_mcp.exchange.paper import PaperExchange
from crypto_trading_mcp.portfolio.manager import PortfolioManager

ExchangeName = Literal[
    "paper",
    "mock",
    "coinbase",
    "delta_india",
    "polymarket",
    "kalshi",
]

_LIVE_NAMES = {"coinbase", "delta_india", "polymarket", "kalshi"}


def create_exchange(
    name: ExchangeName | str = "paper",
    *,
    portfolio: PortfolioManager | None = None,
    config: dict[str, Any] | None = None,
    prices: dict[str, float] | None = None,
    allow_live_stub: bool = False,
    allow_read_adapters: bool = False,
) -> ExchangeAdapter:
    """Resolve an exchange adapter.

    Default paper environments refuse live venue names (Phase 5–8 safety).
    Pass ``allow_read_adapters=True`` to construct Coinbase/Delta adapters for
    public/read interface work; their ``create_order`` still blocks while live
    trading is disabled.
    """
    settings = get_settings()
    key = str(name or "paper").lower().strip()

    if key == "paper":
        return PaperExchange(portfolio=portfolio, config=config, prices=prices)
    if key == "mock":
        return MockExchange(portfolio=portfolio, config=config, prices=prices)

    if key in _LIVE_NAMES:
        live_off = settings.trading_mode == "paper" or not settings.live_trading_enabled
        if live_off and not allow_live_stub and not allow_read_adapters:
            raise LiveExecutionBlocked(
                f"Cannot resolve live adapter '{key}' while TRADING_MODE=paper "
                "or LIVE_TRADING_ENABLED=false"
            )
        if key == "coinbase":
            return CoinbaseAdapter()
        if key == "delta_india":
            return DeltaExchangeIndiaAdapter()
        if key == "polymarket":
            return PolymarketAdapter()
        if key == "kalshi":
            return KalshiAdapter()

    if settings.trading_mode == "paper" or not settings.live_trading_enabled:
        return PaperExchange(portfolio=portfolio, config=config, prices=prices)

    raise LiveExecutionBlocked(f"Unknown exchange adapter: {key}")


def list_exchanges() -> list[dict[str, Any]]:
    settings = get_settings()
    return [
        {"name": "paper", "execution": "paper", "enabled": True},
        {"name": "mock", "execution": "paper", "enabled": True},
        {
            "name": "coinbase",
            "execution": "blocked_unless_live",
            "enabled": True,
            "LIVE_TRADING_ENABLED": settings.live_trading_enabled,
        },
        {
            "name": "delta_india",
            "execution": "blocked_unless_live",
            "enabled": True,
            "LIVE_TRADING_ENABLED": settings.live_trading_enabled,
        },
        {"name": "polymarket", "execution": "stub", "enabled": False},
        {"name": "kalshi", "execution": "stub", "enabled": False},
    ]
