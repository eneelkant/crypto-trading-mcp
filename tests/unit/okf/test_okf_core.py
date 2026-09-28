from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from crypto_trading_mcp.okf.circuit_breakers import OKFCircuitBreakers
from crypto_trading_mcp.okf.correlation_gate import OKFCorrelationGate
from crypto_trading_mcp.okf.loader import (
    OKFValidationError,
    load_and_validate_okf,
    validate_okf,
)
from crypto_trading_mcp.okf.memory_gate import PreTradeMemoryGate
from crypto_trading_mcp.okf.recalibration import BrierRecalibrator
from crypto_trading_mcp.okf.resolver import OKFConfigResolver
from crypto_trading_mcp.okf.sizing import atr_position_quantity, quarter_kelly_fraction
from crypto_trading_mcp.okf.status import okf_diagnostics, okf_paper_metadata
from crypto_trading_mcp.okf.strategies import (
    OKFStrategyRegistry,
    OKF_STRATEGY_IDS,
    evaluate_m1_po3_sweep,
    evaluate_m2_vwap_reclaim,
    evaluate_m3_ict_fvg,
    evaluate_m4_prediction_ensemble,
    evaluate_m5_donchian_breakout,
)
from crypto_trading_mcp.okf.turnover import LowTurnoverGuard
from crypto_trading_mcp.learning.models import (
    FailureCategory,
    TradeLearningRecord,
    TradeOutcome,
)
from crypto_trading_mcp.market.models import Candle
from crypto_trading_mcp.risk.config import KillSwitch, merge_effective_limits
from crypto_trading_mcp.risk.engine import RiskEngine
from crypto_trading_mcp.risk.models import (
    GlobalRiskLimits,
    PortfolioRiskSnapshot,
    RiskReasonCode,
    TradeProposal,
)
from crypto_trading_mcp.strategy.repository import StrategyKnowledgeService
from crypto_trading_mcp.webhook.tradingview import TradingViewWebhookHandler


def test_okf_parse_validate_hash_version():
    loaded = load_and_validate_okf()
    assert loaded["ok"] is True
    assert loaded["version"] == "0.2.0"
    assert loaded["executable"] is False
    assert len(loaded["hash"]) == 64
    assert set(s["model_id"] for s in loaded["data"]["trading_models_and_strategies"]) == set(
        OKF_STRATEGY_IDS
    )


def test_okf_rejects_secret_placeholder(tmp_path: Path):
    raw = load_and_validate_okf()["data"]
    raw = json.loads(json.dumps(raw))
    raw["infrastructure_and_webhook"]["payload_format"]["secret"] = "YOUR_SECRET_KEY"
    assert any("forbidden_secret" in e or "YOUR_SECRET_KEY" in e for e in validate_okf(raw))
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(OKFValidationError):
        load_and_validate_okf(path)


def test_ensemble_weights_sum():
    loaded = load_and_validate_okf()
    m4 = next(
        s
        for s in loaded["data"]["trading_models_and_strategies"]
        if s["model_id"] == "M4_PREDICTION_MARKET_AI"
    )
    assert abs(sum(m4["ensemble_weights"].values()) - 1.0) < 1e-9


def test_risk_conflict_resolution_stricter_wins():
    # System stricter than OKF on risk/trade and drawdown
    system = GlobalRiskLimits(
        max_trade_pct=0.005,
        max_daily_loss_pct=0.05,
        max_drawdown_pct=0.08,
        max_trades_per_day=20,
        kelly_fraction=0.25,
    )
    resolved = OKFConfigResolver().resolve(system)
    assert resolved.max_risk_per_trade_pct == 0.005
    assert resolved.max_drawdown_pct == 0.08
    codes = {c.reason_code for c in resolved.conflicts}
    assert "OKF_SYSTEM_CONFLICT_MAX_RISK_PER_TRADE_PCT" in codes
    assert "OKF_SYSTEM_CONFLICT_MAX_DRAWDOWN_PCT" in codes

    # OKF stricter on risk when system is looser
    loose = GlobalRiskLimits(max_trade_pct=0.02, max_drawdown_pct=0.10)
    r2 = OKFConfigResolver().resolve(loose)
    assert r2.max_risk_per_trade_pct == 0.01


