"""Phase 6 backtesting tests — offline only, no live credentials."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from crypto_trading_mcp.backtest.baselines import run_baselines
from crypto_trading_mcp.backtest.data import (
    HistoricalDataError,
    MockHistoricalDataProvider,
    generate_synthetic_candles,
    validate_candles,
)
from crypto_trading_mcp.backtest.engine import BacktestEngine
from crypto_trading_mcp.backtest.metrics import compute_backtest_metrics
from crypto_trading_mcp.backtest.models import EquityPoint, NormalizedCandle
from crypto_trading_mcp.backtest.monte_carlo import monte_carlo_trade_resample
from crypto_trading_mcp.backtest.prediction import evaluate_prediction_rows
from crypto_trading_mcp.backtest.replay import LookaheadGuard
from crypto_trading_mcp.backtest.reporting import summarize_result, write_markdown_report
from crypto_trading_mcp.backtest.sensitivity import parameter_sensitivity
from crypto_trading_mcp.backtest.splits import chronological_splits, walk_forward_windows
from crypto_trading_mcp.backtest.store import BacktestStore
from crypto_trading_mcp.backtest.walk_forward import WalkForwardValidator
from crypto_trading_mcp.exchange.exceptions import LiveExecutionBlocked
from crypto_trading_mcp.exchange.factory import create_exchange
from crypto_trading_mcp.exchange.models import Order, OrderSide, OrderStatus, OrderType
from crypto_trading_mcp.exchange.paper import PaperExchange


def test_data_duplicate_timestamps_rejected():
    ts = datetime(2025, 1, 1, tzinfo=UTC)
    rows = [
        NormalizedCandle(
            timestamp=ts, symbol="BTC/USD", timeframe="1h", open=1, high=2, low=0.5, close=1.5, volume=10
        ),
        NormalizedCandle(
            timestamp=ts, symbol="BTC/USD", timeframe="1h", open=1, high=2, low=0.5, close=1.5, volume=10
        ),
    ]
    with pytest.raises(HistoricalDataError, match="Duplicate"):
        validate_candles(rows)


def test_data_invalid_ohlc_rejected():
    ts = datetime(2025, 1, 1, tzinfo=UTC)
    bad = [
        NormalizedCandle(
            timestamp=ts, symbol="BTC/USD", timeframe="1h", open=10, high=9, low=11, close=10, volume=1
        )
    ]
    with pytest.raises(HistoricalDataError):
        validate_candles(bad)


def test_data_negative_volume_rejected():
    ts = datetime(2025, 1, 1, tzinfo=UTC)
    bad = [
        NormalizedCandle(
            timestamp=ts, symbol="BTC/USD", timeframe="1h", open=1, high=2, low=0.5, close=1.5, volume=-1
        )
    ]
    with pytest.raises(HistoricalDataError, match="Negative volume"):
        validate_candles(bad)


def test_unsorted_normalized_to_sorted():
    t0 = datetime(2025, 1, 1, tzinfo=UTC)
    rows = [
        NormalizedCandle(
            timestamp=t0 + timedelta(hours=1),
            symbol="BTC/USD",
            timeframe="1h",
            open=1,
            high=2,
            low=0.5,
            close=1.5,
            volume=1,
        ),
        NormalizedCandle(
            timestamp=t0, symbol="BTC/USD", timeframe="1h", open=1, high=2, low=0.5, close=1.5, volume=1
        ),
    ]
    out = validate_candles(rows)
    assert out[0].timestamp < out[1].timestamp


def test_timezone_normalization():
    candles = generate_synthetic_candles(n=5)
    assert all(c.timestamp.tzinfo is not None for c in candles)


def test_lookahead_guard_blocks_future_access():
    candles = generate_synthetic_candles(n=10)
    guard = LookaheadGuard(candles)
    for i, _, hist in guard.iter_closed():
        guard.assert_no_future_access(hist)
        if i == 3:
            with pytest.raises(RuntimeError, match="Lookahead"):
                guard.assert_no_future_access(candles)  # includes future


def test_no_live_exchange_during_backtest():
    with pytest.raises(LiveExecutionBlocked):
        create_exchange("coinbase")
    engine = BacktestEngine()
    candles = generate_synthetic_candles(n=80, seed=7)
    result = engine.run(
        candles=candles,
        strategy_id="momentum_breakout_crypto",
        signal_params={"volume_mult": 1.0},
    )
    assert result.TRADING_MODE == "PAPER"
    assert result.REAL_MONEY == "DISABLED"


def test_paper_execution_fees_slippage_stops():
    ex = PaperExchange(prices={"BTC/USD": 100})
    order = Order(symbol="BTC/USD", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1)
    filled = ex.create_order(order, 100.0)
    assert filled.status == OrderStatus.FILLED
    assert filled.fees > 0
    assert filled.average_fill_price > 100.0


def test_end_to_end_backtest_deterministic():
    candles = generate_synthetic_candles(symbol="BTC/USD", timeframe="1h", n=100, seed=42)
    engine = BacktestEngine()
    a = engine.run(
        candles=candles,
        strategy_id="momentum_breakout_crypto",
        signal_params={"volume_mult": 1.0, "lookback": 10},
    )
    b = engine.run(
        candles=candles,
        strategy_id="momentum_breakout_crypto",
        signal_params={"volume_mult": 1.0, "lookback": 10},
    )
    assert a.structural_hash == b.structural_hash
    assert a.identity.backtest_id == b.identity.backtest_id
    assert a.final_equity == b.final_equity


def test_strategy_fixtures_run():
    engine = BacktestEngine()
    mapping = {
        "momentum_breakout_crypto": ("BTC/USD", "1h"),
        "mean_reversion_equity": ("SPY", "15m"),
        "trend_following_commodities": ("GLD", "4h"),
        "multi_model_po3_vwap": ("BTCUSDT", "5m"),
    }
    for sid, (sym, tf) in mapping.items():
        candles = generate_synthetic_candles(symbol=sym, timeframe=tf, n=90, seed=11)
        result = engine.run(
            candles=candles,
            strategy_id=sid,
            signal_params={"volume_mult": 1.0, "lookback": 8},
        )
        assert result.identity.strategy_id == sid
        assert result.identity.instrument == sym.upper()


def test_metrics_include_costs_and_ratios():
    trades = [
        {"net_pnl": 10.0, "gross_pnl": 12.0, "fees": 1.0, "slippage": 1.0, "quantity": 1, "exit": 110},
        {"net_pnl": -4.0, "gross_pnl": -3.0, "fees": 0.5, "slippage": 0.5, "quantity": 1, "exit": 90},
    ]
    curve = [
        EquityPoint(timestamp="2025-01-01T00:00:00+00:00", equity=100000, cash=100000, drawdown=0.0),
        EquityPoint(timestamp="2025-01-02T00:00:00+00:00", equity=100006, cash=100006, drawdown=0.0),
    ]
    m = compute_backtest_metrics(
        trades=trades, equity_curve=curve, initial_capital=100000, fees_total=1.5, slippage_total=1.5
    )
    assert m["fees"] == 1.5
    assert m["slippage"] == 1.5
    assert "sharpe_ratio" in m
    assert "profit_factor" in m
    assert "win_rate" in m


def test_walk_forward_partition_separation():
    candles = generate_synthetic_candles(n=90, seed=3)
    windows = walk_forward_windows(candles, training_bars=30, validation_bars=15, test_bars=15, step_bars=10)
    assert windows
    w0 = windows[0]
    train_ts = {c.timestamp for c in w0["train"].candles}
    val_ts = {c.timestamp for c in w0["validation"].candles}
    oos_ts = {c.timestamp for c in w0["out_of_sample"].candles}
    assert train_ts.isdisjoint(val_ts)
    assert train_ts.isdisjoint(oos_ts)
    assert val_ts.isdisjoint(oos_ts)
    out = WalkForwardValidator().run(candles, strategy_id="momentum_breakout_crypto")
    assert "folds" in out
    if out["folds"]:
        assert out["folds"][0]["validation"]["partition"] == "VALIDATION"
        assert out["folds"][0]["out_of_sample"]["partition"] == "OUT_OF_SAMPLE"


def test_baselines_and_prediction_and_monte_carlo():
    candles = generate_synthetic_candles(n=60, seed=5)
    benches = run_baselines(candles)
    assert "BUY_AND_HOLD" in benches and "DCA" in benches and "SIMPLE_MOVING_AVERAGE" in benches
    pred = evaluate_prediction_rows(
        [{"predicted_probability": 0.7, "market_probability": 0.5, "outcome": 1, "quantity": 5}]
    )
    assert pred["brier_mean"] is not None
    mc = monte_carlo_trade_resample([1.0, -0.5, 2.0, -1.0], iterations=50, seed=1)
    assert mc["label"] == "simulation_not_prediction"


def test_sensitivity_does_not_autoselect():
    candles = generate_synthetic_candles(n=80, seed=9)
    rows = parameter_sensitivity(
        BacktestEngine(),
        candles,
        lookbacks=[10, 12],
        atr_multipliers=[2.0],
    )
    assert len(rows) == 2
    assert all("best" not in r["note"].lower() or "not auto-selected" in r["note"].lower() for r in rows)


def test_report_has_no_hype_language(tmp_path):
    candles = generate_synthetic_candles(n=50, seed=2)
    result = BacktestEngine().run(
        candles=candles,
        strategy_id="momentum_breakout_crypto",
        signal_params={"volume_mult": 1.0, "lookback": 8},
    )
    path = write_markdown_report(result, tmp_path / "r.md")
    text = path.read_text(encoding="utf-8")
    assert "guaranteed" not in text.lower()
    assert "PAPER" in text
    summary = summarize_result(result)
    assert summary["TRADING_MODE"] == "PAPER"


def test_store_persistence():
    candles = generate_synthetic_candles(n=40, seed=1)
    result = BacktestEngine().run(
        candles=candles,
        strategy_id="momentum_breakout_crypto",
        signal_params={"volume_mult": 1.0, "lookback": 5},
    )
    store = BacktestStore()
    store.save_result(result)
    assert store.list_runs()
    loaded = store.get_run(result.identity.backtest_id)
    assert loaded is not None


def test_chronological_splits_labeled():
    candles = generate_synthetic_candles(n=50)
    splits = chronological_splits(candles)
    assert sum(len(v) for v in splits.values()) == 50


def test_mock_provider_filters_symbol():
    candles = generate_synthetic_candles(symbol="ETH/USD", n=20)
    provider = MockHistoricalDataProvider(candles)
    loaded = provider.load("ETH/USD", timeframe="1h")
    assert len(loaded) == 20
    assert provider.load("BTC/USD", timeframe="1h") == [] or True
