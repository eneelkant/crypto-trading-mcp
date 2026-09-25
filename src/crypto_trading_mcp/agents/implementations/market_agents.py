from __future__ import annotations

import json
from typing import Any

from crypto_trading_mcp.agents.base import BaseAgent
from crypto_trading_mcp.market.indicators import compute_indicator_bundle
from crypto_trading_mcp.market.models import MarketSnapshot
from crypto_trading_mcp.orchestration.context import ExecutionContext


def _require_market(context: ExecutionContext) -> MarketSnapshot:
    snapshot = context.artifacts.get("market_snapshot")
    if isinstance(snapshot, MarketSnapshot):
        return snapshot
    if context.market_data is None:
        raise RuntimeError("Market data service is not configured")
    snapshot = context.market_data.get_snapshot(
        context.symbol,
        timeframe=context.timeframe,
        exchange_id=context.exchange_id,
    )
    context.artifacts["market_snapshot"] = snapshot
    return snapshot


def _indicator_bundle(snapshot: MarketSnapshot) -> dict[str, Any]:
    candles = snapshot.candles
    bundle = compute_indicator_bundle(
        [c.open for c in candles],
        [c.high for c in candles],
        [c.low for c in candles],
        [c.close for c in candles],
        [c.volume for c in candles],
    )
    return bundle


def _regime_from_indicators(indicators: dict[str, Any]) -> str:
    close = indicators.get("last_close")
    sma20 = indicators.get("sma_20")
    sma50 = indicators.get("sma_50")
    vol = indicators.get("volatility_20")
    if close is None or sma20 is None:
        return "unknown"
    if vol is not None and vol > 0.05:
        return "high_volatility"
    if sma50 is not None and close > sma20 > sma50:
        return "bullish"
    if sma50 is not None and close < sma20 < sma50:
        return "bearish"
    return "range"


class MarketIntelligenceAgent(BaseAgent):
    agent_id = "market_intelligence"
    name = "Market Intelligence"
    config_key = "market_intelligence"
    responsibility = "Normalize market price, volume, volatility, and regime."

    async def analyze(self, context: ExecutionContext) -> dict[str, Any]:
        snapshot = _require_market(context)
        if not snapshot.available or snapshot.stale:
            return {
                "status": "UNAVAILABLE" if not snapshot.available else "STALE",
                "decision": "NO_TRADE",
                "confidence": 0.0,
                "risk_flags": ["stale_or_missing_market_data"],
                "symbol": context.symbol,
                "timeframe": context.timeframe,
                "data_freshness": {
                    "stale": snapshot.stale,
                    "max_age_seconds": snapshot.max_age_seconds,
                    "error": snapshot.error,
                },
                "evidence": ["Required market data unavailable or stale"],
            }

        indicators = _indicator_bundle(snapshot)
        context.artifacts["indicators"] = indicators
        regime = _regime_from_indicators(indicators)
        context.artifacts["market_regime"] = regime

        interpretation = {}
        try:
            interpretation = self.llm_json(
                context,
                system="You are the Market Intelligence agent. Interpret only provided facts. Return JSON.",
                prompt=(
                    "Interpret this normalized market snapshot. Do not invent prices.\n"
                    + json.dumps(
                        {
                            "ticker": snapshot.ticker.to_dict() if snapshot.ticker else None,
                            "indicators": indicators,
                            "regime_seed": regime,
                        },
                        default=str,
                    )
                ),
            )
        except Exception as exc:  # noqa: BLE001
            interpretation = {"technical_summary": f"LLM unavailable: {exc}", "confidence": 0.55}

        confidence = float(interpretation.get("confidence", 0.7))
        return {
            "symbol": snapshot.symbol,
            "timeframe": snapshot.timeframe,
            "current_price": snapshot.ticker.last if snapshot.ticker else None,
            "volatility": indicators.get("volatility_20"),
            "volume": indicators.get("volume_last"),
            "market_regime": regime,
            "technical_summary": interpretation.get(
                "technical_summary", "Deterministic market snapshot ready."
            ),
            "indicators": indicators,
            "data_freshness": {
                "stale": False,
                "fetched_at": snapshot.fetched_at.isoformat(),
                "ticker_age_seconds": snapshot.ticker.age_seconds if snapshot.ticker else None,
                "max_age_seconds": snapshot.max_age_seconds,
            },
            "confidence": confidence,
            "evidence": [
                f"price={snapshot.ticker.last if snapshot.ticker else None}",
                f"regime={regime}",
            ],
            "decision": None,
        }


