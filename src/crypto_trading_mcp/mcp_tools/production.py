from __future__ import annotations

from typing import Any

from crypto_trading_mcp.autonomous.loop import get_autonomous_loop
from crypto_trading_mcp.exchange.coinbase import CoinbaseAdapter
from crypto_trading_mcp.exchange.delta_india import DeltaExchangeIndiaAdapter
from crypto_trading_mcp.exchange.factory import create_exchange, list_exchanges
from crypto_trading_mcp.market.data import MockMarketData
from crypto_trading_mcp.market.gateway import MarketDataGateway


class ProductionToolSurface:
    """Phase 9 MCP surface — paper cycle + read-only market/exchange status."""

    def __init__(self) -> None:
        self.gateway = MarketDataGateway(MockMarketData())
        self.loop = get_autonomous_loop()

    def get_market_status(self) -> dict[str, Any]:
        return self.gateway.status()

    def get_exchange_status(self, name: str = "paper") -> dict[str, Any]:
        if name in {"coinbase", "delta_india"}:
            adapter = create_exchange(name, allow_read_adapters=True)
        else:
            adapter = create_exchange(name)
        return getattr(adapter, "status", lambda: {"exchange": name})()

    def get_market_data(self, symbol: str = "BTC/USD") -> dict[str, Any]:
        return self.gateway.get_snapshot(symbol).to_dict()

    def get_order_book(self, symbol: str = "BTC/USD") -> dict[str, Any]:
        book = self.gateway.get_order_book(symbol)
        return book.to_dict()

    def get_account(self, exchange: str = "paper") -> dict[str, Any]:
        adapter = create_exchange(exchange if exchange in {"paper", "mock"} else "paper")
        return adapter.get_account()

    def get_positions(self, exchange: str = "paper") -> dict[str, Any]:
        adapter = create_exchange(exchange if exchange in {"paper", "mock"} else "paper")
        return {"positions": adapter.get_positions(), "TRADING_MODE": "paper"}

    def get_open_orders(self, exchange: str = "paper") -> dict[str, Any]:
        adapter = create_exchange(exchange if exchange in {"paper", "mock"} else "paper")
        orders = adapter.get_open_orders()
        return {
            "orders": [o.model_dump(mode="json") if hasattr(o, "model_dump") else o for o in orders],
            "TRADING_MODE": "paper",
        }

    def start_paper_cycle(self, max_cycles: int = 1) -> dict[str, Any]:
        return self.loop.start(background=False, max_cycles=max_cycles)

    def stop_paper_cycle(self) -> dict[str, Any]:
        return self.loop.stop()

    def get_cycle_status(self) -> dict[str, Any]:
        return self.loop.status()

    def get_execution_status(self) -> dict[str, Any]:
        return {
            "Live Execution": "DISABLED",
            "LIVE_TRADING_ENABLED": False,
            "TRADING_MODE": "paper",
            "adapters": list_exchanges(),
            "coinbase": CoinbaseAdapter().status(),
            "delta_india": DeltaExchangeIndiaAdapter().status(),
        }