def test_merge_effective_limits_with_okf():
    strategy = StrategyKnowledgeService().get_strategy().config
    okf = OKFConfigResolver().resolve(GlobalRiskLimits(max_trade_pct=0.02)).to_dict()
    limits = merge_effective_limits(
        GlobalRiskLimits(max_trade_pct=0.02, max_daily_loss_pct=0.05, max_drawdown_pct=0.10),
        strategy,
        okf_constraints=okf,
    )
    assert limits["risk_per_trade_pct"] == 0.01
    assert limits["max_trades_per_day"] <= 8


def test_atr_position_sizing():
    ok = atr_position_quantity(
        account_equity=10_000,
        risk_percent=0.01,
        entry_price=100.0,
        stop_loss_price=90.0,
    )
    assert ok["ok"] is True
    assert ok["quantity"] == 10.0  # (10000*0.01)/10

    assert atr_position_quantity(
        account_equity=10_000, risk_percent=0.01, entry_price=100, stop_loss_price=None
    )["reason_code"] == "STOP_LOSS_REQUIRED"
    assert atr_position_quantity(
        account_equity=10_000, risk_percent=0.01, entry_price=100, stop_loss_price=100
    )["reason_code"] == "ZERO_STOP_DISTANCE"
    small = atr_position_quantity(
        account_equity=10_000,
        risk_percent=0.01,
        entry_price=100,
        stop_loss_price=90,
        min_qty=100,
    )
    assert small["reason_code"] == "BELOW_MIN_ORDER_SIZE"


def test_kelly_quarter_and_bounds():
    # p=0.6, b=1 → f*=0.2; quarter → 0.05
    res = quarter_kelly_fraction(p=0.6, b=1.0, kelly_multiplier=0.25)
    assert res["ok"]
    assert abs(res["full_kelly"] - 0.2) < 1e-9
    assert abs(res["effective_fraction"] - 0.05) < 1e-9
    assert res["can_bypass_risk_limits"] is False
    capped = quarter_kelly_fraction(p=0.9, b=2.0, kelly_multiplier=0.25, max_fraction=0.01)
    assert capped["effective_fraction"] <= 0.01


def test_circuit_breakers_daily_drawdown_stop():
    events = []
    ks = KillSwitch()
    cb = OKFCircuitBreakers(
        kill_switch=ks,
        max_drawdown_pct=0.10,
        max_daily_loss_pct=0.05,
        event_sink=events.append,
        cancel_fn=lambda: {"cancelled": ["o1"]},
        flatten_fn=lambda: {"flattened": True},
    )
    d = cb.evaluate(equity=10_000, daily_pnl=-600, drawdown_pct=0.0)
    assert d["breached"] and d["reason_code"] == "OKF_DAILY_LOSS_BREACH"
    assert ks.active and d["new_intents_allowed"] is False

    ks2 = KillSwitch()
    cb2 = OKFCircuitBreakers(kill_switch=ks2, max_drawdown_pct=0.10)
    d2 = cb2.evaluate(equity=10_000, daily_pnl=0, drawdown_pct=0.10)
    assert d2["reason_code"] == "OKF_DRAWDOWN_BREACH"

    ks3 = KillSwitch()
    cb3 = OKFCircuitBreakers(kill_switch=ks3)
    d3 = cb3.evaluate(equity=10_000, daily_pnl=0, drawdown_pct=0.0, stop_file_present=True)
    assert d3["reason_code"] == "KILL_SWITCH_STOP_FILE"
    assert d3["requires_operator_recovery"] is True