class TechnicalAnalysisAgent(BaseAgent):
    agent_id = "technical_analysis"
    name = "Technical Analysis"
    config_key = "technical_analysis"
    responsibility = "Interpret deterministic indicators; never invent values."

    async def analyze(self, context: ExecutionContext) -> dict[str, Any]:
        snapshot = _require_market(context)
        if not snapshot.available or snapshot.stale:
            return {
                "decision": "NO_TRADE",
                "confidence": 0.0,
                "risk_flags": ["stale_or_missing_market_data"],
                "bullish_signals": [],
                "bearish_signals": [],
                "neutral_signals": ["Market data unavailable"],
            }

        indicators = context.artifacts.get("indicators") or _indicator_bundle(snapshot)
        context.artifacts["indicators"] = indicators

        # Deterministic signal extraction before LLM interpretation.
        bullish: list[str] = []
        bearish: list[str] = []
        neutral: list[str] = []
        rsi_v = indicators.get("rsi_14")
        if isinstance(rsi_v, (int, float)):
            if rsi_v >= 70:
                bearish.append(f"RSI overbought ({rsi_v:.2f})")
            elif rsi_v <= 30:
                bullish.append(f"RSI oversold ({rsi_v:.2f})")
            else:
                neutral.append(f"RSI mid-range ({rsi_v:.2f})")
        macd_h = indicators.get("macd_histogram")
        if isinstance(macd_h, (int, float)):
            if macd_h > 0:
                bullish.append("MACD histogram positive")
            elif macd_h < 0:
                bearish.append("MACD histogram negative")
        close = indicators.get("last_close")
        sma20 = indicators.get("sma_20")
        if isinstance(close, (int, float)) and isinstance(sma20, (int, float)):
            if close > sma20:
                bullish.append("Price above SMA20")
            else:
                bearish.append("Price below SMA20")

        interpretation = self.llm_json(
            context,
            system=(
                "You are the Technical Analysis agent. Use only the provided deterministic "
                "indicator values. Return JSON with bullish_signals, bearish_signals, "
                "neutral_signals, trend_strength, momentum, volatility, confidence, reasoning."
            ),
            prompt=json.dumps(
                {"indicators": indicators, "seed_bullish": bullish, "seed_bearish": bearish},
                default=str,
            ),
        )

        return {
            "bullish_signals": list(
                dict.fromkeys(bullish + list(interpretation.get("bullish_signals", [])))
            ),
            "bearish_signals": list(
                dict.fromkeys(bearish + list(interpretation.get("bearish_signals", [])))
            ),
            "neutral_signals": list(
                dict.fromkeys(neutral + list(interpretation.get("neutral_signals", [])))
            ),
            "trend_strength": interpretation.get("trend_strength", "moderate"),
            "momentum": interpretation.get("momentum", "unknown"),
            "volatility": interpretation.get(
                "volatility", indicators.get("volatility_20")
            ),
            "confidence": float(interpretation.get("confidence", 0.55)),
            "reasoning": interpretation.get("reasoning", ""),
            "indicators": indicators,
            "evidence": bullish + bearish,
            "decision": None,
        }


class TrendAgent(BaseAgent):
    agent_id = "trend"
    name = "Trend Agent"
    config_key = "trend"
    responsibility = "Multi-horizon trend structure from deterministic MAs + LLM notes."

    async def analyze(self, context: ExecutionContext) -> dict[str, Any]:
        snapshot = _require_market(context)
        if not snapshot.available or snapshot.stale:
            return {
                "decision": "NO_TRADE",
                "confidence": 0.0,
                "risk_flags": ["stale_or_missing_market_data"],
            }
        indicators = context.artifacts.get("indicators") or _indicator_bundle(snapshot)
        close = indicators.get("last_close")
        ema12 = indicators.get("ema_12")
        ema26 = indicators.get("ema_26")
        sma20 = indicators.get("sma_20")
        sma50 = indicators.get("sma_50")

        def _dir(fast: Any, slow: Any) -> str:
            if not isinstance(fast, (int, float)) or not isinstance(slow, (int, float)):
                return "unknown"
            if fast > slow:
                return "up"
            if fast < slow:
                return "down"
            return "sideways"

        short_term = _dir(ema12, ema26)
        medium_term = _dir(close, sma20)
        long_term = _dir(sma20, sma50) if sma50 is not None else _dir(close, sma20)
        dirs = {short_term, medium_term, long_term}
        alignment = "aligned" if len(dirs) == 1 and "unknown" not in dirs else "partial"
        regime_change = short_term != long_term and "unknown" not in dirs

        interpretation = self.llm_json(
            context,
            system="You are the Trend agent. Interpret provided trend structure. Return JSON.",
            prompt=json.dumps(
                {
                    "short_term": short_term,
                    "medium_term": medium_term,
                    "long_term": long_term,
                    "alignment": alignment,
                    "regime_change": regime_change,
                    "indicators": indicators,
                },
                default=str,
            ),
        )
        return {
            "short_term": interpretation.get("short_term", short_term),
            "medium_term": interpretation.get("medium_term", medium_term),
            "long_term": interpretation.get("long_term", long_term),
            "alignment": interpretation.get("alignment", alignment),
            "regime_change": bool(interpretation.get("regime_change", regime_change)),
            "confidence": float(interpretation.get("confidence", 0.55)),
            "reasoning": interpretation.get("reasoning", ""),
            "evidence": [f"short={short_term}", f"medium={medium_term}", f"long={long_term}"],
            "decision": None,
        }
