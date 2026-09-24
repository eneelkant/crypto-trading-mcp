"""Internal MCP tool interface stubs for Phase 4 (no execute_trade)."""

from __future__ import annotations

from typing import Any

from crypto_trading_mcp.orchestration.orchestrator import TradingOrchestrator
from crypto_trading_mcp.risk.config import load_risk_config
from crypto_trading_mcp.strategy.repository import StrategyKnowledgeService


class Phase4ToolSurface:
    """Prepared interfaces for future MCP registration. No order execution."""

    def __init__(self, orchestrator: TradingOrchestrator | None = None) -> None:
        self.orchestrator = orchestrator or TradingOrchestrator()
        self.knowledge = StrategyKnowledgeService()

    def get_risk_status(self) -> dict[str, Any]:
        cfg = load_risk_config()
        return {
            "kill_switch": cfg.kill_switch.model_dump(),
            "global_risk": cfg.risk.model_dump(),
            "live_trading_enabled": False,
        }

    def get_portfolio(self) -> dict[str, Any]:
        return self.orchestrator.portfolio.snapshot().to_dict()

    def get_positions(self) -> list[dict[str, Any]]:
        return [p.model_dump(mode="json") for p in self.orchestrator.portfolio.snapshot().positions]

    async def propose_trade(self, symbol: str) -> dict[str, Any]:
        return await self.orchestrator.propose(symbol)

    def validate_trade(self, proposal_result: dict[str, Any]) -> dict[str, Any]:
        risk = proposal_result.get("risk", {})
        return {
            "approved": bool(risk.get("approved")),
            "reason_codes": risk.get("reason_codes", []),
            "execution_allowed": False,
        }

    def get_strategy(self, strategy_id: str = "multi_model_po3_vwap") -> dict[str, Any]:
        return self.knowledge.knowledge_bundle(strategy_id)

    def list_strategies(self) -> list[dict[str, Any]]:
        return [
            {
                "strategy_id": r.strategy_id,
                "version": r.version,
                "name": r.name,
                "status": r.status.value,
                "config_hash": r.config_hash,
            }
            for r in self.knowledge.repository.list()
        ]

    def get_strategy_model(self, model_id: str) -> dict[str, Any]:
        record = self.knowledge.get_strategy()
        model = record.config.model_by_id(model_id)
        if model is None:
            raise KeyError(model_id)
        return {
            **model.model_dump(),
            "primary_agents": self.knowledge.primary_agents_for(model_id),
        }
