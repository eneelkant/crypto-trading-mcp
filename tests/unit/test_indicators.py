from __future__ import annotations

from crypto_trading_mcp.market.indicators import (
    atr,
    bollinger,
    ema,
    macd,
    rsi,
    sma,
    support_resistance,
    volume_metrics,
)


def test_sma_ema_known_values():
    values = [1, 2, 3, 4, 5]
    assert sma(values, 3) == [None, None, 2.0, 3.0, 4.0]
    ema_vals = ema(values, 3)
    assert ema_vals[2] == 2.0
    assert ema_vals[-1] is not None


def test_rsi_bounds():
    up = [float(i) for i in range(1, 40)]
    values = rsi(up, 14)
    assert values[-1] is not None
    assert 50 < values[-1] <= 100


def test_macd_and_bollinger_and_atr():
    closes = [100 + i * 0.5 for i in range(60)]
    highs = [c + 1 for c in closes]
    lows = [c - 1 for c in closes]
    bundle = macd(closes)
    assert bundle["macd"][-1] is not None
    bb = bollinger(closes, 20)
    assert bb["upper"][-1] > bb["middle"][-1] > bb["lower"][-1]
    assert atr(highs, lows, closes, 14)[-1] is not None


def test_volume_and_levels():
    volumes = [10.0] * 10 + [50.0]
    metrics = volume_metrics(volumes, 10)
    assert metrics["relative"] is not None and metrics["relative"] > 1
    levels = support_resistance([11, 12, 13], [9, 8, 10], lookback=3)
    assert levels["support"] == 8
    assert levels["resistance"] == 13
