from __future__ import annotations

from typing import Sequence

from crypto_trading_mcp.backtest.models import NormalizedCandle
from crypto_trading_mcp.learning.models import MarketRegime
from crypto_trading_mcp.market.indicators import adx, atr, ema, realized_volatility


def detect_regime(candles: Sequence[NormalizedCandle]) -> MarketRegime:
    """Deterministic regime detection from closed candles only."""
    if len(candles) < 30:
        return MarketRegime.UNKNOWN
    closes = [c.close for c in candles]
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    volumes = [c.volume for c in candles]
    atrs = atr(highs, lows, closes, 14)
    adx_series = adx(highs, lows, closes, 14)["adx"]
    emas_fast = ema(closes, 20)
    emas_slow = ema(closes, 50)
    vols = realized_volatility(closes, 20)
    atr_v = atrs[-1]
    adx_v = adx_series[-1]
    ef = emas_fast[-1]
    es = emas_slow[-1]
    vol = vols[-1]
    last = candles[-1]
    avg_vol = sum(volumes[-20:]) / 20.0
    prior_high = max(c.high for c in candles[-21:-1])
    prior_low = min(c.low for c in candles[-21:-1])

    if atr_v is not None and closes[-1] > 0:
        atr_pct = atr_v / closes[-1]
    else:
        atr_pct = 0.0
    if vol is not None and vol > 0.03:
        return MarketRegime.HIGH_VOLATILITY
    if vol is not None and vol < 0.005 and (adx_v is None or adx_v < 18):
        return MarketRegime.LOW_VOLATILITY
    if last.close > prior_high and last.volume >= avg_vol * 1.4:
        return MarketRegime.BREAKOUT
    if last.close < prior_low and last.volume >= avg_vol * 1.4:
        return MarketRegime.BREAKOUT
    if adx_v is not None and adx_v >= 25 and ef is not None and es is not None:
        if ef > es and closes[-1] > ef:
            return MarketRegime.TRENDING_UP
        if ef < es and closes[-1] < ef:
            return MarketRegime.TRENDING_DOWN
    if adx_v is not None and adx_v < 18:
        # ranging vs mean-reverting heuristic
        if atr_pct < 0.01:
            return MarketRegime.RANGING
        return MarketRegime.MEAN_REVERTING
    return MarketRegime.UNKNOWN
