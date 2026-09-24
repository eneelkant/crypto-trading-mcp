"""Phase 5 safety and failure-mode tests. No real exchange credentials or live orders."""

from __future__ import annotations

import os

import pytest

from crypto_trading_mcp.config.settings import Settings, get_settings
from crypto_trading_mcp.exchange.base import CoinbaseAdapter
from crypto_trading_mcp.exchange.exceptions import LiveExecutionBlocked
from crypto_trading_mcp.exchange.factory import create_exchange
from crypto_trading_mcp.exchange.fees import FeeEngine
from crypto_trading_mcp.exchange.models import Order, OrderSide, OrderStatus, OrderType
from crypto_trading_mcp.exchange.paper import PaperExchange
from crypto_trading_mcp.exchange.prediction import PredictionContract, PredictionMarketBook
from crypto_trading_mcp.exchange.slippage import SlippageEngine
from crypto_trading_mcp.execution.planner import TradePlan
from crypto_trading_mcp.paper.engine import PaperTradingEngine
from crypto_trading_mcp.paper.replay import Candle, DeterministicReplay, MarketDataReplay


def _plan(**kwargs) -> TradePlan:
    base = dict(
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
    base.update(kwargs)
    return TradePlan(**base)


def test_1_paper_mode_cannot_execute_live_order():
    with pytest.raises(LiveExecutionBlocked):
        create_exchange("coinbase")
    adapter = CoinbaseAdapter()
    with pytest.raises(LiveExecutionBlocked):
        adapter.create_order(
            Order(symbol="BTC/USD", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1),
            market_price=100.0,
        )


def test_2_live_trading_enabled_false_blocks_live(monkeypatch):
    monkeypatch.setenv("TRADING_MODE", "paper")
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "false")
    get_settings.cache_clear()
    settings = Settings(trading_mode="paper", live_trading_enabled=False)
    assert settings.live_trading_enabled is False
    eng = PaperTradingEngine()
    # Force live flag mid-flight
    object.__setattr__(eng.settings, "live_trading_enabled", True)
    result = eng.execute_approved_plan(_plan(), market_price=100.0)
    assert result["executed"] is False
    assert "PAPER_MODE_REQUIRED" in result["reason_codes"]
    get_settings.cache_clear()


def test_3_risk_rejection_prevents_paper_execution():
    eng = PaperTradingEngine()
    eng.reset()
    eng.start()
    bad = _plan(stop_loss=None, risk_reward_ratio=0.1)
    result = eng.execute_approved_plan(bad, market_price=100.0)
    assert result["executed"] is False
    assert result["execution_attempted"] is False
    assert result.get("reason_codes")


def test_4_kill_switch_prevents_new_orders(tmp_path, monkeypatch):
    stop = tmp_path / "STOP"
    stop.write_text("STOP\n", encoding="utf-8")
    monkeypatch.setattr(
        "crypto_trading_mcp.paper.engine.REPO_ROOT",
        tmp_path,
    )
    eng = PaperTradingEngine()
    eng.reset()
    # Recreate with stop file present
    eng = PaperTradingEngine()
    eng._check_stop_file()
    assert eng.kill_switch.active
    result = eng.execute_approved_plan(_plan(), market_price=100.0)
    assert result["executed"] is False
    assert "KILL_SWITCH_ACTIVE" in result["reason_codes"]


def test_5_llm_cannot_bypass_risk_controls():
    eng = PaperTradingEngine()
    eng.reset()
    eng.start()
    # LLM-like payload trying to force approve via metadata
    plan = _plan()
    plan.confluence = {"llm_override_risk": True, "force_approve": True}
    # Still must go through risk; oversized notional should fail
    huge = _plan(quantity=1000, notional=100_000, risk_amount=5000)
    result = eng.execute_approved_plan(huge, market_price=100.0)
    assert result["executed"] is False
    assert result["execution_attempted"] is False


def test_6_stale_market_data_prevents_new_trades():
    eng = PaperTradingEngine()
    eng.reset()
    eng.start()
    result = eng.execute_approved_plan(_plan(), market_price=100.0, market_data_stale=True)
    assert result["executed"] is False
    assert "STALE_MARKET_DATA" in result["reason_codes"]

    ex = PaperExchange(prices={"BTC/USD": 100})
    ex.mark_stale("BTC/USD")
    order = Order(symbol="BTC/USD", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1)
    rejected = ex.create_order(order, 100.0)
    assert rejected.status == OrderStatus.REJECTED
    assert rejected.reject_reason == "STALE_MARKET_DATA"


def test_7_exchange_failure_circuit_breaker():
    ex = PaperExchange(prices={"BTC/USD": 100})
    for _ in range(3):
        ex.simulate_failure("timeout")
    assert ex.halted
    assert ex.halt_reason == "API_FAILURE_CIRCUIT_BREAKER"
    order = Order(symbol="BTC/USD", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1)
    rejected = ex.create_order(order, 100.0)
    assert rejected.status == OrderStatus.REJECTED


