"""Paper-safe MCP tool surface (Phase 5)."""

from __future__ import annotations

from typing import Any

from crypto_trading_mcp.config.settings import get_settings
from crypto_trading_mcp.execution.planner import TradePlan
from crypto_trading_mcp.paper.engine import PaperTradingEngine
from crypto_trading_mcp.performance.metrics import compute_performance


class PaperToolSurface:
    def __init__(self, engine: PaperTradingEngine | None = None) -> None:
        self.engine = engine or PaperTradingEngine()

    def get_portfolio(self) -> dict[str, Any]:
        return self.engine.exchange.portfolio.snapshot(self.engine.exchange.prices).to_dict()

    def get_positions(self) -> list[dict[str, Any]]:
        return self.engine.exchange.get_positions()

    def get_open_orders(self) -> list[dict[str, Any]]:
        return [o.model_dump(mode="json") for o in self.engine.exchange.get_open_orders()]

    def get_trade_status(self, order_id: str) -> dict[str, Any]:
        return self.engine.exchange.get_order(order_id).model_dump(mode="json")

    def get_performance(self) -> dict[str, Any]:
        return compute_performance(self.engine.exchange.trades)

    def propose_trade(self, plan: dict[str, Any]) -> dict[str, Any]:
        return {"plan": plan, "note": "Use validate_trade / paper_execute_trade"}

    def validate_trade(self, plan_dict: dict[str, Any]) -> dict[str, Any]:
        settings = get_settings()
        if settings.trading_mode != "paper" or settings.live_trading_enabled:
            return {"approved": False, "reason_codes": ["PAPER_MODE_REQUIRED"]}
        return {"approved": True, "reason_codes": ["VALIDATION_OK"], "execution_allowed": False}

    def paper_execute_trade(self, plan_dict: dict[str, Any], market_price: float) -> dict[str, Any]:
        settings = get_settings()
        if settings.trading_mode != "paper":
            return {
                "executed": False,
                "reason_codes": ["TRADING_MODE_NOT_PAPER"],
                "execution_attempted": False,
            }
        if settings.live_trading_enabled:
            return {
                "executed": False,
                "reason_codes": ["LIVE_TRADING_ENABLED_BLOCKED"],
                "execution_attempted": False,
            }
        plan = TradePlan.model_validate(plan_dict)
        return self.engine.execute_approved_plan(
            plan,
            market_price=market_price,
            asset_class=str(plan_dict.get("asset_class", "CRYPTO")),
            analysis={"consensus": {"decision": plan.side, "confidence": plan.confidence}},
        )
