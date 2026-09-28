"""OKF strategy registry and deterministic signal generators (M1–M5).

Signals produce decision objects only; they never submit exchange orders.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from crypto_trading_mcp.market.indicators import (
    adx,
    atr,
    detect_fair_value_gaps,
    fibonacci_levels,
    last_number,
    market_structure_break,
    swing_points,
    vwap,
    volume_metrics,
)
from crypto_trading_mcp.market.models import Candle
from crypto_trading_mcp.okf.loader import load_and_validate_okf
from crypto_trading_mcp.strategy.features import session_levels


OKF_STRATEGY_IDS = (
    "M1_PO3_SWEEP",
    "M2_VWAP_RECLAIM",
    "M3_ICT_FVG_SWING",
    "M4_PREDICTION_MARKET_AI",
    "M5_MOMENTUM_BREAKOUT",
)


@dataclass
class StrategySignal:
    model_id: str
    status: str  # CONFIRMED | REJECTED | UNAVAILABLE
    side: str | None = None
    entry_style: str = "LIMIT"
    reasons: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    submits_exchange_order: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "status": self.status,
            "side": self.side,
            "entry_style": self.entry_style,
            "reasons": list(self.reasons),
            "evidence": list(self.evidence),
            "metadata": dict(self.metadata),
            "submits_exchange_order": False,
            "requires_risk_engine": True,
        }


class OKFStrategyRegistry:
    """Register and expose the five OKF strategies from the canonical JSON."""

    def __init__(self, loaded: dict[str, Any] | None = None) -> None:
        self.loaded = loaded or load_and_validate_okf()
        self._strategies = {
            str(s["model_id"]): s
            for s in self.loaded["data"].get("trading_models_and_strategies") or []
            if isinstance(s, dict) and s.get("model_id")
        }

    def list_ids(self) -> list[str]:
        return list(OKF_STRATEGY_IDS)

    def get(self, model_id: str) -> dict[str, Any]:
        if model_id not in self._strategies:
            raise KeyError(model_id)
        return dict(self._strategies[model_id])

    def list_all(self) -> list[dict[str, Any]]:
        return [self.get(i) for i in OKF_STRATEGY_IDS if i in self._strategies]

    def catalog(self) -> dict[str, Any]:
        return {
            "version": self.loaded["version"],
            "hash": self.loaded["hash"],
            "strategies": self.list_all(),
            "note": "Signals require RiskEngine; no direct exchange submission.",
        }


def evaluate_m1_po3_sweep(
    candles: Sequence[Candle],
    *,
    adx_min: float = 21.0,
    volume_mult: float = 1.3,
) -> StrategySignal:
    mid = "M1_PO3_SWEEP"
    if len(candles) < 40:
        return StrategySignal(mid, "UNAVAILABLE", reasons=["Insufficient candles"])
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    closes = [c.close for c in candles]
    volumes = [c.volume for c in candles]
    adx_val = last_number(adx(highs, lows, closes, 14)["adx"])
    vol = volume_metrics(volumes, 20)
    levels = session_levels(candles)
    if adx_val is None or adx_val <= adx_min:
        return StrategySignal(mid, "REJECTED", reasons=[f"ADX<{adx_min}"])
    if (vol.get("relative") or 0) < volume_mult:
        return StrategySignal(mid, "REJECTED", reasons=[f"volume<{volume_mult}x"])
    pdh = levels["PDH"].value
    pdl = levels["PDL"].value
    pmh = levels["PMH"].value
    pml = levels["PML"].value
    last = candles[-1]
    # Sweep + body close rejection
    if pdh is not None and last.high > pdh and last.close < pdh and last.close < last.open:
        return StrategySignal(
            mid,
            "CONFIRMED",
            side="SHORT",
            evidence=["PDH sweep with bearish body rejection"],
            metadata={"level": "PDH", "adx": adx_val, "volume_rel": vol.get("relative")},
        )
    if pdl is not None and last.low < pdl and last.close > pdl and last.close > last.open:
        return StrategySignal(
            mid,
            "CONFIRMED",
            side="LONG",
            evidence=["PDL sweep with bullish body rejection"],
            metadata={"level": "PDL", "adx": adx_val, "volume_rel": vol.get("relative")},
        )
    if pmh is not None and last.high > pmh and last.close < pmh and last.close < last.open:
        return StrategySignal(
            mid,
            "CONFIRMED",
            side="SHORT",
            evidence=["PMH sweep with bearish body rejection"],
            metadata={"level": "PMH", "adx": adx_val},
        )
    if pml is not None and last.low < pml and last.close > pml and last.close > last.open:
        return StrategySignal(
            mid,
            "CONFIRMED",
            side="LONG",
            evidence=["PML sweep with bullish body rejection"],
            metadata={"level": "PML", "adx": adx_val},
        )
    return StrategySignal(mid, "REJECTED", reasons=["No PDH/PDL/PMH/PML sweep+rejection"])


def evaluate_m2_vwap_reclaim(
    candles: Sequence[Candle],
    candles_4h: Sequence[Candle] | None = None,
    *,
    displacement_atr_mult: float = 0.3,
) -> StrategySignal:
    mid = "M2_VWAP_RECLAIM"
    if len(candles) < 30:
        return StrategySignal(mid, "UNAVAILABLE", reasons=["Insufficient candles"])
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    closes = [c.close for c in candles]
    opens = [c.open for c in candles]
    volumes = [c.volume for c in candles]
    vwap_val = last_number(vwap(highs, lows, closes, volumes))
    atr_val = last_number(atr(highs, lows, closes, 14))
    if vwap_val is None or atr_val is None or atr_val <= 0:
        return StrategySignal(mid, "UNAVAILABLE", reasons=["VWAP/ATR unavailable"])
    htf = "unknown"
    if candles_4h and len(candles_4h) >= 2:
        htf = "bullish" if candles_4h[-1].close >= candles_4h[-2].close else "bearish"
    else:
        return StrategySignal(mid, "UNAVAILABLE", reasons=["4H bias unavailable"])
    body = abs(closes[-1] - opens[-1])
    if body < displacement_atr_mult * atr_val:
        return StrategySignal(mid, "REJECTED", reasons=["Displacement < 0.3 ATR"])
    # Reclaim: prior close below VWAP, current close above (bullish) aligned with HTF
    if len(closes) >= 2 and closes[-2] < vwap_val <= closes[-1] and htf == "bullish":
        return StrategySignal(
            mid,
            "CONFIRMED",
            side="LONG",
            evidence=["VWAP reclaim with displacement, 4H bullish"],
            metadata={"vwap": vwap_val, "displacement": body, "atr": atr_val, "htf": htf},
        )
    if len(closes) >= 2 and closes[-2] > vwap_val >= closes[-1] and htf == "bearish":
        return StrategySignal(
            mid,
            "CONFIRMED",
            side="SHORT",
            evidence=["VWAP lose with displacement, 4H bearish"],
            metadata={"vwap": vwap_val, "displacement": body, "atr": atr_val, "htf": htf},
        )
    return StrategySignal(mid, "REJECTED", reasons=["No VWAP reclaim confluence"])


def evaluate_m3_ict_fvg(
    candles_15m: Sequence[Candle],
    candles_4h: Sequence[Candle],
    *,
    min_fib: float = 0.5,
) -> StrategySignal:
    mid = "M3_ICT_FVG_SWING"
    if len(candles_15m) < 40 or len(candles_4h) < 5:
        return StrategySignal(mid, "UNAVAILABLE", reasons=["Insufficient HTF/LTF candles"])
    h4_highs = [c.high for c in candles_4h]
    h4_lows = [c.low for c in candles_4h]
    h4_swings = swing_points(h4_highs, h4_lows)
    # Require a prior HTF swing sweep (last 4H candle traded through prior swing)
    swept = False
    if h4_swings["swing_highs"] and candles_4h[-1].high > h4_swings["swing_highs"][-1][1]:
        swept = True
    if h4_swings["swing_lows"] and candles_4h[-1].low < h4_swings["swing_lows"][-1][1]:
        swept = True
    if not swept:
        return StrategySignal(mid, "REJECTED", reasons=["No 4H swing high/low sweep"])

    highs = [c.high for c in candles_15m]
    lows = [c.low for c in candles_15m]
    closes = [c.close for c in candles_15m]
    swings = swing_points(highs, lows)
    msb = market_structure_break(closes, swings["swing_highs"], swings["swing_lows"])
    direction = str(msb.get("direction") or "none")
    if direction not in {"bullish_msb", "bearish_msb"}:
        return StrategySignal(mid, "REJECTED", reasons=["No 15m MSB"])
    fvgs = detect_fair_value_gaps(highs, lows, closes)
    if not fvgs:
        return StrategySignal(mid, "REJECTED", reasons=["No 15m FVG"])
    if not swings["swing_highs"] or not swings["swing_lows"]:
        return StrategySignal(mid, "REJECTED", reasons=["No swings for fib"])
    fib = fibonacci_levels(swings["swing_lows"][-1][1], swings["swing_highs"][-1][1])
    last = closes[-1]
    fib_50 = fib.get("0.5")
    if fib_50 is None:
        return StrategySignal(mid, "REJECTED", reasons=["Fib 0.5 unavailable"])
    side = "LONG" if direction == "bullish_msb" else "SHORT"
    fvg = fvgs[-1]
    fvg_low = float(min(fvg.get("bottom", last), fvg.get("top", last)))
    fvg_high = float(max(fvg.get("bottom", last), fvg.get("top", last)))
    in_fvg = fvg_low <= last <= fvg_high
    # Retrace >= 0.5: for longs, price at/below 0.5 fib; for shorts at/above.
    retraced = (side == "LONG" and last <= fib_50) or (side == "SHORT" and last >= fib_50)
    if min_fib >= 0.5 and not (retraced and in_fvg):
        return StrategySignal(mid, "REJECTED", reasons=["No retrace to >=0.5 Fib in FVG"])
    return StrategySignal(
        mid,
        "CONFIRMED",
        side=side,
        entry_style="LIMIT",
        evidence=["4H sweep → 15m MSB → FVG → Fib retrace; limit in FVG"],
        metadata={"fvg": fvg, "fib_0_5": fib_50, "msb": msb},
    )


def evaluate_m4_prediction_ensemble(
    *,
    provider_probs: dict[str, float],
    market_prob: float,
    vader_sentiment: float,
    ensemble_weights: dict[str, float] | None = None,
    edge_threshold: float = 0.04,
) -> StrategySignal:
    mid = "M4_PREDICTION_MARKET_AI"
    weights = ensemble_weights or {
        "grok_forecaster": 0.30,
        "claude_news_analyst": 0.20,
        "gpt4_bull_advocate": 0.20,
        "gemini_bear_advocate": 0.15,
        "deepseek_risk_manager": 0.15,
    }
    # Provider names are configuration labels only; local/mock providers OK.
    missing = [k for k in weights if k not in provider_probs]
    if missing:
        return StrategySignal(
            mid,
            "UNAVAILABLE",
            reasons=[f"Missing provider labels: {missing}"],
            metadata={"note": "Labels only; paid providers not required"},
        )
    p_model = sum(weights[k] * float(provider_probs[k]) for k in weights)
    edge = p_model - float(market_prob)
    if vader_sentiment < 0:
        return StrategySignal(
            mid,
            "REJECTED",
            reasons=["VADER sentiment < 0"],
            metadata={"p_model": p_model, "edge": edge, "sentiment": vader_sentiment},
        )
    if edge <= edge_threshold:
        return StrategySignal(
            mid,
            "REJECTED",
            reasons=[f"edge {edge:.4f} <= {edge_threshold}"],
            metadata={"p_model": p_model, "edge": edge, "sentiment": vader_sentiment},
        )
    return StrategySignal(
        mid,
        "CONFIRMED",
        side="LONG",
        entry_style="LIMIT",
        evidence=[f"Ensemble edge {edge:.4f} with non-negative sentiment"],
        metadata={
            "p_model": p_model,
            "p_market": market_prob,
            "edge": edge,
            "sentiment": vader_sentiment,
            "weights": weights,
            "providers_are_labels_only": True,
        },
    )


def evaluate_m5_donchian_breakout(
    candles_1h: Sequence[Candle],
    *,
    period: int = 20,
    volume_mult: float = 1.5,
    trail_atr_mult: float = 2.0,
) -> StrategySignal:
    mid = "M5_MOMENTUM_BREAKOUT"
    if len(candles_1h) < period + 5:
        return StrategySignal(mid, "UNAVAILABLE", reasons=["Insufficient 1h candles"])
    highs = [c.high for c in candles_1h]
    lows = [c.low for c in candles_1h]
    closes = [c.close for c in candles_1h]
    volumes = [c.volume for c in candles_1h]
    # Donchian prior period excluding current bar
    channel_high = max(highs[-(period + 1) : -1])
    avg_vol = sum(volumes[-(period + 1) : -1]) / period
    atr_val = last_number(atr(highs, lows, closes, 14))
    last = candles_1h[-1]
    if last.close <= channel_high:
        return StrategySignal(mid, "REJECTED", reasons=["No 20-period high break"])
    if avg_vol <= 0 or last.volume < volume_mult * avg_vol:
        return StrategySignal(mid, "REJECTED", reasons=[f"volume < {volume_mult}x avg"])
    trail = None if atr_val is None else trail_atr_mult * atr_val
    return StrategySignal(
        mid,
        "CONFIRMED",
        side="LONG",
        evidence=["Donchian 20 high break with volume confirmation"],
        metadata={
            "channel_high": channel_high,
            "volume_rel": last.volume / avg_vol if avg_vol else None,
            "trail_stop_distance": trail,
            "trail_atr_mult": trail_atr_mult,
        },
    )


def evaluate_all_okf_strategies(
    *,
    candles_5m: Sequence[Candle],
    candles_15m: Sequence[Candle] | None = None,
    candles_1h: Sequence[Candle] | None = None,
    candles_4h: Sequence[Candle] | None = None,
    provider_probs: dict[str, float] | None = None,
    market_prob: float = 0.5,
    vader_sentiment: float = 0.0,
) -> list[StrategySignal]:
    c15 = candles_15m or candles_5m
    c4h = candles_4h or []
    c1h = candles_1h or candles_5m
    signals = [
        evaluate_m1_po3_sweep(candles_5m),
        evaluate_m2_vwap_reclaim(candles_5m, c4h),
        evaluate_m3_ict_fvg(c15, c4h) if c4h else StrategySignal("M3_ICT_FVG_SWING", "UNAVAILABLE", reasons=["No 4H"]),
        evaluate_m4_prediction_ensemble(
            provider_probs=provider_probs
            or {
                "grok_forecaster": 0.55,
                "claude_news_analyst": 0.55,
                "gpt4_bull_advocate": 0.55,
                "gemini_bear_advocate": 0.55,
                "deepseek_risk_manager": 0.55,
            },
            market_prob=market_prob,
            vader_sentiment=vader_sentiment,
        ),
        evaluate_m5_donchian_breakout(c1h),
    ]
    return signals
