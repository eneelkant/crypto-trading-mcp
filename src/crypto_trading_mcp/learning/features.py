from __future__ import annotations

from typing import Any, Sequence

from crypto_trading_mcp.backtest.models import NormalizedCandle
from crypto_trading_mcp.learning.regime import detect_regime
from crypto_trading_mcp.market.indicators import (
    adx,
    atr,
    bollinger,
    ema,
    macd,
    rsi,
    vwap,
)


FEATURE_NAMES = [
    "RSI_14",
    "MACD_HISTOGRAM",
    "VWAP_DISTANCE",
    "BOLLINGER_BAND_WIDTH",
    "VOLUME_BREAKOUT_MULT",
    "ATR",
    "ADX",
    "EMA_DISTANCE",
    "RETURNS",
    "VOLATILITY",
]


def extract_features(candles: Sequence[NormalizedCandle]) -> dict[str, float | None]:
    """Deterministic features from closed candles (lookahead-safe caller responsibility)."""
    if len(candles) < 30:
        return {name: None for name in FEATURE_NAMES} | {"MARKET_REGIME_CODE": None}
    closes = [c.close for c in candles]
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    volumes = [c.volume for c in candles]
    opens = [c.open for c in candles]
    rsi_s = rsi(closes, 14)
    macd_s = macd(closes)
    atr_s = atr(highs, lows, closes, 14)
    adx_s = adx(highs, lows, closes, 14)["adx"]
    ema_f = ema(closes, 20)
    ema_s = ema(closes, 50)
    bb = bollinger(closes, 20)
    # simple cumulative VWAP approximation on closed set
    try:
        vwap_s = vwap(highs, lows, closes, volumes)
        vwap_last = vwap_s[-1] if vwap_s else None
    except TypeError:
        # some signatures differ; fall back
        typical = [(h + l + c) / 3 for h, l, c in zip(highs, lows, closes)]
        cum_pv = 0.0
        cum_v = 0.0
        vwap_last = None
        for t, v in zip(typical, volumes):
            cum_pv += t * v
            cum_v += v
            vwap_last = (cum_pv / cum_v) if cum_v else None
    avg_vol = sum(volumes[-20:]) / 20.0
    last = candles[-1]
    ret = None if closes[-2] == 0 else (closes[-1] - closes[-2]) / closes[-2]
    # realized vol approx
    rets = []
    for i in range(1, min(21, len(closes))):
        prev = closes[-i - 1]
        if prev:
            rets.append((closes[-i] - prev) / prev)
    vol = (sum(r * r for r in rets) / len(rets)) ** 0.5 if rets else None
    hist = macd_s.get("histogram") or []
    bw = bb.get("bandwidth") or []
    features: dict[str, float | None] = {
        "RSI_14": rsi_s[-1],
        "MACD_HISTOGRAM": hist[-1] if hist else None,
        "VWAP_DISTANCE": None if vwap_last in (None, 0) else (last.close - vwap_last) / vwap_last,
        "BOLLINGER_BAND_WIDTH": bw[-1] if bw else None,
        "VOLUME_BREAKOUT_MULT": None if avg_vol == 0 else last.volume / avg_vol,
        "ATR": atr_s[-1],
        "ADX": adx_s[-1],
        "EMA_DISTANCE": None
        if ema_f[-1] is None or ema_s[-1] in (None, 0)
        else (ema_f[-1] - ema_s[-1]) / ema_s[-1],
        "RETURNS": ret,
        "VOLATILITY": vol,
    }
    regime = detect_regime(candles)
    code = {
        "TRENDING_UP": 1.0,
        "TRENDING_DOWN": -1.0,
        "RANGING": 0.0,
        "HIGH_VOLATILITY": 2.0,
        "LOW_VOLATILITY": -2.0,
        "BREAKOUT": 3.0,
        "MEAN_REVERTING": 0.5,
        "UNKNOWN": None,
    }.get(regime.value)
    features["MARKET_REGIME_CODE"] = code
    features["MARKET_REGIME"] = regime.value  # type: ignore[assignment]
    return features


def feature_vector(features: dict[str, Any]) -> list[float]:
    out: list[float] = []
    for name in FEATURE_NAMES + ["MARKET_REGIME_CODE"]:
        val = features.get(name)
        out.append(0.0 if val is None else float(val))
    return out