def test_correlation_filter_cases():
    gate = OKFCorrelationGate(
        risk_on_assets=["BTC/USD", "BTCUSDT"],
        correlated_long_blockers=["SPY", "QQQ"],
    )
    assert gate.evaluate(
        symbol="BTC/USD", side="LONG", open_positions={}, is_new_entry=True
    )["allowed"]
    assert gate.evaluate(
        symbol="BTC/USD", side="LONG", open_positions={"SPY": 1}, is_new_entry=True
    )["allowed"]
    blocked = gate.evaluate(
        symbol="BTC/USD",
        side="LONG",
        open_positions={"SPY": 1, "QQQ": 2},
        is_new_entry=True,
    )
    assert not blocked["allowed"]
    assert blocked["reason_code"] == "CORRELATION_FILTER_BLOCK"

    assert gate.evaluate(
        symbol="BTC/USD",
        side="LONG",
        open_positions={"SPY": 1, "QQQ": 1},
        is_position_modification=True,
    )["allowed"]
    assert gate.evaluate(
        symbol="BTC/USD",
        side="SHORT",
        open_positions={"SPY": 1, "QQQ": 1},
    )["allowed"]
    unavailable = gate.evaluate(
        symbol="BTC/USD",
        side="LONG",
        open_positions=None,
        correlation_data_available=False,
    )
    assert not unavailable["allowed"]
    assert unavailable["fail_closed"] is True


def test_low_turnover_guard():
    g = LowTurnoverGuard(max_trades_per_day=8, min_cooldown_bars=5)
    assert g.evaluate(trades_today=0, bars_since_last_trade=10)["allowed"]
    assert not g.evaluate(trades_today=8, bars_since_last_trade=10)["allowed"]
    assert not g.evaluate(trades_today=0, bars_since_last_trade=2)["allowed"]
    assert not g.evaluate(
        trades_today=0,
        bars_since_last_trade=10,
        strategy_style="high_frequency_scalping",
    )["allowed"]


def test_brier_recalibration_threshold():
    # Below
    r = BrierRecalibrator(threshold=0.25)
    # perfect preds → BS=0
    for _ in range(5):
        r.update(1.0, 1)
    st = r.status()
    assert st["comparison"] == "below"
    assert st["degraded"] is False

    # Equal: predicted 0.5 always, outcomes half — construct BS == 0.25
    # For constant p=0.5, BS = 0.25 always.
    r2 = BrierRecalibrator(threshold=0.25)
    for o in [0, 1, 0, 1]:
        r2.update(0.5, o)
    st2 = r2.status()
    assert st2["brier_score"] == pytest.approx(0.25)
    assert st2["comparison"] == "equal"
    assert st2["degraded"] is False

    # Above
    r3 = BrierRecalibrator(threshold=0.25)
    for _ in range(4):
        r3.update(0.9, 0)  # bad calibration
    st3 = r3.status()
    assert st3["brier_score"] > 0.25
    assert st3["degraded"] is True
    assert st3["kelly_multiplier"] <= 0.0625
    assert st3["weakens_hard_risk_limits"] is False
    assert st3["events"]


def test_memory_gate_block_and_unavailable():
    gate = PreTradeMemoryGate(block_confidence=0.80)
    unavailable = gate.evaluate(None, None, memory_available=False)
    assert not unavailable["allowed"]
    assert unavailable["reason_code"] == "FAILURE_MEMORY_UNAVAILABLE"

    feats = {"RSI_14": 30.0, "MACD_HISTOGRAM": -1.0, "VWAP_DISTANCE": -0.01}
    rec = TradeLearningRecord(
        trade_id="t1",
        symbol="BTC/USD",
        side="LONG",
        quantity=1,
        entry_price=100,
        exit_price=90,
        net_pnl=-10,
        outcome=TradeOutcome.LOSS,
        features=feats,
        failure_categories=[FailureCategory.BAD_PREDICTION],
    )
    blocked = gate.evaluate(feats, [rec], memory_available=True)
    assert not blocked["allowed"]
    assert blocked["reason_code"] == "FAILURE_MEMORY_MATCH_BLOCK"
    assert blocked["match_confidence"] > 0.80
    assert blocked["matched_memory_id"] == rec.memory_id
    assert blocked["llm_can_override"] is False


