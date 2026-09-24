from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Sequence

from crypto_trading_mcp.market.indicators import (
    adx,
    atr,
    detect_fair_value_gaps,
    ema,
    fibonacci_levels,
    last_number,
    market_structure_break,
    structural_3bar_swing_stop,
    swing_points,
    vwap,
    volume_metrics,
)
from crypto_trading_mcp.market.models import Candle
from crypto_trading_mcp.strategy.schema import StrategyConfig


class FeatureStatus(StrEnum):
    CALCULATED = "CALCULATED"
    UNAVAILABLE = "UNAVAILABLE"
    INVALID = "INVALID"
    STALE = "STALE"


@dataclass
class FeatureValue:
    name: str
    status: FeatureStatus
    value: Any = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "value": self.value,
            "reason": self.reason,
        }


@dataclass
class ModelEvaluation:
    model_id: str
    status: str  # CONFIRMED | REJECTED | UNAVAILABLE
    reasons: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "status": self.status,
            "reasons": self.reasons,
            "evidence": self.evidence,
        }


def only_closed_candles(
    candles: Sequence[Candle],
    *,
    as_of: datetime,
    timeframe_minutes: int,
) -> list[Candle]:
    """Exclude in-progress HTF candle to prevent look-ahead leakage."""
    closed: list[Candle] = []
    delta_seconds = timeframe_minutes * 60
    for candle in candles:
        ts = candle.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        close_time = ts.timestamp() + delta_seconds
        if close_time <= as_of.timestamp():
            closed.append(candle)
    return closed


def timeframe_to_minutes(tf: str) -> int:
    tf = tf.strip().lower()
    if tf.endswith("m"):
        return int(tf[:-1])
    if tf.endswith("h"):
        return int(tf[:-1]) * 60
    if tf.endswith("d"):
        return int(tf[:-1]) * 1440
    raise ValueError(f"Unsupported timeframe: {tf}")


def session_levels(candles: Sequence[Candle]) -> dict[str, FeatureValue]:
    if not candles:
        unavailable = FeatureStatus.UNAVAILABLE
        return {
            "PDH": FeatureValue("PDH", unavailable, reason="No candles"),
            "PDL": FeatureValue("PDL", unavailable, reason="No candles"),
            "PMH": FeatureValue("PMH", unavailable, reason="No candles"),
            "PML": FeatureValue("PML", unavailable, reason="No candles"),
        }
    by_day: dict[str, list[Candle]] = {}
    by_month: dict[str, list[Candle]] = {}
    for c in candles:
        day = c.timestamp.strftime("%Y-%m-%d")
        month = c.timestamp.strftime("%Y-%m")
        by_day.setdefault(day, []).append(c)
        by_month.setdefault(month, []).append(c)
    days = sorted(by_day)
    months = sorted(by_month)
    prev_day = by_day[days[-2]] if len(days) >= 2 else None
    prev_month = by_month[months[-2]] if len(months) >= 2 else None
    return {
        "PDH": FeatureValue(
            "PDH",
            FeatureStatus.CALCULATED if prev_day else FeatureStatus.UNAVAILABLE,
            max(c.high for c in prev_day) if prev_day else None,
            None if prev_day else "Need prior day",
        ),
        "PDL": FeatureValue(
            "PDL",
            FeatureStatus.CALCULATED if prev_day else FeatureStatus.UNAVAILABLE,
            min(c.low for c in prev_day) if prev_day else None,
            None if prev_day else "Need prior day",
        ),
        "PMH": FeatureValue(
            "PMH",
            FeatureStatus.CALCULATED if prev_month else FeatureStatus.UNAVAILABLE,
            max(c.high for c in prev_month) if prev_month else None,
            None if prev_month else "Need prior month",
        ),
        "PML": FeatureValue(
            "PML",
            FeatureStatus.CALCULATED if prev_month else FeatureStatus.UNAVAILABLE,
            min(c.low for c in prev_month) if prev_month else None,
            None if prev_month else "Need prior month",
        ),
    }


