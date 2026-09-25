from __future__ import annotations

from crypto_trading_mcp.compliance.policy import CompliancePolicy, TaxSimulator, load_compliance_config
from crypto_trading_mcp.config.settings import Settings
from crypto_trading_mcp.exchange.prediction import (
    EnsembleAttribution,
    PredictionContract,
    PredictionMarketBook,
    brier_score,
)
from crypto_trading_mcp.exchange.paper import PaperExchange
from crypto_trading_mcp.execution.planner import TradePlan
from crypto_trading_mcp.paper.engine import PaperTradingEngine
from crypto_trading_mcp.paper.replay import DeterministicReplay
from crypto_trading_mcp.risk.correlation import CorrelationFilter


def test_prediction_contract_buy_and_settle():
    ex = PaperExchange(prices={})
    book = PredictionMarketBook(ex)
    contract = PredictionContract(
        market_id="ELECTION1",
        question="Will event X happen?",
        outcome="YES",
        price=0.56,
        probability=0.56,
        liquidity=100000,
    )
    book.register_market(contract)
    attr = EnsembleAttribution(
        grok_weight=0.2,
        claude_weight=0.2,
        gpt_weight=0.2,
        gemini_weight=0.2,
        deepseek_weight=0.2,
        individual_predictions={"gpt": 0.63},
        ensemble_probability=0.63,
        market_probability=0.56,
        edge=0.07,
    )
    order = book.buy(
        contract.symbol,
        10,
        side=__import__("crypto_trading_mcp.exchange.models", fromlist=["OrderSide"]).OrderSide.BUY_YES,
        strategy_id="prediction_market_ai",
        attribution=attr,
        model_probability=0.63,
    )
    assert order.status.value == "FILLED"
    assert abs(order.metadata["edge"] - 0.07) < 1e-9
    results = book.resolve("ELECTION1", "YES")
    assert results
    assert results[0]["settlement_value"] == 1.0
    assert brier_score(0.63, 1) < brier_score(0.10, 1)


def test_compliance_blocks_strategy():
    compliance = CompliancePolicy()
    compliance.config.blocked_strategies = ["bad_strat"]
    decision = compliance.evaluate(
        strategy_id="bad_strat",
        asset_class="CRYPTO",
        notional=100,
        daily_turnover=0,
    )
    assert not decision.approved
    assert "COMPLIANCE_BLOCKED" in decision.reason_codes


def test_tax_simulation_crypto_only():
    tax = TaxSimulator()
    crypto = tax.apply(gross_pnl=100, fees=1, notional=1000, asset_class="CRYPTO")
    equity = tax.apply(gross_pnl=100, fees=1, notional=1000, asset_class="EQUITY")
    assert crypto["estimated_tax"] > 0
    assert crypto["tds"] > 0
    assert "Not tax advice" in crypto["disclaimer"] or "simulation" in crypto["disclaimer"].lower()
    assert equity["transaction_tax"] > 0


def test_correlation_filter():
    filt = CorrelationFilter(max_correlation=0.9)
    series = [1, 2, 3, 4, 5, 6]
    ok, reasons = filt.evaluate(series, {"BTC/USD": series})
    assert not ok
    assert "CORRELATION_LIMIT" in reasons


def test_paper_engine_end_to_end_and_replay():
    eng = PaperTradingEngine()
    eng.reset()
    eng.start()
    plan = TradePlan(
        strategy_id="momentum_breakout_crypto",
        strategy_version="1.0.0",
        model_ids=["DONCHIAN20"],
        symbol="BTC/USD",
        side="LONG",
        entry_price=100.0,
        quantity=1.0,
        notional=100.0,
        stop_loss=95.0,
        take_profit=120.0,
        risk_amount=5.0,
        risk_reward_ratio=4.0,
        confidence=0.9,
        status="PROPOSED",
    )
    result = eng.execute_approved_plan(
        plan,
        market_price=100.0,
        asset_class="CRYPTO",
        analysis={"consensus": {"decision": "LONG", "confidence": 0.9}, "messages": {}},
        candidate_returns=[0.01, 0.02, -0.01, 0.0, 0.03],
    )
    assert result["execution_attempted"] is True
    assert result["live_trading_enabled"] is False
    assert result.get("executed") is True

    # Equity path
    eng.exchange.set_price("SPY", 400)
    spy_plan = TradePlan(
        strategy_id="mean_reversion_equity",
        strategy_version="1.0.0",
        model_ids=["SMA20_MR"],
        symbol="SPY",
        side="LONG",
        entry_price=400.0,
        quantity=0.4,
        notional=160.0,
        stop_loss=390.0,
        take_profit=420.0,
        risk_amount=4.0,
        risk_reward_ratio=2.0,
        confidence=0.8,
        status="PROPOSED",
        confluence={},
    )
    spy = eng.execute_approved_plan(spy_plan, market_price=400.0, asset_class="ETF")
    assert spy["executed"] is True

    # Commodity
    eng.exchange.set_price("GLD", 180)
    gld_plan = TradePlan(
        strategy_id="trend_following_commodities",
        strategy_version="1.0.0",
        model_ids=["EMA_CROSS"],
        symbol="GLD",
        side="LONG",
        entry_price=180.0,
        quantity=1.0,
        notional=180.0,
        stop_loss=170.0,
        take_profit=210.0,
        risk_amount=10.0,
        risk_reward_ratio=3.0,
        confidence=0.8,
        status="PROPOSED",
    )
    assert eng.execute_approved_plan(gld_plan, market_price=180.0, asset_class="COMMODITY")["executed"]

    replay = DeterministicReplay()
    plan2 = TradePlan(
        strategy_id="momentum_breakout_crypto",
        strategy_version="1.0.0",
        model_ids=["DONCHIAN20"],
        symbol="BTC/USD",
        side="LONG",
        entry_price=100.0,
        quantity=1.0,
        notional=100.0,
        stop_loss=95.0,
        take_profit=120.0,
        risk_amount=5.0,
        risk_reward_ratio=4.0,
        confidence=0.9,
        status="PROPOSED",
    )
    a = replay.run(initial_cash=10_000, prices=[("BTC/USD", 100.0)], plans=[plan2])
    b = replay.run(initial_cash=10_000, prices=[("BTC/USD", 100.0)], plans=[plan2])
    assert a["structural_hash"] == b["structural_hash"]


def test_paper_mode_required_settings():
    _, tax_cfg = load_compliance_config()
    assert tax_cfg.enabled
    settings = Settings(trading_mode="paper", live_trading_enabled=False)
    assert settings.trading_mode == "paper"
    assert settings.live_trading_enabled is False
