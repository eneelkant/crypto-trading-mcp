from __future__ import annotations

from typing import Any, Literal

from crypto_trading_mcp.config.settings import get_settings
from crypto_trading_mcp.exchange.base import (
    CoinbaseAdapter,
    DeltaExchangeIndiaAdapter,
    ExchangeAdapter,
    KalshiAdapter,
    PolymarketAdapter,
)
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
) -> ExchangeAdapter:
    """Resolve an exchange adapter.

    Paper environments always resolve to PaperExchange/MockExchange.
    Live venue names raise ``LiveExecutionBlocked`` unless ``allow_live_stub``
    is set (returns interface-only stubs that still reject execution).
    """
    settings = get_settings()
    key = str(name or "paper").lower().strip()

    if settings.trading_mode == "paper" or not settings.live_trading_enabled:
        if key in _LIVE_NAMES and not allow_live_stub:
            raise LiveExecutionBlocked(
                f"Cannot resolve live adapter '{key}' while TRADING_MODE=paper "
                "or LIVE_TRADING_ENABLED=false"
            )
        if key in {"paper", "mock"} or key not in _LIVE_NAMES:
            if key == "mock":
                return MockExchange(portfolio=portfolio, config=config, prices=prices)
            return PaperExchange(portfolio=portfolio, config=config, prices=prices)

    if key == "paper":
        return PaperExchange(portfolio=portfolio, config=config, prices=prices)
    if key == "mock":
        return MockExchange(portfolio=portfolio, config=config, prices=prices)
    if key == "coinbase":
        return CoinbaseAdapter()
    if key == "delta_india":
        return DeltaExchangeIndiaAdapter()
    if key == "polymarket":
        return PolymarketAdapter()
    if key == "kalshi":
        return KalshiAdapter()
    raise LiveExecutionBlocked(f"Unknown exchange adapter: {key}")