class StrategyFeatureEngine:
    """Deterministic feature computation for the reference strategy models."""

    def compute(
        self,
        *,
        strategy: StrategyConfig,
        candles_5m: Sequence[Candle],
        candles_15m: Sequence[Candle],
        candles_240m: Sequence[Candle],
        as_of: datetime | None = None,
        stale: bool = False,
        cvd_status: str = "UNAVAILABLE",
    ) -> dict[str, Any]:
        as_of = as_of or datetime.now(UTC)
        c5 = only_closed_candles(candles_5m, as_of=as_of, timeframe_minutes=5)
        c15 = only_closed_candles(candles_15m, as_of=as_of, timeframe_minutes=15)
        c240 = only_closed_candles(candles_240m, as_of=as_of, timeframe_minutes=240)

        if stale:
            return {
                "status": FeatureStatus.STALE.value,
                "features": {},
                "models": [],
                "confluence": {"confirmed": 0, "available": 0, "ratio": 0.0},
            }
        if len(c5) < 50:
            return {
                "status": FeatureStatus.UNAVAILABLE.value,
                "reason": "Insufficient closed 5m candles",
                "features": {},
                "models": [],
                "confluence": {"confirmed": 0, "available": 0, "ratio": 0.0},
            }

        opens = [c.open for c in c5]
        highs = [c.high for c in c5]
        lows = [c.low for c in c5]
        closes = [c.close for c in c5]
        volumes = [c.volume for c in c5]

        filters = strategy.signal_filters
        ema_fast = last_number(ema(closes, filters.ema_alignment.fast_ema))
        ema_slow = last_number(ema(closes, filters.ema_alignment.slow_ema))
        ema_struct = last_number(ema(closes, filters.ema_alignment.structural_ema))
        ema_lt = last_number(ema(closes, filters.ema_alignment.long_term_ema))
        adx_bundle = adx(highs, lows, closes, filters.adx.length)
        adx_val = last_number(adx_bundle["adx"])
        atr_val = last_number(atr(highs, lows, closes, 14))
        vwap_val = last_number(vwap(highs, lows, closes, volumes))
        vol = volume_metrics(volumes, filters.volume.length)
        swings = swing_points(highs, lows)
        levels = session_levels(c5)
        msb = market_structure_break(closes, swings["swing_highs"], swings["swing_lows"])
        fvgs = detect_fair_value_gaps(highs, lows, closes)

        features: dict[str, Any] = {
            "ema_9": FeatureValue("ema_9", _status(ema_fast), ema_fast).to_dict(),
            "ema_21": FeatureValue("ema_21", _status(ema_slow), ema_slow).to_dict(),
            "ema_50": FeatureValue("ema_50", _status(ema_struct), ema_struct).to_dict(),
            "ema_200": FeatureValue("ema_200", _status(ema_lt), ema_lt).to_dict(),
            "adx_11": FeatureValue("adx_11", _status(adx_val), adx_val).to_dict(),
            "atr_14": FeatureValue("atr_14", _status(atr_val), atr_val).to_dict(),
            "vwap": FeatureValue("vwap", _status(vwap_val), vwap_val).to_dict(),
            "volume_relative": FeatureValue(
                "volume_relative", _status(vol["relative"]), vol["relative"]
            ).to_dict(),
            "msb": FeatureValue("msb", FeatureStatus.CALCULATED, msb).to_dict(),
            "fvg_count": FeatureValue(
                "fvg_count", FeatureStatus.CALCULATED, len(fvgs)
            ).to_dict(),
            "cvd": FeatureValue(
                "cvd",
                FeatureStatus.UNAVAILABLE
                if cvd_status == "UNAVAILABLE"
                else FeatureStatus.CALCULATED,
                None,
                "No reliable order-flow provider configured"
                if cvd_status == "UNAVAILABLE"
                else None,
            ).to_dict(),
            **{k: v.to_dict() for k, v in levels.items()},
            "last_close": closes[-1],
            "last_open": opens[-1],
            "last_high": highs[-1],
            "last_low": lows[-1],
            "as_of": as_of.isoformat(),
            "closed_bars": {"5m": len(c5), "15m": len(c15), "240m": len(c240)},
        }

        htf_bias = "unknown"
        if len(c240) >= 2:
            htf_bias = "bullish" if c240[-1].close >= c240[-2].close else "bearish"
        features["htf_bias"] = FeatureValue(
            "htf_bias",
            FeatureStatus.CALCULATED if len(c240) >= 2 else FeatureStatus.UNAVAILABLE,
            htf_bias if len(c240) >= 2 else None,
            None if len(c240) >= 2 else "Need closed 240m candles",
        ).to_dict()

        models = [
            self._eval_m1(strategy, features, closes, highs, lows, atr_val, adx_val, ema_fast, ema_slow),
            self._eval_m2(strategy, features, closes, opens, atr_val, vwap_val, vol, htf_bias),
            self._eval_m3(strategy, features, closes, opens, atr_val, vol, cvd_status),
            self._eval_m4(strategy, features, c15, c240, fvgs, msb),
        ]
        available = [m for m in models if m.status != "UNAVAILABLE"]
        confirmed = [m for m in models if m.status == "CONFIRMED"]
        confluence = {
            "confirmed": len(confirmed),
            "available": len(available),
            "ratio": (len(confirmed) / len(available)) if available else 0.0,
            "confirmed_ids": [m.model_id for m in confirmed],
            "statuses": {m.model_id: m.status for m in models},
        }
        return {
            "status": FeatureStatus.CALCULATED.value,
            "features": features,
            "models": [m.to_dict() for m in models],
            "confluence": confluence,
            "stop_long": structural_3bar_swing_stop(highs, lows, "LONG"),
            "stop_short": structural_3bar_swing_stop(highs, lows, "SHORT"),
            "fibonacci": (
                fibonacci_levels(swings["swing_lows"][-1][1], swings["swing_highs"][-1][1])
                if swings["swing_highs"] and swings["swing_lows"]
                else None
            ),
        }

    def _eval_m1(self, strategy, features, closes, highs, lows, atr_val, adx_val, ema_fast, ema_slow):
        model = strategy.model_by_id("M1")
        if model is None or not model.enabled:
            return ModelEvaluation("M1", "UNAVAILABLE", ["Model disabled"])
        min_adx = strategy.signal_filters.adx.min_strength
        if adx_val is None or ema_fast is None or ema_slow is None:
            return ModelEvaluation("M1", "UNAVAILABLE", ["Missing ADX/EMA"])
        pdh = features["PDH"]["value"]
        pdl = features["PDL"]["value"]
        last = closes[-1]
        lookback = int(model.rules.get("sweep_lookback_bars", 10))
        recent_high = max(highs[-lookback:])
        recent_low = min(lows[-lookback:])
        evidence: list[str] = []
        confirmed = False
        if pdh is not None and recent_high > pdh and last < pdh and ema_fast > ema_slow and adx_val >= min_adx:
            confirmed = True
            evidence.append("Swept PDH with rejection and bullish EMA/ADX stack")
        if pdl is not None and recent_low < pdl and last > pdl and ema_fast < ema_slow and adx_val >= min_adx:
            confirmed = True
            evidence.append("Swept PDL with rejection and bearish EMA/ADX stack")
        if confirmed:
            return ModelEvaluation("M1", "CONFIRMED", evidence=evidence)
        return ModelEvaluation("M1", "REJECTED", reasons=["No PO3 sweep+rejection confluence"])

    def _eval_m2(self, strategy, features, closes, opens, atr_val, vwap_val, vol, htf_bias):
        model = strategy.model_by_id("M2")
        if model is None or not model.enabled:
            return ModelEvaluation("M2", "UNAVAILABLE", ["Model disabled"])
        if vwap_val is None or atr_val is None or vol["relative"] is None:
            return ModelEvaluation("M2", "UNAVAILABLE", ["Missing VWAP/ATR/volume"])
        body = abs(closes[-1] - opens[-1])
        min_body = float(model.rules.get("min_body_atr_multiplier", 1.0)) * atr_val
        vol_mult = float(model.rules.get("volume_multiplier", 1.3))
        reclaim_up = opens[-1] < vwap_val <= closes[-1]
        reclaim_down = opens[-1] > vwap_val >= closes[-1]
        if body >= min_body and vol["relative"] >= vol_mult and reclaim_up and htf_bias == "bullish":
            return ModelEvaluation(
                "M2",
                "CONFIRMED",
                evidence=["VWAP reclaim up with displacement and bullish HTF bias"],
            )
        if body >= min_body and vol["relative"] >= vol_mult and reclaim_down and htf_bias == "bearish":
            return ModelEvaluation(
                "M2",
                "CONFIRMED",
                evidence=["VWAP reclaim down with displacement and bearish HTF bias"],
            )
        return ModelEvaluation("M2", "REJECTED", reasons=["No VWAP displacement reclaim"])

    def _eval_m3(self, strategy, features, closes, opens, atr_val, vol, cvd_status):
        model = strategy.model_by_id("M3")
        if model is None or not model.enabled:
            return ModelEvaluation("M3", "UNAVAILABLE", ["Model disabled"])
        if cvd_status == "UNAVAILABLE":
            return ModelEvaluation(
                "M3",
                "UNAVAILABLE",
                reasons=["CVD_STATUS=UNAVAILABLE; refusing fabricated order-flow confirmation"],
            )
        # CVD available path (future providers).
        return ModelEvaluation("M3", "REJECTED", reasons=["CVD present but absorption rules not met"])

    def _eval_m4(self, strategy, features, c15, c240, fvgs, msb):
        model = strategy.model_by_id("M4")
        if model is None or not model.enabled:
            return ModelEvaluation("M4", "UNAVAILABLE", ["Model disabled"])
        if len(c15) < 20 or len(c240) < 3:
            return ModelEvaluation("M4", "UNAVAILABLE", ["Incomplete HTF/LTF closed candles"])
        if not fvgs:
            return ModelEvaluation("M4", "REJECTED", reasons=["No FVG detected on closed bars"])
        if msb.get("direction") in {"bullish_msb", "bearish_msb"} and fvgs:
            return ModelEvaluation(
                "M4",
                "CONFIRMED",
                evidence=[f"MSB={msb.get('direction')} with FVG count={len(fvgs)}"],
            )
        return ModelEvaluation("M4", "REJECTED", reasons=["No MSB+FVG confluence"])


def _status(value: Any) -> FeatureStatus:
    return FeatureStatus.CALCULATED if value is not None else FeatureStatus.UNAVAILABLE
