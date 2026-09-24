from __future__ import annotations

import pytest

from crypto_trading_mcp.risk.config import KillSwitch, merge_effective_limits, pair_allowed
from crypto_trading_mcp.risk.engine import RiskEngine
from crypto_trading_mcp.risk.models import (
    GlobalRiskLimits,
    PortfolioRiskSnapshot,
    RiskReasonCode,
    TradeProposal,
)
from crypto_trading_mcp.strategy.repository import StrategyKnowledgeService


def _proposal(**kwargs) -> TradeProposal:
    base = dict(
        symbol="BTC/USD",
        side="LONG",
        quantity=0.01,
        notional=100.0,
        entry_price=10000.0,
        stop_loss=9900.0,
        take_profit=10400.0,
        current_price=10000.0,
        estimated_fees=0.1,
        estimated_slippage_pct=0.0001,
        leverage=1.0,
        confidence=0.8,
        model_ids=["M1"],
        liquidity_usd=1_000_000,
        market_data_stale=False,
        bars_since_last_trade=100,
    )
    base.update(kwargs)
    return TradeProposal(**base)


def _portfolio(**kwargs) -> PortfolioRiskSnapshot:
    base = dict(
        equity=10_000.0,
        available_cash=10_000.0,
        positions_exposure=0.0,
        daily_pnl=0.0,
        drawdown_pct=0.0,
        trades_today=0,
        kill_switch_active=False,
        trading_halted=False,
    )
    base.update(kwargs)
    return PortfolioRiskSnapshot(**base)


@pytest.fixture
def strategy():
    return StrategyKnowledgeService().get_strategy().config


def test_global_risk_wins_over_strategy(strategy):
    global_limits = GlobalRiskLimits(max_daily_loss_pct=0.03, max_trade_pct=0.005)
    effective = merge_effective_limits(global_limits, strategy)
    # Strategy daily loss 5% -> 0.05, global 0.03 wins.
    assert effective["max_daily_loss_pct"] == 0.03
    # Strategy risk 1% = 0.01, global max_trade 0.5% = 0.005 wins for risk_per_trade.
    assert effective["risk_per_trade_pct"] == 0.005


def test_risk_ok(strategy):
    engine = RiskEngine()
    # Tiny trade within limits.
    decision = engine.evaluate(
        _proposal(quantity=0.001, notional=10.0, entry_price=10000, stop_loss=9900, take_profit=10400),
        _portfolio(),
        strategy,
    )
    assert decision.approved
    assert RiskReasonCode.RISK_OK in decision.reason_codes


@pytest.mark.parametrize(
    "kwargs,code",
    [
        ({"notional": 5000, "quantity": 0.5}, RiskReasonCode.POSITION_LIMIT_EXCEEDED),
        ({"estimated_slippage_pct": 0.05}, RiskReasonCode.SLIPPAGE_LIMIT),
        ({"leverage": 5}, RiskReasonCode.LEVERAGE_LIMIT),
        ({"symbol": "DOGE/USD"}, RiskReasonCode.PAIR_NOT_ALLOWED),
        ({"market_data_stale": True}, RiskReasonCode.STALE_MARKET_DATA),
        ({"stop_loss": None}, RiskReasonCode.STOP_LOSS_REQUIRED),
        ({"stop_loss": 11000}, RiskReasonCode.INVALID_STOP),
        ({"take_profit": 10050}, RiskReasonCode.RISK_REWARD_TOO_LOW),
        ({"liquidity_usd": 10}, RiskReasonCode.INSUFFICIENT_LIQUIDITY),
        ({"model_ids": []}, RiskReasonCode.NO_VALID_MODEL),
        ({"confidence": 0.1}, RiskReasonCode.INSUFFICIENT_CONFIDENCE),
        ({"bars_since_last_trade": 1}, RiskReasonCode.COOLDOWN_ACTIVE),
    ],
)
def test_individual_risk_checks(strategy, kwargs, code):
    engine = RiskEngine()
    decision = engine.evaluate(_proposal(**kwargs), _portfolio(), strategy)
    assert not decision.approved
    assert code in decision.reason_codes


def test_daily_loss_drawdown_trade_count(strategy):
    engine = RiskEngine()
    d1 = engine.evaluate(_proposal(), _portfolio(daily_pnl=-400), strategy)
    assert RiskReasonCode.DAILY_LOSS_LIMIT in d1.reason_codes
    d2 = engine.evaluate(_proposal(), _portfolio(drawdown_pct=0.2), strategy)
    assert RiskReasonCode.DRAWDOWN_LIMIT in d2.reason_codes
    d3 = engine.evaluate(_proposal(), _portfolio(trades_today=100), strategy)
    assert RiskReasonCode.TRADE_COUNT_LIMIT in d3.reason_codes


def test_kill_switch(strategy):
    ks = KillSwitch()
    ks.activate("test")
    engine = RiskEngine(kill_switch=ks)
    decision = engine.evaluate(_proposal(), _portfolio(), strategy)
    assert RiskReasonCode.KILL_SWITCH_ACTIVE in decision.reason_codes
    with pytest.raises(PermissionError):
        ks.deactivate()
    ks.deactivate(operator_authorized=True)
    assert not ks.active


def test_pair_allowed_normalization():
    assert pair_allowed("BTC-USD", ["BTC/USD"])
    assert pair_allowed("BTCUSDT", ["BTCUSDT", "ETH/USD"])
