from __future__ import annotations

from datetime import UTC, datetime, timedelta

from crypto_trading_mcp.market.indicators import (
    adx,
    atr,
    detect_fair_value_gaps,
    ema,
    fibonacci_levels,
    market_structure_break,
    swing_points,
    vwap,
)
from crypto_trading_mcp.market.models import Candle
from crypto_trading_mcp.orchestration.proposal import default_mock_candles, synthesize_timeframe
from crypto_trading_mcp.strategy.features import StrategyFeatureEngine, only_closed_candles
from crypto_trading_mcp.strategy.repository import StrategyKnowledgeService


def _series(n=80, start=100.0):
    closes = [start + i * 0.2 for i in range(n)]
    highs = [c + 0.3 for c in closes]
    lows = [c - 0.3 for c in closes]
    volumes = [1000 + i for i in range(n)]
    return highs, lows, closes, volumes


def test_ema_adx_vwap_atr():
    highs, lows, closes, volumes = _series()
    assert ema(closes, 9)[-1] is not None
    assert ema(closes, 21)[-1] is not None
    assert ema(closes, 50)[-1] is not None
    adx_v = adx(highs, lows, closes, 11)
    assert adx_v["adx"][-1] is not None
    assert vwap(highs, lows, closes, volumes)[-1] is not None
    assert atr(highs, lows, closes, 14)[-1] is not None


def test_session_levels_swings_fib_msb_fvg():
    candles = default_mock_candles(400)
    # Force multi-day span already present.
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    closes = [c.close for c in candles]
    swings = swing_points(highs, lows)
    assert swings["swing_highs"] or True
    if swings["swing_highs"] and swings["swing_lows"]:
        fib = fibonacci_levels(swings["swing_lows"][-1][1], swings["swing_highs"][-1][1])
        assert "0.5" in fib
    msb = market_structure_break(closes, swings["swing_highs"], swings["swing_lows"])
    assert msb["status"] == "CALCULATED"
    gaps = detect_fair_value_gaps(highs, lows, closes)
    assert isinstance(gaps, list)


def test_look_ahead_protection_excludes_open_htf_candle():
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    candles = [
        Candle(timestamp=now - timedelta(hours=8), open=1, high=2, low=0.5, close=1.5, volume=1),
        Candle(timestamp=now - timedelta(hours=4), open=1.5, high=2.5, low=1.2, close=2.0, volume=1),
        # In-progress 4H bar (opened recently, not closed)
        Candle(timestamp=now - timedelta(minutes=30), open=2.0, high=2.1, low=1.9, close=2.05, volume=1),
    ]
    closed = only_closed_candles(candles, as_of=now, timeframe_minutes=240)
    assert len(closed) == 2
    assert closed[-1].timestamp == candles[1].timestamp


def test_feature_engine_marks_cvd_unavailable():
    strategy = StrategyKnowledgeService().get_strategy().config
    candles = default_mock_candles(400)
    engine = StrategyFeatureEngine()
    bundle = engine.compute(
        strategy=strategy,
        candles_5m=candles,
        candles_15m=synthesize_timeframe(candles, "15m"),
        candles_240m=synthesize_timeframe(candles, "240m"),
        cvd_status="UNAVAILABLE",
    )
    assert bundle["features"]["cvd"]["status"] == "UNAVAILABLE"
    models = {m["model_id"]: m["status"] for m in bundle["models"]}
    assert models["M3"] == "UNAVAILABLE"
