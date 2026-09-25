from __future__ import annotations

from crypto_trading_mcp.agents.base import BaseAgent


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        self._agents[agent.agent_id] = agent

    def get(self, agent_id: str) -> BaseAgent:
        if agent_id not in self._agents:
            raise KeyError(f"Agent not registered: {agent_id}")
        return self._agents[agent_id]

    def list(self) -> list[BaseAgent]:
        return list(self._agents.values())

    def ids(self) -> list[str]:
        return list(self._agents.keys())


def build_default_registry() -> AgentRegistry:
    from crypto_trading_mcp.agents.implementations import (
        BearAnalystAgent,
        BullAnalystAgent,
        ConsensusAgent,
        MacroEventAgent,
        MarketIntelligenceAgent,
        OnChainAgent,
        SentimentAgent,
        StrategyAgent,
        TechnicalAnalysisAgent,
        TrendAgent,
    )

    registry = AgentRegistry()
    for agent in (
        MarketIntelligenceAgent(),
        TechnicalAnalysisAgent(),
        TrendAgent(),
        SentimentAgent(),
        OnChainAgent(),
        MacroEventAgent(),
        StrategyAgent(),
        BullAnalystAgent(),
        BearAnalystAgent(),
        ConsensusAgent(),
    ):
        registry.register(agent)
    return registry
