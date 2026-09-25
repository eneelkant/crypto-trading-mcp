from __future__ import annotations

import json

import pytest

from crypto_trading_mcp.agents.registry import build_default_registry
from crypto_trading_mcp.config.settings import Settings
from crypto_trading_mcp.llm import LLMError, LLMRouter, MockLLMProvider
from crypto_trading_mcp.market.data import MockMarketData
from crypto_trading_mcp.orchestration.context import ExecutionContext
from crypto_trading_mcp.orchestration.orchestrator import TradingOrchestrator
from crypto_trading_mcp.providers.external import ProviderResult


@pytest.fixture
def settings() -> Settings:
    return Settings(
        trading_mode="paper",
        live_trading_enabled=False,
        llm_provider="mock",
        model_name="mock-analyst",
    )


@pytest.mark.asyncio
async def test_full_analysis_pipeline(settings: Settings):
    orch = TradingOrchestrator(
        settings=settings,
        market_data=MockMarketData(),
        llm_router=LLMRouter({"mock": MockLLMProvider()}),
    )
    result = await orch.analyze("BTC/USD")
    assert result["live_trading_enabled"] is False
    assert result["real_money"] is False
    assert result["execution_attempted"] is False
    assert "consensus" in result["messages"]
    assert result["consensus"]["decision"] in {"LONG", "SHORT", "NEUTRAL", "NO_TRADE"}
    assert result["messages"]["sentiment"]["payload"]["status"] == "UNAVAILABLE"
    assert result["messages"]["on_chain"]["payload"]["status"] == "UNAVAILABLE"
    assert result["messages"]["macro_event"]["payload"]["status"] == "UNAVAILABLE"


@pytest.mark.asyncio
async def test_stale_market_data_forces_no_trade(settings: Settings):
    orch = TradingOrchestrator(
        settings=settings,
        market_data=MockMarketData(force_stale=True, max_age_seconds=30),
        llm_router=LLMRouter({"mock": MockLLMProvider()}),
    )
    result = await orch.analyze("BTC/USD")
    assert result["consensus"]["decision"] == "NO_TRADE"
    assert "stale_or_missing_market_data" in result["consensus"]["risk_flags"]


@pytest.mark.asyncio
async def test_missing_market_data_forces_no_trade(settings: Settings):
    orch = TradingOrchestrator(
        settings=settings,
        market_data=MockMarketData(fail=True),
        llm_router=LLMRouter({"mock": MockLLMProvider()}),
    )
    result = await orch.analyze("BTC/USD")
    assert result["consensus"]["decision"] == "NO_TRADE"


@pytest.mark.asyncio
async def test_bull_bear_independence(settings: Settings):
    """Bull and Bear must not receive each other's outputs."""

    seen: dict[str, str] = {}

    class RecordingMock(MockLLMProvider):
        def complete(self, *, prompt, model, system=None, temperature=0.0):
            text = f"{system or ''}\n{prompt}"
            if "Bull Analyst" in (system or ""):
                assert "Bear Analyst" not in prompt
                assert '"bull"' not in prompt.lower() or "bullish" in prompt.lower()
                # Ensure bear payload key not present as agent output.
                assert "downside_catalysts" not in prompt
                seen["bull"] = prompt
            if "Bear Analyst" in (system or ""):
                assert "supporting_evidence" in prompt or "technical" in prompt.lower()
                assert "catalysts" not in prompt or "downside" in prompt.lower()
                # Bull-only field from bull output should not appear.
                assert '"thesis": "Constructive momentum' not in prompt
                seen["bear"] = prompt
            return super().complete(
                prompt=prompt, model=model, system=system, temperature=temperature
            )

    orch = TradingOrchestrator(
        settings=settings,
        market_data=MockMarketData(),
        llm_router=LLMRouter({"mock": RecordingMock()}),
    )
    await orch.analyze("BTC/USD")
    assert "bull" in seen and "bear" in seen


@pytest.mark.asyncio
async def test_malformed_llm_json_fail_closed(settings: Settings):
    class BadJSON(MockLLMProvider):
        def complete(self, *, prompt, model, system=None, temperature=0.0):
            from crypto_trading_mcp.llm.providers import LLMResponse

            return LLMResponse(
                content="not-json",
                provider="mock",
                model=model,
                latency_ms=1.0,
            )

    router = LLMRouter({"mock": BadJSON()})
    with pytest.raises(LLMError):
        router.parse_json_content("not-json")

    orch = TradingOrchestrator(
        settings=settings,
        market_data=MockMarketData(),
        llm_router=router,
    )
    # Technical analysis will error on malformed JSON → agent error envelope.
    result = await orch.analyze("BTC/USD")
    # Pipeline continues; consensus fail-closed if market intel broken.
    assert result["execution_attempted"] is False


@pytest.mark.asyncio
async def test_unavailable_llm_does_not_execute(settings: Settings):
    class DeadProvider(MockLLMProvider):
        def available(self) -> bool:
            return False

    orch = TradingOrchestrator(
        settings=settings,
        market_data=MockMarketData(),
        llm_router=LLMRouter({"mock": DeadProvider()}),
    )
    result = await orch.analyze("BTC/USD")
    assert result["execution_attempted"] is False
    assert result["live_trading_enabled"] is False


@pytest.mark.asyncio
async def test_context_forbids_execution(settings: Settings):
    context = ExecutionContext(
        symbol="BTC/USD",
        settings=settings,
        allow_execution=True,
    )
    with pytest.raises(RuntimeError):
        context.require_no_execution()


def test_live_defaults_disabled(settings: Settings):
    assert settings.trading_mode == "paper"
    assert settings.live_trading_enabled is False
    assert settings.real_money_enabled is False


def test_registry_has_ten_agents():
    registry = build_default_registry()
    assert len(registry.ids()) == 10


@pytest.mark.asyncio
async def test_optional_providers_can_be_available(settings: Settings):
    from crypto_trading_mcp.agents.implementations import SentimentAgent

    class FakeSentiment:
        def fetch(self, symbol: str) -> ProviderResult:
            return ProviderResult(
                status="AVAILABLE",
                data={"score": 0.2},
                sources=[{"name": "fixture", "timestamp": "2026-01-01T00:00:00Z"}],
            )

    agent = SentimentAgent(provider=FakeSentiment())
    context = ExecutionContext(
        symbol="BTC/USD",
        settings=settings,
        llm_router=LLMRouter({"mock": MockLLMProvider()}),
        allow_execution=False,
    )
    message = await agent.run(context)
    assert message.payload["status"] == "AVAILABLE"
