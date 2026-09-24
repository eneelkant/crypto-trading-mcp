"""Deterministic technical indicators. LLMs must not invent these values."""

from __future__ import annotations

from typing import Sequence


def sma(values: Sequence[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if period <= 0:
        raise ValueError("period must be positive")
    running = 0.0
    for i, value in enumerate(values):
        running += value
        if i >= period:
            running -= values[i - period]
        if i >= period - 1:
            out[i] = running / period
    return out


def ema(values: Sequence[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if period <= 0:
        raise ValueError("period must be positive")
    if not values:
        return out
    multiplier = 2 / (period + 1)
    seed = sma(values, period)
    start = period - 1
    if start >= len(values) or seed[start] is None:
        return out
    out[start] = seed[start]
    prev = seed[start]
    assert prev is not None
    for i in range(start + 1, len(values)):
        prev = (values[i] - prev) * multiplier + prev
        out[i] = prev
    return out


def rsi(values: Sequence[float], period: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) <= period:
        return out
    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        delta = values[i] - values[i - 1]
        if delta >= 0:
            gains += delta
        else:
            losses -= delta
    avg_gain = gains / period
    avg_loss = losses / period
    out[period] = 100.0 if avg_loss == 0 else 100 - (100 / (1 + avg_gain / avg_loss))
    for i in range(period + 1, len(values)):
        delta = values[i] - values[i - 1]
        gain = max(delta, 0.0)
        loss = max(-delta, 0.0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        out[i] = 100.0 if avg_loss == 0 else 100 - (100 / (1 + avg_gain / avg_loss))
    return out


def macd(
    values: Sequence[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> dict[str, list[float | None]]:
    fast_ema = ema(values, fast)
    slow_ema = ema(values, slow)
    line: list[float | None] = [None] * len(values)
    for i, (f, s) in enumerate(zip(fast_ema, slow_ema, strict=True)):
        if f is not None and s is not None:
            line[i] = f - s
    # Signal EMA over available MACD values (None-safe).
    compact = [v for v in line if v is not None]
    signal_compact = ema(compact, signal)
    signal_line: list[float | None] = [None] * len(values)
    hist: list[float | None] = [None] * len(values)
    compact_idx = 0
    for i, value in enumerate(line):
        if value is None:
            continue
        sig = signal_compact[compact_idx]
        signal_line[i] = sig
        if sig is not None:
            hist[i] = value - sig
        compact_idx += 1
    return {"macd": line, "signal": signal_line, "histogram": hist}


def atr(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> list[float | None]:
    n = len(closes)
    out: list[float | None] = [None] * n
    if n == 0:
        return out
    trs: list[float] = []
    for i in range(n):
        if i == 0:
            trs.append(highs[i] - lows[i])
        else:
            trs.append(
                max(
                    highs[i] - lows[i],
                    abs(highs[i] - closes[i - 1]),
                    abs(lows[i] - closes[i - 1]),
                )
            )
    running = 0.0
    for i, tr in enumerate(trs):
        running += tr
        if i >= period:
            running -= trs[i - period]
        if i >= period - 1:
            out[i] = running / period
    return out


def bollinger(
    values: Sequence[float],
    period: int = 20,
    num_std: float = 2.0,
) -> dict[str, list[float | None]]:
    mid = sma(values, period)
    upper: list[float | None] = [None] * len(values)
    lower: list[float | None] = [None] * len(values)
    width: list[float | None] = [None] * len(values)
    for i in range(len(values)):
        if mid[i] is None:
            continue
        window = values[i - period + 1 : i + 1]
        mean = mid[i]
        assert mean is not None
        var = sum((x - mean) ** 2 for x in window) / period
        std = var**0.5
        upper[i] = mean + num_std * std
        lower[i] = mean - num_std * std
        width[i] = (upper[i] - lower[i]) / mean if mean else None
    return {"middle": mid, "upper": upper, "lower": lower, "bandwidth": width}


def realized_volatility(values: Sequence[float], period: int = 20) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    returns: list[float] = [0.0]
    for i in range(1, len(values)):
        prev = values[i - 1]
        returns.append(0.0 if prev == 0 else (values[i] - prev) / prev)
    for i in range(period, len(values)):
        window = returns[i - period + 1 : i + 1]
        mean = sum(window) / period
        var = sum((r - mean) ** 2 for r in window) / period
        out[i] = var**0.5
    return out


def volume_metrics(volumes: Sequence[float], period: int = 20) -> dict[str, float | None]:
    if not volumes:
        return {"last": None, "sma": None, "relative": None}
    vol_sma = sma(volumes, period)
    last = volumes[-1]
    avg = vol_sma[-1]
    relative = None if avg in (None, 0) else last / avg
    return {"last": last, "sma": avg, "relative": relative}


def support_resistance(
    highs: Sequence[float],
    lows: Sequence[float],
    lookback: int = 20,
) -> dict[str, float | None]:
    if not highs or not lows:
        return {"support": None, "resistance": None}
    window_h = highs[-lookback:]
    window_l = lows[-lookback:]
    return {"support": min(window_l), "resistance": max(window_h)}


def last_number(series: Sequence[float | None]) -> float | None:
    for value in reversed(series):
        if value is not None:
            return float(value)
    return None


def adx(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> dict[str, list[float | None]]:
    n = len(closes)
    plus_di: list[float | None] = [None] * n
    minus_di: list[float | None] = [None] * n
    adx_vals: list[float | None] = [None] * n
    if n <= period:
        return {"adx": adx_vals, "plus_di": plus_di, "minus_di": minus_di}

    trs: list[float] = []
    plus_dm: list[float] = []
    minus_dm: list[float] = []
    for i in range(n):
        if i == 0:
            trs.append(highs[i] - lows[i])
            plus_dm.append(0.0)
            minus_dm.append(0.0)
            continue
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
        trs.append(
            max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
        )

    atr_s = sum(trs[1 : period + 1])
    plus_s = sum(plus_dm[1 : period + 1])
    minus_s = sum(minus_dm[1 : period + 1])
    dx_vals: list[float] = []
    for i in range(period, n):
        if i > period:
            atr_s = atr_s - (atr_s / period) + trs[i]
            plus_s = plus_s - (plus_s / period) + plus_dm[i]
            minus_s = minus_s - (minus_s / period) + minus_dm[i]
        if atr_s == 0:
            plus_di[i] = 0.0
            minus_di[i] = 0.0
            dx = 0.0
        else:
            pdi = 100 * plus_s / atr_s
            mdi = 100 * minus_s / atr_s
            plus_di[i] = pdi
            minus_di[i] = mdi
            denom = pdi + mdi
            dx = 0.0 if denom == 0 else abs(pdi - mdi) / denom * 100
        dx_vals.append(dx)
        if len(dx_vals) == period:
            adx_vals[i] = sum(dx_vals) / period
        elif len(dx_vals) > period:
            prev = adx_vals[i - 1]
            assert prev is not None
            adx_vals[i] = ((prev * (period - 1)) + dx) / period
    return {"adx": adx_vals, "plus_di": plus_di, "minus_di": minus_di}


def vwap(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    volumes: Sequence[float],
) -> list[float | None]:
    out: list[float | None] = [None] * len(closes)
    cum_pv = 0.0
    cum_vol = 0.0
    for i, (h, l, c, v) in enumerate(zip(highs, lows, closes, volumes, strict=True)):
        typical = (h + l + c) / 3.0
        cum_pv += typical * v
        cum_vol += v
        out[i] = None if cum_vol == 0 else cum_pv / cum_vol
    return out


def swing_points(
    highs: Sequence[float],
    lows: Sequence[float],
    left: int = 2,
    right: int = 2,
) -> dict[str, list[tuple[int, float]]]:
    swing_highs: list[tuple[int, float]] = []
    swing_lows: list[tuple[int, float]] = []
    n = len(highs)
    for i in range(left, n - right):
        window_h = highs[i - left : i + right + 1]
        window_l = lows[i - left : i + right + 1]
        if highs[i] == max(window_h):
            swing_highs.append((i, float(highs[i])))
        if lows[i] == min(window_l):
            swing_lows.append((i, float(lows[i])))
    return {"swing_highs": swing_highs, "swing_lows": swing_lows}


def structural_3bar_swing_stop(
    highs: Sequence[float],
    lows: Sequence[float],
    side: str,
) -> float | None:
    if len(highs) < 3 or len(lows) < 3:
        return None
    if side.upper() in {"LONG", "BUY"}:
        return min(lows[-3:])
    if side.upper() in {"SHORT", "SELL"}:
        return max(highs[-3:])
    return None


def fibonacci_levels(swing_low: float, swing_high: float) -> dict[str, float]:
    diff = swing_high - swing_low
    return {
        "0.0": swing_high,
        "0.236": swing_high - 0.236 * diff,
        "0.382": swing_high - 0.382 * diff,
        "0.5": swing_high - 0.5 * diff,
        "0.618": swing_high - 0.618 * diff,
        "0.786": swing_high - 0.786 * diff,
        "1.0": swing_low,
    }


def detect_fair_value_gaps(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
) -> list[dict[str, float | int | str]]:
    """3-candle FVG: bullish if low[i] > high[i-2]; bearish if high[i] < low[i-2]."""
    gaps: list[dict[str, float | int | str]] = []
    for i in range(2, len(closes)):
        if lows[i] > highs[i - 2]:
            gaps.append(
                {
                    "index": i,
                    "type": "bullish",
                    "top": float(lows[i]),
                    "bottom": float(highs[i - 2]),
                }
            )
        elif highs[i] < lows[i - 2]:
            gaps.append(
                {
                    "index": i,
                    "type": "bearish",
                    "top": float(lows[i - 2]),
                    "bottom": float(highs[i]),
                }
            )
    return gaps


def market_structure_break(
    closes: Sequence[float],
    swing_highs: list[tuple[int, float]],
    swing_lows: list[tuple[int, float]],
) -> dict[str, object]:
    if not closes:
        return {"status": "UNAVAILABLE", "direction": None}
    last = closes[-1]
    last_sh = swing_highs[-1][1] if swing_highs else None
    last_sl = swing_lows[-1][1] if swing_lows else None
    if last_sh is not None and last > last_sh:
        return {"status": "CALCULATED", "direction": "bullish_msb", "level": last_sh}
    if last_sl is not None and last < last_sl:
        return {"status": "CALCULATED", "direction": "bearish_msb", "level": last_sl}
    return {"status": "CALCULATED", "direction": "none", "level": None}


def compute_indicator_bundle(
    opens: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    volumes: Sequence[float],
) -> dict[str, object]:
    macd_bundle = macd(closes)
    bb = bollinger(closes)
    levels = support_resistance(highs, lows)
    vol = volume_metrics(volumes)
    adx_bundle = adx(highs, lows, closes, 11)
    return {
        "sma_20": last_number(sma(closes, 20)),
        "sma_50": last_number(sma(closes, 50)),
        "ema_9": last_number(ema(closes, 9)),
        "ema_12": last_number(ema(closes, 12)),
        "ema_21": last_number(ema(closes, 21)),
        "ema_26": last_number(ema(closes, 26)),
        "ema_50": last_number(ema(closes, 50)),
        "ema_200": last_number(ema(closes, 200)),
        "rsi_14": last_number(rsi(closes, 14)),
        "macd": last_number(macd_bundle["macd"]),
        "macd_signal": last_number(macd_bundle["signal"]),
        "macd_histogram": last_number(macd_bundle["histogram"]),
        "atr_14": last_number(atr(highs, lows, closes, 14)),
        "adx_11": last_number(adx_bundle["adx"]),
        "plus_di_11": last_number(adx_bundle["plus_di"]),
        "minus_di_11": last_number(adx_bundle["minus_di"]),
        "vwap": last_number(vwap(highs, lows, closes, volumes)),
        "bollinger_middle": last_number(bb["middle"]),
        "bollinger_upper": last_number(bb["upper"]),
        "bollinger_lower": last_number(bb["lower"]),
        "bollinger_bandwidth": last_number(bb["bandwidth"]),
        "volatility_20": last_number(realized_volatility(closes, 20)),
        "volume_last": vol["last"],
        "volume_sma_20": vol["sma"],
        "volume_relative": vol["relative"],
        "support": levels["support"],
        "resistance": levels["resistance"],
        "last_close": closes[-1] if closes else None,
        "last_open": opens[-1] if opens else None,
    }
