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
    return {
        "sma_20": last_number(sma(closes, 20)),
        "sma_50": last_number(sma(closes, 50)),
        "ema_12": last_number(ema(closes, 12)),
        "ema_26": last_number(ema(closes, 26)),
        "rsi_14": last_number(rsi(closes, 14)),
        "macd": last_number(macd_bundle["macd"]),
        "macd_signal": last_number(macd_bundle["signal"]),
        "macd_histogram": last_number(macd_bundle["histogram"]),
        "atr_14": last_number(atr(highs, lows, closes, 14)),
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
