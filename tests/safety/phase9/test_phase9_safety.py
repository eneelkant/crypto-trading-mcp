from __future__ import annotations

import pytest

from crypto_trading_mcp.autonomous.loop import AutonomousPaperLoop
from crypto_trading_mcp.config.settings import get_settings
from crypto_trading_mcp.exchange.factory import create_exchange
from crypto_trading_mcp.exchange.exceptions import LiveExecutionBlocked
from crypto_trading_mcp.market.data import MockMarketData
from crypto_trading_mcp.market.gateway import MarketDataGateway


def test_phase9_defaults_paper_only():
    s = get_settings()
    assert s.trading_mode == "paper"
    assert s.live_trading_enabled is False


def test_loop_rejects_live_config(monkeypatch):
    loop = AutonomousPaperLoop(
        config={"live_trading_enabled": True, "persist_state": False},
        market=MarketDataGateway(MockMarketData()),
    )
    with pytest.raises(RuntimeError):
        loop.start(background=False, max_cycles=1)


def test_create_exchange_coinbase_still_blocked_by_default():
    with pytest.raises(LiveExecutionBlocked):
        create_exchange("coinbase")