def test_8_fees_reduce_realized_pnl():
    ex = PaperExchange(prices={"BTC/USD": 100})
    buy = Order(symbol="BTC/USD", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1)
    ex.create_order(buy, 100.0)
    sell = Order(symbol="BTC/USD", side=OrderSide.SELL, order_type=OrderType.MARKET, quantity=1)
    ex.create_order(sell, 110.0)
    assert ex.portfolio.fees_paid > 0
    # Gross move ~10; fees bite into net
    assert ex.portfolio.realized_pnl < 10.0


def test_9_slippage_reflected_in_fill_price():
    engine = SlippageEngine({"enabled": True, "model": "fixed_bps", "default_bps": 10})
    result = engine.apply(side="BUY", market_price=100.0)
    assert result.fill_price == pytest.approx(100.1)
    assert result.slippage_bps == 10
    ex = PaperExchange(prices={"BTC/USD": 100})
    order = Order(symbol="BTC/USD", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1)
    filled = ex.create_order(order, 100.0)
    assert filled.average_fill_price is not None
    assert filled.average_fill_price > 100.0
    assert filled.slippage > 0


def test_10_stop_loss_executes():
    ex = PaperExchange(prices={"BTC/USD": 100})
    buy = Order(
        symbol="BTC/USD",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=1,
        metadata={"stop_loss": 95.0, "take_profit": 150.0},
    )
    ex.create_order(buy, 100.0)
    ex.on_price_update("BTC/USD", 94.0)
    assert "BTC/USD" not in ex.portfolio.positions
    assert any(e["type"] == "POSITION_CLOSED" and e.get("reason") == "STOP_LOSS" for e in ex.events)


def test_11_take_profit_executes():
    ex = PaperExchange(prices={"BTC/USD": 100})
    buy = Order(
        symbol="BTC/USD",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=1,
        metadata={"stop_loss": 90.0, "take_profit": 110.0},
    )
    ex.create_order(buy, 100.0)
    ex.on_price_update("BTC/USD", 111.0)
    assert "BTC/USD" not in ex.portfolio.positions
    assert any(e["type"] == "POSITION_CLOSED" and e.get("reason") == "TAKE_PROFIT" for e in ex.events)


def test_12_trailing_stop_deterministic():
    ex = PaperExchange(prices={"BTC/USD": 100})
    buy = Order(
        symbol="BTC/USD",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=1,
        metadata={"stop_loss": 90.0},
    )
    ex.create_order(buy, 100.0)
    ex.configure_position_rules("BTC/USD", trailing_atr=2.0, trailing_mult=2.0)
    ex.on_price_update("BTC/USD", 110.0)
    stop1 = ex.portfolio.positions["BTC/USD"].stop_loss
    ex.on_price_update("BTC/USD", 120.0)
    stop2 = ex.portfolio.positions["BTC/USD"].stop_loss
    assert stop2 is not None and stop1 is not None
    assert stop2 >= stop1  # never widens risk for long
    # Replay same path
    ex2 = PaperExchange(prices={"BTC/USD": 100})
    buy2 = Order(
        symbol="BTC/USD",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=1,
        metadata={"stop_loss": 90.0},
    )
    ex2.create_order(buy2, 100.0)
    ex2.configure_position_rules("BTC/USD", trailing_atr=2.0, trailing_mult=2.0)
    ex2.on_price_update("BTC/USD", 110.0)
    ex2.on_price_update("BTC/USD", 120.0)
    assert ex2.portfolio.positions["BTC/USD"].stop_loss == stop2


def test_13_partial_fills_update_portfolio():
    ex = PaperExchange(prices={"BTC/USD": 100})
    ex.simulate_failure("partial_fill")
    # partial_fill mode shouldn't trip circuit breaker via simulate_failure for that mode
    ex.clear_failure()
    ex.failure_mode = "partial_fill"
    order = Order(symbol="BTC/USD", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=2)
    filled = ex.create_order(order, 100.0)
    assert filled.status == OrderStatus.PARTIALLY_FILLED
    assert filled.filled_quantity == pytest.approx(1.0)
    assert ex.portfolio.positions["BTC/USD"].quantity == pytest.approx(1.0)


def test_14_prediction_contracts_settle():
    ex = PaperExchange(prices={})
    book = PredictionMarketBook(ex)
    contract = PredictionContract(
        market_id="M1",
        question="Event?",
        outcome="YES",
        price=0.4,
        probability=0.4,
    )
    book.register_market(contract)
    book.buy(contract.symbol, 10, side=OrderSide.BUY_YES, strategy_id="prediction_market_ai")
    yes = book.resolve("M1", "YES")
    assert yes[0]["settlement_value"] == 1.0

    contract2 = PredictionContract(
        market_id="M2",
        question="Event2?",
        outcome="YES",
        price=0.4,
        probability=0.4,
    )
    book.register_market(contract2)
    book.buy(contract2.symbol, 10, side=OrderSide.BUY_YES)
    no = book.resolve("M2", "NO")
    assert no[0]["settlement_value"] == 0.0