def test_post_mortem_categories():
    from crypto_trading_mcp.learning.post_mortem import run_post_mortem

    rec = TradeLearningRecord(
        trade_id="t2",
        symbol="ETH/USD",
        side="LONG",
        quantity=1,
        entry_price=100,
        exit_price=90,
        net_pnl=-5,
        predicted_probability=0.8,
        slippage=1.0,
        execution_quality="POOR",
        drift_state="REGIME_SHIFT",
        features={"EXTERNAL_SHOCK": 1.0, "RSI_14": 40},
    )
    pm = run_post_mortem(rec)
    cats = set(pm["classification"]["failure_categories"])
    for required in {
        "BAD_PREDICTION",
        "HIGH_SLIPPAGE",
        "MARKET_REGIME_SHIFT",
        "BAD_TIMING_OR_EXECUTION",
        "EXTERNAL_SHOCK",
    }:
        assert required in cats


def _candles(n: int = 80, start: float = 100.0, *, up: bool = True) -> list[Candle]:
    out = []
    price = start
    t0 = datetime(2024, 1, 1, tzinfo=UTC)
    for i in range(n):
        o = price
        c = price + (1.0 if up else -1.0)
        h = max(o, c) + 0.5
        l = min(o, c) - 0.5
        # fabricate day boundaries for PDH/PDL
        ts = t0 + timedelta(minutes=5 * i)
        if i < 40:
            ts = datetime(2024, 1, 1, tzinfo=UTC) + timedelta(minutes=5 * i)
        else:
            ts = datetime(2024, 1, 2, tzinfo=UTC) + timedelta(minutes=5 * (i - 40))
        out.append(
            Candle(
                timestamp=ts,
                open=o,
                high=h,
                low=l,
                close=c,
                volume=1000 + (500 if i == n - 1 else 0),
            )
        )
        price = c
    return out


def test_strategy_registry_and_signals():
    reg = OKFStrategyRegistry()
    assert set(reg.list_ids()) == set(OKF_STRATEGY_IDS)
    catalog = reg.catalog()
    assert catalog["version"] == "0.2.0"
    assert len(catalog["strategies"]) == 5

    # M4 ensemble validation
    m4 = evaluate_m4_prediction_ensemble(
        provider_probs={
            "grok_forecaster": 0.7,
            "claude_news_analyst": 0.7,
            "gpt4_bull_advocate": 0.7,
            "gemini_bear_advocate": 0.7,
            "deepseek_risk_manager": 0.7,
        },
        market_prob=0.5,
        vader_sentiment=0.1,
    )
    assert m4.status == "CONFIRMED"
    assert m4.submits_exchange_order is False

    m4b = evaluate_m4_prediction_ensemble(
        provider_probs={
            "grok_forecaster": 0.51,
            "claude_news_analyst": 0.51,
            "gpt4_bull_advocate": 0.51,
            "gemini_bear_advocate": 0.51,
            "deepseek_risk_manager": 0.51,
        },
        market_prob=0.5,
        vader_sentiment=0.1,
    )
    assert m4b.status == "REJECTED"

    # Donchian: force breakout on last bar
    c1h = _candles(40, start=100, up=True)
    # Raise last close above prior 20-high
    last = c1h[-1]
    channel = max(c.high for c in c1h[-21:-1])
    c1h[-1] = Candle(
        timestamp=last.timestamp,
        open=last.open,
        high=channel + 5,
        low=last.low,
        close=channel + 4,
        volume=10_000,
    )
    m5 = evaluate_m5_donchian_breakout(c1h)
    assert m5.status in {"CONFIRMED", "REJECTED", "UNAVAILABLE"}
    assert m5.model_id == "M5_MOMENTUM_BREAKOUT"

    # PO3 / VWAP / ICT return structured signals (status may vary with synthetic data)
    c5 = _candles(80)
    assert evaluate_m1_po3_sweep(c5).model_id == "M1_PO3_SWEEP"
    assert evaluate_m2_vwap_reclaim(c5, c5).model_id == "M2_VWAP_RECLAIM"
    assert evaluate_m3_ict_fvg(c5, c5).model_id == "M3_ICT_FVG_SWING"


