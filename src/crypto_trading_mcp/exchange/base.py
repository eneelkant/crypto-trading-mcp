from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from crypto_trading_mcp.exchange.exceptions import LiveExecutionBlocked
from crypto_trading_mcp.exchange.models import Balance, Order


class ExchangeAdapter(ABC):
    """Unified exchange adapter. Phase 5 only implements paper/mock execution."""

    name: str
    supports_live_execution: bool = False

    @abstractmethod
    def get_balance(self) -> list[Balance]: ...

    @abstractmethod
    def get_positions(self) -> list[dict[str, Any]]: ...

    @abstractmethod
    def get_market_price(self, symbol: str) -> float: ...

    @abstractmethod
    def get_orderbook(self, symbol: str, limit: int = 20) -> dict[str, Any]: ...

    @abstractmethod
    def create_order(self, order: Order, market_price: float | None = None) -> Order: ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> Order: ...

    @abstractmethod
    def get_order(self, order_id: str) -> Order: ...

    @abstractmethod
    def get_open_orders(self, symbol: str | None = None) -> list[Order]: ...


class _FutureLiveAdapter(ExchangeAdapter):
    """Interface-only stub for future authenticated venues."""

    supports_live_execution = True

    def get_balance(self) -> list[Balance]:
        raise LiveExecutionBlocked(f"{self.name} live execution is not implemented in Phase 5")

    def get_positions(self) -> list[dict[str, Any]]:
        raise LiveExecutionBlocked(f"{self.name} live execution is not implemented in Phase 5")

    def get_market_price(self, symbol: str) -> float:
        raise LiveExecutionBlocked(f"{self.name} live execution is not implemented in Phase 5")

    def get_orderbook(self, symbol: str, limit: int = 20) -> dict[str, Any]:
        raise LiveExecutionBlocked(f"{self.name} live execution is not implemented in Phase 5")

    def create_order(self, order: Order, market_price: float | None = None) -> Order:
        raise LiveExecutionBlocked(f"{self.name} live execution is not implemented in Phase 5")

    def cancel_order(self, order_id: str) -> Order:
        raise LiveExecutionBlocked(f"{self.name} live execution is not implemented in Phase 5")

    def get_order(self, order_id: str) -> Order:
        raise LiveExecutionBlocked(f"{self.name} live execution is not implemented in Phase 5")

    def get_open_orders(self, symbol: str | None = None) -> list[Order]:
        raise LiveExecutionBlocked(f"{self.name} live execution is not implemented in Phase 5")


class CoinbaseAdapter(_FutureLiveAdapter):
    name = "coinbase"


class DeltaExchangeIndiaAdapter(_FutureLiveAdapter):
    name = "delta_india"


class PolymarketAdapter(_FutureLiveAdapter):
    name = "polymarket"


class KalshiAdapter(_FutureLiveAdapter):
    name = "kalshi"
