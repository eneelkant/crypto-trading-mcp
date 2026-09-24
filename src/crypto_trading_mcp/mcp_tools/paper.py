"""Paper-safe MCP tool surface (Phase 5)."""

from __future__ import annotations

from typing import Any

from crypto_trading_mcp.config.settings import get_settings
from crypto_trading_mcp.exchange.exceptions import LiveExecutionBlocked
from crypto_trading_mcp.exchange.factory import create_exchange
from crypto_trading_mcp.execution.planner import TradePlan
from crypto_trading_mcp.paper.engine import PaperTradingEngine
from crypto_trading_mcp.performance.metrics import compute_performance


class PaperToolSurface:
    def __init__(self, engine: PaperTradingEngine | None = None) -> None:
        self.engine = engine or PaperTradingEngine()

    def get_paper_status(self) -> dict[str, Any]:
        return self.engine.status()

    def get_paper_portfolio(self) -> dict[str, Any]:
        data = self.engine.exchange.portfolio.snapshot(self.engine.exchange.prices).to_dict()
        return {**data, "TRADING_MODE": "PAPER", "REAL_MONEY": "DISABLED"}

    def get_paper_orders(self) -> list[dict[str, Any]]:
        return [o.model_dump(mode="json") for o in self.engine.exchange.get_open_orders()]

    def get_paper_trades(self) -> list[dict[str, Any]]:
        return list(self.engine.exchange.trades)

    def get_paper_performance(self) -> dict[str, Any]:
        return {
            **compute_performance(self.engine.exchange.trades),
            "TRADING_MODE": "PAPER",
            "REAL_MONEY": "DISABLED",
        }

    def reset_paper_account(self) -> dict[str, Any]:
        return self.engine.reset()

    def run_paper_trade(self, plan_dict: dict[str, Any], market_price: float) -> dict[str, Any]:
        return self.paper_execute_trade(plan_dict, market_price)

    # Backward-compatible aliases
    def get_portfolio(self) -> dict[str, Any]:
        return self.get_paper_portfolio()

    def get_positions(self) -> list[dict[str, Any]]:
        return self.engine.exchange.get_positions()

    def get_open_orders(self) -> list[dict[str, Any]]:
        return self.get_paper_orders()

    def get_trade_status(self, order_id: str) -> dict[str, Any]:
        return self.engine.exchange.get_order(order_id).model_dump(mode="json")

    def get_performance(self) -> dict[str, Any]:
        return self.get_paper_performance()

    def propose_trade(self, plan: dict[str, Any]) -> dict[str, Any]:
        return {"plan": plan, "note": "Use validate_trade / run_paper_trade", "TRADING_MODE": "PAPER"}

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
        # Ensure factory never resolves a live venue in paper mode.
        try:
            create_exchange("paper")
        except LiveExecutionBlocked as exc:
            return {
                "executed": False,
                "reason_codes": ["LIVE_ADAPTER_BLOCKED"],
                "detail": str(exc),
                "execution_attempted": False,
            }
        plan = TradePlan.model_validate(plan_dict)
        return self.engine.execute_approved_plan(
            plan,
            market_price=market_price,
            asset_class=str(plan_dict.get("asset_class", "CRYPTO")),
            analysis={"consensus": {"decision": plan.side, "confidence": plan.confidence}},
        )