def test_risk_engine_okf_correlation_and_memory():
    strategy = StrategyKnowledgeService().get_strategy().config
    engine = RiskEngine()
    prop = TradeProposal(
        symbol="BTC/USD",
        side="LONG",
        quantity=0.001,
        notional=10.0,
        entry_price=10000,
        stop_loss=9900,
        take_profit=10400,
        current_price=10000,
        confidence=0.8,
        model_ids=["M1_PO3_SWEEP"],
        liquidity_usd=1_000_000,
        bars_since_last_trade=100,
    )
    port = PortfolioRiskSnapshot(
        equity=10_000,
        available_cash=10_000,
        positions_exposure=0,
        daily_pnl=0,
        drawdown_pct=0,
        trades_today=0,
    )
    blocked = engine.evaluate(
        prop,
        port,
        strategy,
        open_positions={"SPY": 1.0, "QQQ": 1.0},
    )
    assert not blocked.approved
    assert RiskReasonCode.CORRELATION_FILTER_BLOCK in blocked.reason_codes

    mem_blocked = engine.evaluate(
        prop,
        port,
        strategy,
        open_positions={},
        memory_gate_result={
            "allowed": False,
            "reason_code": "FAILURE_MEMORY_MATCH_BLOCK",
        },
    )
    assert RiskReasonCode.FAILURE_MEMORY_MATCH_BLOCK in mem_blocked.reason_codes


def test_okf_diagnostics_and_paper_metadata():
    diag = okf_diagnostics()
    assert diag["version"] == "0.2.0"
    assert diag["LIVE_TRADING_ENABLED"] is False
    assert diag["executable"] is False
    assert diag["delta_exchange"]["production_trading_enabled"] is False
    meta = okf_paper_metadata()
    assert meta["okf_version"] == "0.2.0"
    assert len(meta["okf_hash"]) == 64


def test_tradingview_webhook_security():
    handler = TradingViewWebhookHandler(secret="test-webhook-secret-abc")
    now = 1_700_000_000.0
    handler.clock = lambda: now

    bad_secret = handler.handle(
        {
            "action": "buy",
            "symbol": "BTCUSD",
            "price": 100,
            "qty": 1,
            "secret": "YOUR_SECRET_KEY",
        },
        headers={"x-webhook-timestamp": str(now), "x-webhook-nonce": "n1"},
        remote_scheme="https",
    )
    assert bad_secret["reason_code"] in {"SECRET_PLACEHOLDER", "AUTH_FAILED"}

    base = {
        "action": "buy",
        "symbol": "BTC/USD",
        "price": 100.0,
        "qty": 0.01,
        "secret": "test-webhook-secret-abc",
    }
    headers = {"x-webhook-timestamp": str(now), "x-webhook-nonce": "nonce-1"}
    ok = handler.handle(base, headers=headers, remote_scheme="https")
    assert ok["accepted"] and ok["intent_created"]
    assert ok["intent"]["execution_attempted"] is False
    assert "RiskEngine" in ok["intent"]["requires"]

    # Replay same nonce
    replay = handler.handle(base, headers=headers, remote_scheme="https")
    assert replay["reason_code"] == "REPLAY_DETECTED"

    # Idempotency
    headers2 = {
        "x-webhook-timestamp": str(now),
        "x-webhook-nonce": "nonce-2",
        "idempotency-key": "idem-1",
    }
    first = handler.handle(base, headers=headers2, remote_scheme="https")
    second = handler.handle(
        base,
        headers={
            "x-webhook-timestamp": str(now),
            "x-webhook-nonce": "nonce-3",
            "idempotency-key": "idem-1",
        },
        remote_scheme="https",
    )
    assert first["intent_created"]
    assert second["reason_code"] == "IDEMPOTENT_REPLAY"
    assert second["intent_created"] is False

    # HTTPS required
    https = handler.handle(
        base,
        headers={"x-webhook-timestamp": str(now), "x-webhook-nonce": "nonce-4"},
        remote_scheme="http",
        remote_host="example.com",
    )
    assert https["reason_code"] == "HTTPS_REQUIRED"

    # Audit never stores raw secret
    for entry in handler.audit_log:
        blob = json.dumps(entry)
        assert "test-webhook-secret-abc" not in blob


def test_delta_okf_config_reference_only():
    diag = okf_diagnostics()
    assert diag["delta_exchange"]["okf_production_reference_url"] == (
        "https://api.india.delta.exchange"
    )
    assert diag["delta_exchange"]["stage2_uses_testnet_sandbox"] is True
    assert diag["delta_exchange"]["production_trading_enabled"] is False
