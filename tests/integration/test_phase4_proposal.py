from __future__ import annotations

import pytest

from crypto_trading_mcp.config.settings import Settings
from crypto_trading_mcp.llm import LLMRouter, MockLLMProvider
from crypto_trading_mcp.market.data import MockMarketData
from crypto_trading_mcp.orchestration.orchestrator import TradingOrchestrator
from crypto_trading_mcp.orchestration.proposal import default_mock_candles
from crypto_trading_mcp.risk.config import KillSwitch


@pytest.mark.asyncio
async def test_propose_pipeline_no_execution():
    settings = Settings(trading_mode="paper", live_trading_enabled=False, llm_provider="mock")
    orch = TradingOrchestrator(
        settings=settings,
        market_data=MockMarketData(candles=default_mock_candles(400)),
        llm_router=LLMRouter({"mock": MockLLMProvider()}),
    )
    result = await orch.propose("BTC-USD")
    assert result["execution_attempted"] is False
    assert result["live_trading_enabled"] is False
    assert "trade_plan" in result
    assert "risk" in result
    assert result["models"]["M3"] == "UNAVAILABLE"
    # Rejected plans must not proceed to execution (there is no execute path).
    if not result.get("risk", {}).get("approved", False):
        assert result["execution_attempted"] is False


@pytest.mark.asyncio
async def test_stale_data_rejects_proposal():
    settings = Settings(trading_mode="paper", live_trading_enabled=False, llm_provider="mock")
    orch = TradingOrchestrator(
        settings=settings,
        market_data=MockMarketData(candles=default_mock_candles(400), force_stale=True),
        llm_router=LLMRouter({"mock": MockLLMProvider()}),
    )
    result = await orch.propose("BTC/USD")
    assert result["execution_attempted"] is False
    codes = result["risk"].get("reason_codes", [])
    assert "STALE_MARKET_DATA" in codes or result["trade_plan"]["status"] == "NO_TRADE"


@pytest.mark.asyncio
async def test_kill_switch_blocks_approval():
    settings = Settings(trading_mode="paper", live_trading_enabled=False, llm_provider="mock")
    ks = KillSwitch()
    ks.activate("test")
    orch = TradingOrchestrator(
        settings=settings,
        market_data=MockMarketData(candles=default_mock_candles(400)),
        llm_router=LLMRouter({"mock": MockLLMProvider()}),
        kill_switch=ks,
    )
    result = await orch.propose("BTC/USD")
    assert result.get("risk", {}).get("approved") is False
