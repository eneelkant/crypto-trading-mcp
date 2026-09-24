from __future__ import annotations

from typing import Any

from crypto_trading_mcp.agents.messages import AgentMessage
from crypto_trading_mcp.agents.registry import AgentRegistry, build_default_registry
from crypto_trading_mcp.config.settings import Settings, get_settings
from crypto_trading_mcp.llm import LLMRouter
from crypto_trading_mcp.market.data import MockMarketData, PublicCCXTMarketData
from crypto_trading_mcp.orchestration.context import ExecutionContext
from crypto_trading_mcp.orchestration.state_machine import StateMachine, TradingState

ANALYSIS_PIPELINE = [
    "market_intelligence",
    "technical_analysis",
    "trend",
    "sentiment",
    "on_chain",
    "macro_event",
    "strategy",
    "bull",
    "bear",
    "consensus",
]


class TradingOrchestrator:
    """Runs the analytical pipeline. Does not execute trades."""

    def __init__(
        self,
        *,
        registry: AgentRegistry | None = None,
        settings: Settings | None = None,
        llm_router: LLMRouter | None = None,
        market_data: Any | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.settings.assert_no_live_trading()
        self.registry = registry or build_default_registry()
        self.llm_router = llm_router or LLMRouter.from_settings(self.settings)
        self.market_data = market_data or PublicCCXTMarketData(
            default_exchange_id=self.settings.default_exchange_id,
            max_age_seconds=float(self.settings.market_data_max_age_seconds),
        )
        self.state_machine = StateMachine()

    async def analyze(
        self,
        symbol: str,
        *,
        timeframe: str = "1h",
        exchange_id: str | None = None,
    ) -> dict[str, Any]:
        if self.settings.real_money_enabled:
            raise RuntimeError("Live trading is disabled in Phase 3")

        context = ExecutionContext(
            symbol=symbol.upper(),
            timeframe=timeframe,
            exchange_id=(exchange_id or self.settings.default_exchange_id).lower(),
            settings=self.settings,
            market_data=self.market_data,
            llm_router=self.llm_router,
            allow_execution=False,
        )

        self.state_machine = StateMachine(TradingState.IDLE)
        self.state_machine.transition(TradingState.SCANNING)
        self.state_machine.transition(TradingState.ANALYZING)

        messages: dict[str, AgentMessage] = {}
        try:
            for agent_id in ANALYSIS_PIPELINE:
                if agent_id in {"bull", "bear", "consensus"}:
                    if self.state_machine.state == TradingState.ANALYZING:
                        self.state_machine.transition(TradingState.DEBATING)
                message = await self.registry.get(agent_id).run(context)
                messages[agent_id] = message
            self.state_machine.transition(TradingState.IDLE)
        except Exception:
            if self.state_machine.state != TradingState.HALTED:
                try:
                    self.state_machine.transition(TradingState.FAILED)
                except ValueError:
                    pass
            raise

        consensus = messages.get("consensus")
        return {
            "symbol": context.symbol,
            "timeframe": context.timeframe,
            "exchange_id": context.exchange_id,
            "trading_mode": self.settings.trading_mode,
            "live_trading_enabled": self.settings.live_trading_enabled,
            "real_money": False,
            "execution_attempted": False,
            "state": self.state_machine.state.value,
            "consensus": consensus.payload if consensus else {},
            "messages": {key: msg.to_audit_dict() for key, msg in messages.items()},
        }


def build_test_orchestrator(**kwargs: Any) -> TradingOrchestrator:
    settings = kwargs.pop("settings", None) or get_settings()
    market_data = kwargs.pop("market_data", None) or MockMarketData()
    llm_router = kwargs.pop("llm_router", None) or LLMRouter.from_settings(settings)
    return TradingOrchestrator(
        settings=settings,
        market_data=market_data,
        llm_router=llm_router,
        **kwargs,
    )