def test_15_deterministic_replay_identical():
    plan = _plan()
    replay = DeterministicReplay()
    a = replay.run(initial_cash=10_000, prices=[("BTC/USD", 100.0)], plans=[plan])
    b = replay.run(initial_cash=10_000, prices=[("BTC/USD", 100.0)], plans=[plan])
    assert a["structural_hash"] == b["structural_hash"]

    eng = PaperTradingEngine()
    eng.reset()
    md = MarketDataReplay(eng)
    candles = [
        Candle("2026-01-01T00:00:00Z", 100, 105, 99, 102, 1000, "BTC/USD"),
        Candle("2026-01-01T01:00:00Z", 102, 108, 101, 107, 1100, "BTC/USD"),
    ]
    md.feed_many(candles)
    assert eng.exchange.prices["BTC/USD"] == 107.0


def test_16_no_real_exchange_credentials_required(monkeypatch):
    for key in (
        "COINBASE_API_KEY",
        "DELTA_API_KEY",
        "POLYMARKET_API_KEY",
        "KALSHI_API_KEY",
        "WALLET_PRIVATE_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    eng = PaperTradingEngine()
    eng.reset()
    eng.start()
    result = eng.execute_approved_plan(_plan(), market_price=100.0)
    assert result.get("executed") is True
    assert result["live_trading_enabled"] is False


def test_17_no_test_submits_real_exchange_order():
    # Accidental credentials must still never be used by paper path.
    os.environ["COINBASE_API_KEY"] = "should-never-be-used"
    try:
        with pytest.raises(LiveExecutionBlocked):
            create_exchange("coinbase")
        ex = create_exchange("paper", prices={"BTC/USD": 1.0})
        assert isinstance(ex, PaperExchange)
        assert ex.supports_live_execution is False
    finally:
        os.environ.pop("COINBASE_API_KEY", None)


@pytest.mark.parametrize(
    "reason",
    [
        "missing",
        "invalid_order",
        "insufficient_cash",
        "bad_price",
        "bad_quantity",
        "duplicate_order",
        "exchange_unavailable",
    ],
)
def test_failure_modes_deterministic(reason):
    ex = PaperExchange(prices={"BTC/USD": 100.0})
    if reason == "missing":
        order = Order(symbol="UNKNOWN/USD", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1)
        out = ex.create_order(order, market_price=None)
        assert out.status == OrderStatus.REJECTED
        assert out.reject_reason == "NO_MARKET_PRICE"
    elif reason == "invalid_order":
        order = Order(symbol="BTC/USD", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=0)
        out = ex.create_order(order, 100.0)
        assert out.reject_reason == "BAD_QUANTITY"
    elif reason == "insufficient_cash":
        order = Order(symbol="BTC/USD", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=10_000)
        out = ex.create_order(order, 100.0)
        assert out.status == OrderStatus.REJECTED
        assert "cash" in (out.reject_reason or "").lower()
    elif reason == "bad_price":
        order = Order(symbol="BTC/USD", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1)
        out = ex.create_order(order, 0.0)
        assert out.reject_reason == "BAD_PRICE"
    elif reason == "bad_quantity":
        order = Order(symbol="BTC/USD", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=-1)
        out = ex.create_order(order, 100.0)
        assert out.reject_reason == "BAD_QUANTITY"
    elif reason == "duplicate_order":
        o1 = Order(
            symbol="BTC/USD",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=1,
            limit_price=90,
            client_order_id="dup-1",
        )
        o2 = Order(
            symbol="BTC/USD",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=1,
            limit_price=90,
            client_order_id="dup-1",
        )
        ex.create_order(o1, 100.0)
        out = ex.create_order(o2, 100.0)
        assert out.reject_reason == "DUPLICATE_ORDER"
    else:
        ex.simulate_failure("exchange_unavailable")
        order = Order(symbol="BTC/USD", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1)
        out = ex.create_order(order, 100.0)
        assert out.status == OrderStatus.REJECTED


def test_fee_engine_config_driven():
    fees = FeeEngine({"default_rate": 0.001})
    result = fees.calculate(notional=1000, liquidity="taker")
    assert result.fee == pytest.approx(1.0)
    assert result.schedule == "default_rate"


def test_safe_restart_after_kill_switch(tmp_path, monkeypatch):
    monkeypatch.setattr("crypto_trading_mcp.paper.engine.REPO_ROOT", tmp_path)
    eng = PaperTradingEngine()
    eng.kill_switch.activate("operator")
    eng.exchange.halt("KILL_SWITCH_ACTIVE")
    # STOP file absent
    out = eng.safe_restart()
    assert out["restarted"] is True
    assert eng.running is True
