from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from crypto_trading_mcp.exchange.exceptions import LiveExecutionBlocked
from crypto_trading_mcp.exchange.models import Balance, Order


class ExchangeAdapter(ABC):
    """Unified exchange adapter. Live venues must still honor LIVE_TRADING_ENABLED."""

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

    # Optional Phase 9 surface (default wrappers)
    def get_account(self) -> dict[str, Any]:
        return {"balances": [b.model_dump() if hasattr(b, "model_dump") else b for b in self.get_balance()]}

    def get_balances(self) -> list[Balance]:
        return self.get_balance()

    def get_ticker(self, symbol: str) -> dict[str, Any]:
        return {"symbol": symbol, "last": self.get_market_price(symbol)}

    def get_market_info(self, symbol: str) -> dict[str, Any]:
        return {"symbol": symbol}

    def submit_order(self, order: Order, market_price: float | None = None) -> Order:
        return self.create_order(order, market_price=market_price)

    def get_order_history(self, symbol: str | None = None) -> list[dict[str, Any]]:
        return []

    def status(self) -> dict[str, Any]:
        return {
            "exchange": self.name,
            "supports_live_execution": self.supports_live_execution,
            "LIVE_TRADING_ENABLED": False,
        }


class _FutureLiveAdapter(ExchangeAdapter):
    """Interface-only stub for future authenticated venues."""

    supports_live_execution = True

    def get_balance(self) -> list[Balance]:
        raise LiveExecutionBlocked(f"{self.name} live execution is not implemented")

    def get_positions(self) -> list[dict[str, Any]]:
        raise LiveExecutionBlocked(f"{self.name} live execution is not implemented")

    def get_market_price(self, symbol: str) -> float:
        raise LiveExecutionBlocked(f"{self.name} live execution is not implemented")

    def get_orderbook(self, symbol: str, limit: int = 20) -> dict[str, Any]:
        raise LiveExecutionBlocked(f"{self.name} live execution is not implemented")

    def create_order(self, order: Order, market_price: float | None = None) -> Order:
        raise LiveExecutionBlocked(f"{self.name} live execution is not implemented")

    def cancel_order(self, order_id: str) -> Order:
        raise LiveExecutionBlocked(f"{self.name} live execution is not implemented")

    def get_order(self, order_id: str) -> Order:
        raise LiveExecutionBlocked(f"{self.name} live execution is not implemented")

    def get_open_orders(self, symbol: str | None = None) -> list[Order]:
        raise LiveExecutionBlocked(f"{self.name} live execution is not implemented")


class PolymarketAdapter(_FutureLiveAdapter):
    name = "polymarket"


class KalshiAdapter(_FutureLiveAdapter):
    name = "kalshi"


# Backward-compatible re-exports (concrete adapters live in dedicated modules)
from crypto_trading_mcp.exchange.coinbase import CoinbaseAdapter as CoinbaseAdapter
from crypto_trading_mcp.exchange.delta_india import DeltaExchangeIndiaAdapter as DeltaExchangeIndiaAdapter
