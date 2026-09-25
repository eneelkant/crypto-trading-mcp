from __future__ import annotations

from crypto_trading_mcp.execution.planner import TradePlanner
from crypto_trading_mcp.risk.models import GlobalRiskLimits
from crypto_trading_mcp.strategy.repository import StrategyKnowledgeService


def test_planner_no_trade_on_neutral():
    record = StrategyKnowledgeService().get_strategy()
    planner = TradePlanner(GlobalRiskLimits())
    plan = planner.plan(
        strategy_record=record,
        consensus={"decision": "NEUTRAL", "confidence": 0.9},
        feature_bundle={"confluence": {"confirmed_ids": ["M1"]}, "features": {"last_close": 100}},
        equity=10_000,
    )
    assert plan.status == "NO_TRADE"


def test_planner_no_valid_model():
    record = StrategyKnowledgeService().get_strategy()
    planner = TradePlanner()
    plan = planner.plan(
        strategy_record=record,
        consensus={"decision": "LONG", "confidence": 0.9},
        feature_bundle={
            "confluence": {"confirmed_ids": []},
            "features": {"last_close": 100},
            "stop_long": 95,
        },
        equity=10_000,
    )
    assert plan.status == "NO_TRADE"
    assert plan.reason == "NO_VALID_MODEL"


def test_planner_sizes_long_with_rr():
    record = StrategyKnowledgeService().get_strategy()
    planner = TradePlanner(GlobalRiskLimits(max_trade_pct=0.02, max_position_pct=0.1))
    plan = planner.plan(
        strategy_record=record,
        consensus={"decision": "LONG", "confidence": 0.8},
        feature_bundle={
            "confluence": {"confirmed_ids": ["M1", "M2"]},
            "features": {"last_close": 100.0, "atr_14": {"value": 2.0}},
            "stop_long": 95.0,
        },
        equity=10_000,
    )
    assert plan.status == "PROPOSED"
    assert plan.side == "LONG"
    assert plan.quantity > 0
    assert plan.stop_loss == 95.0
    assert plan.risk_reward_ratio is not None
    assert plan.risk_reward_ratio >= record.config.risk_management.min_risk_reward_ratio
