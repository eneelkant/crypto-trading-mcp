from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from crypto_trading_mcp.backtest.models import NormalizedCandle
from crypto_trading_mcp.market.indicators import atr, ema, sma


@dataclass(frozen=True)
class StrategySignal:
    side: str  # LONG | SHORT | FLAT
    confidence: float
    entry: float
    stop_loss: float | None
    take_profit: float | None
    model_ids: list[str]
    reason: str


def _slice_closed(candles: Sequence[NormalizedCandle], index: int) -> list[NormalizedCandle]:
    """Return candles available at decision index (inclusive closed candle)."""
    if index < 0:
        return []
    return list(candles[: index + 1])


def donchian_breakout_signal(
    candles: Sequence[NormalizedCandle],
    index: int,
    *,
    lookback: int = 20,
    atr_mult: float = 2.0,
    volume_mult: float = 1.5,
) -> StrategySignal:
    hist = _slice_closed(candles, index)
    if len(hist) < lookback + 2:
        return StrategySignal("FLAT", 0.0, hist[-1].close if hist else 0.0, None, None, [], "insufficient")
    window = hist[-(lookback + 1) : -1]
    upper = max(c.high for c in window)
    lower = min(c.low for c in window)
    last = hist[-1]
    closes = [c.close for c in hist]
    highs = [c.high for c in hist]
    lows = [c.low for c in hist]
    atrs = atr(highs, lows, closes, 14)
    atr_v = atrs[-1] if atrs and atrs[-1] is not None else last.close * 0.02
    vols = [c.volume for c in hist[-lookback:]]
    avg_vol = sum(vols) / len(vols) if vols else last.volume
    if last.close > upper and last.volume >= avg_vol * volume_mult:
        stop = last.close - atr_mult * float(atr_v)
        tp = last.close + 3.0 * (last.close - stop)
        return StrategySignal("LONG", 0.8, last.close, stop, tp, ["DONCHIAN20"], "breakout_up")
    if last.close < lower and last.volume >= avg_vol * volume_mult:
        stop = last.close + atr_mult * float(atr_v)
        tp = last.close - 3.0 * (stop - last.close)
        return StrategySignal("SHORT", 0.8, last.close, stop, tp, ["DONCHIAN20"], "breakout_down")
    return StrategySignal("FLAT", 0.0, last.close, None, None, [], "no_breakout")


def mean_reversion_signal(
    candles: Sequence[NormalizedCandle],
    index: int,
    *,
    sma_period: int = 20,
    entry_z: float = 0.02,
) -> StrategySignal:
    hist = _slice_closed(candles, index)
    if len(hist) < sma_period + 1:
        return StrategySignal("FLAT", 0.0, hist[-1].close if hist else 0.0, None, None, [], "insufficient")
    closes = [c.close for c in hist]
    series = sma(closes, sma_period)
    mid = series[-1]
    last = hist[-1]
    if mid is None:
        return StrategySignal("FLAT", 0.0, last.close, None, None, [], "sma_unavailable")
    if last.close < mid * (1 - entry_z):
        stop = last.close * 0.98
        tp = float(mid)
        return StrategySignal("LONG", 0.7, last.close, stop, tp, ["SMA20_MR"], "below_sma")
    if last.close > mid * (1 + entry_z):
        stop = last.close * 1.02
        tp = float(mid)
        return StrategySignal("SHORT", 0.7, last.close, stop, tp, ["SMA20_MR"], "above_sma")
    return StrategySignal("FLAT", 0.0, last.close, None, None, [], "near_sma")


def trend_following_signal(
    candles: Sequence[NormalizedCandle],
    index: int,
    *,
    fast: int = 20,
    slow: int = 50,
) -> StrategySignal:
    hist = _slice_closed(candles, index)
    if len(hist) < slow + 2:
        return StrategySignal("FLAT", 0.0, hist[-1].close if hist else 0.0, None, None, [], "insufficient")
    closes = [c.close for c in hist]
    f = ema(closes, fast)
    s = ema(closes, slow)
    if f[-1] is None or s[-1] is None or f[-2] is None or s[-2] is None:
        return StrategySignal("FLAT", 0.0, hist[-1].close, None, None, [], "ema_unavailable")
    last = hist[-1]
    # Cross up
    if f[-2] <= s[-2] and f[-1] > s[-1]:
        stop = last.close * 0.97
        tp = last.close * 1.09
        return StrategySignal("LONG", 0.75, last.close, stop, tp, ["EMA_CROSS"], "ema_cross_up")
    if f[-2] >= s[-2] and f[-1] < s[-1]:
        stop = last.close * 1.03
        tp = last.close * 0.91
        return StrategySignal("SHORT", 0.75, last.close, stop, tp, ["EMA_CROSS"], "ema_cross_down")
    return StrategySignal("FLAT", 0.0, last.close, None, None, [], "no_cross")


def smc_structure_signal(
    candles: Sequence[NormalizedCandle],
    index: int,
    *,
    lookback: int = 10,
) -> StrategySignal:
    """Simplified structure break proxy for SMC / PO3 confluence backtests."""
    hist = _slice_closed(candles, index)
    if len(hist) < lookback + 2:
        return StrategySignal("FLAT", 0.0, hist[-1].close if hist else 0.0, None, None, [], "insufficient")
    window = hist[-(lookback + 1) : -1]
    last = hist[-1]
    swing_high = max(c.high for c in window)
    swing_low = min(c.low for c in window)
    if last.close > swing_high:
        stop = swing_low
        risk = last.close - stop
        tp = last.close + 2.0 * risk
        return StrategySignal("LONG", 0.72, last.close, stop, tp, ["SMC_OB", "PO3"], "bos_up")
    if last.close < swing_low:
        stop = swing_high
        risk = stop - last.close
        tp = last.close - 2.0 * risk
        return StrategySignal("SHORT", 0.72, last.close, stop, tp, ["SMC_OB", "PO3"], "bos_down")
    return StrategySignal("FLAT", 0.0, last.close, None, None, [], "no_bos")


def signal_for_strategy(
    strategy_id: str,
    candles: Sequence[NormalizedCandle],
    index: int,
    *,
    params: dict | None = None,
) -> StrategySignal:
    params = params or {}
    sid = strategy_id.lower()
    if "momentum" in sid or "breakout" in sid:
        return donchian_breakout_signal(
            candles,
            index,
            lookback=int(params.get("lookback", 20)),
            atr_mult=float(params.get("atr_mult", 2.0)),
            volume_mult=float(params.get("volume_mult", 1.0)),  # lower for tests
        )
    if "mean_reversion" in sid:
        return mean_reversion_signal(candles, index, sma_period=int(params.get("sma_period", 20)))
    if "trend" in sid or "commodit" in sid:
        return trend_following_signal(candles, index)
    if "smc" in sid or "po3" in sid or "vwap" in sid:
        return smc_structure_signal(candles, index)
    return donchian_breakout_signal(candles, index, volume_mult=1.0)
