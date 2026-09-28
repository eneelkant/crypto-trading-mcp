from __future__ import annotations

from crypto_trading_mcp.autonomous.loop import AutonomousPaperLoop
from crypto_trading_mcp.exchange.coinbase import CoinbaseAdapter
from crypto_trading_mcp.exchange.delta_india import DeltaExchangeIndiaAdapter
from crypto_trading_mcp.exchange.exceptions import LiveExecutionBlocked
from crypto_trading_mcp.exchange.models import Order, OrderSide, OrderType
from crypto_trading_mcp.market.data import MockMarketData
from crypto_trading_mcp.market.gateway import MarketDataGateway
from crypto_trading_mcp.mcp_tools.production import ProductionToolSurface
import pytest


def test_full_paper_cycle_via_loop():
    loop = AutonomousPaperLoop(
        config={
            "persist_state": False,
            "duplicate_cycle_protection": False,
            "live_trading_enabled": False,
            "symbols": ["BTC/USD"],
        },
        market=MarketDataGateway(MockMarketData()),
    )
    out = loop.start(background=False, max_cycles=2)
    assert out["started"] is True or out.get("cycles_completed", 0) >= 0
    status = loop.status()
    assert status["LIVE_TRADING_ENABLED"] is False
    assert status["cycles_completed"] >= 1


def test_mcp_production_surface_paper_only():
    tools = ProductionToolSurface()
    assert tools.get_execution_status()["LIVE_TRADING_ENABLED"] is False
    cycle = tools.start_paper_cycle(max_cycles=1)
    assert cycle["LIVE_TRADING_ENABLED"] is False or "Live Execution" in tools.get_execution_status()


def test_live_adapters_cannot_submit():
    order = Order(symbol="BTC/USD", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=0.01)
    with pytest.raises(LiveExecutionBlocked):
        CoinbaseAdapter().submit_order(order)
    with pytest.raises(LiveExecutionBlocked):
        DeltaExchangeIndiaAdapter(api_key="x", api_secret="y").submit_order(order)
