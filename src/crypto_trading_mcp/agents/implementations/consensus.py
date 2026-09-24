from __future__ import annotations

from typing import Any

from crypto_trading_mcp.agents.base import BaseAgent
from crypto_trading_mcp.agents.messages import MessageStatus
from crypto_trading_mcp.orchestration.context import ExecutionContext

CRITICAL_MARKET_AGENTS = ("market_intelligence", "technical_analysis", "trend")


class ConsensusAgent(BaseAgent):
    agent_id = "consensus"
    name = "Debate / Consensus"
    config_key = "consensus"
    responsibility = (
        "Weighted debate across agents. Preserve disagreement. Never execute trades."
    )

    async def analyze(self, context: ExecutionContext) -> dict[str, Any]:
        # Deterministic consensus gate — LLM may annotate but cannot override NO_TRADE
        # when market data is stale/missing.
        missing: list[str] = []
        supporting: list[str] = []
        disagreements: list[str] = []

        for agent_id in CRITICAL_MARKET_AGENTS:
            message = context.get(agent_id)
            if message is None or message.status != MessageStatus.OK:
                missing.append(agent_id)
            payload = message.payload if message else {}
            if payload.get("decision") == "NO_TRADE" or payload.get("status") in {
                "UNAVAILABLE",
                "STALE",
            }:
                missing.append(f"{agent_id}:stale_or_unavailable")

        for agent_id in ("sentiment", "on_chain", "macro_event"):
            message = context.get(agent_id)
            if message is None or message.status == MessageStatus.UNAVAILABLE:
                missing.append(agent_id)
            elif message.payload.get("status") == "UNAVAILABLE":
                missing.append(agent_id)

        market = context.get("market_intelligence")
        market_payload = market.payload if market else {}
        critical_gap = any(
            item in CRITICAL_MARKET_AGENTS or item.endswith("stale_or_unavailable")
            for item in missing
        )
        if critical_gap or (
            market is None
            or market.status != MessageStatus.OK
            or market_payload.get("status") in {"UNAVAILABLE", "STALE"}
            or market_payload.get("decision") == "NO_TRADE"
        ):
            return {
                "decision": "NO_TRADE",
                "confidence": 0.0,
                "supporting_agents": [],
                "disagreement_summary": "Critical market inputs missing or stale.",
                "missing_information": sorted(set(missing)),
                "invalidating_conditions": [
                    "Required market data stale or unavailable"
                ],
                "risk_flags": ["stale_or_missing_market_data"],
                "evidence": ["Fail-closed: no discretionary trade hypothesis"],
            }

        bull = context.get("bull")
        bear = context.get("bear")
        strategy = context.get("strategy")
        technical = context.get("technical_analysis")
        trend = context.get("trend")

        scores = {"LONG": 0.0, "SHORT": 0.0, "NEUTRAL": 0.0}
        weights = {
            "strategy": 1.2,
            "technical_analysis": 1.0,
            "trend": 1.0,
            "bull": 0.8,
            "bear": 0.8,
        }

        def _add(agent_id: str, direction: str, confidence: float, quality: float) -> None:
            direction = direction.upper()
            if direction in {"BUY", "LONG"}:
                key = "LONG"
            elif direction in {"SELL", "SHORT"}:
                key = "SHORT"
            elif direction in {"NO_TRADE"}:
                return
            else:
                key = "NEUTRAL"
            scores[key] += weights.get(agent_id, 1.0) * confidence * quality
            supporting.append(f"{agent_id}:{key}:{confidence:.2f}")

        def _quality(agent_id: str) -> float:
            message = context.get(agent_id)
            if message is None or message.status != MessageStatus.OK:
                return 0.25
            # Lower weight when alternative data is missing from that agent's inputs.
            return 1.0

        if strategy and strategy.payload.get("direction"):
            _add(
                "strategy",
                str(strategy.payload.get("direction")),
                strategy.confidence,
                _quality("strategy"),
            )
        if technical:
            bullish_n = len(technical.payload.get("bullish_signals", []))
            bearish_n = len(technical.payload.get("bearish_signals", []))
            if bullish_n > bearish_n:
                _add("technical_analysis", "LONG", technical.confidence, 1.0)
            elif bearish_n > bullish_n:
                _add("technical_analysis", "SHORT", technical.confidence, 1.0)
            else:
                _add("technical_analysis", "NEUTRAL", technical.confidence, 1.0)
        if trend:
            short = str(trend.payload.get("short_term", "")).lower()
            if short == "up":
                _add("trend", "LONG", trend.confidence, 1.0)
            elif short == "down":
                _add("trend", "SHORT", trend.confidence, 1.0)
            else:
                _add("trend", "NEUTRAL", trend.confidence, 0.8)
        if bull:
            _add("bull", "LONG", bull.confidence, 0.9)
        if bear:
            _add("bear", "SHORT", bear.confidence, 0.9)

        if bull and bear and abs(bull.confidence - bear.confidence) < 0.1:
            disagreements.append(
                f"Bull ({bull.confidence:.2f}) and Bear ({bear.confidence:.2f}) are close."
            )

        best = max(scores, key=scores.get)
        total = sum(scores.values()) or 1.0
        confidence = scores[best] / total

        # Contested debate → NEUTRAL rather than forcing a side.
        ranked = sorted(scores.values(), reverse=True)
        if len(ranked) > 1 and ranked[0] > 0 and (ranked[0] - ranked[1]) / total < 0.08:
            best = "NEUTRAL"
            disagreements.append("Scores too close; preserving disagreement as NEUTRAL.")
            confidence = min(confidence, 0.5)

        min_conf = float(
            context.settings.trading_yaml()
            .get("analysis", {})
            .get("minimum_confidence_for_direction", 0.55)
        )
        if best in {"LONG", "SHORT"} and confidence < min_conf:
            disagreements.append(
                f"Direction {best} below minimum confidence {min_conf}."
            )
            best = "NEUTRAL"

        return {
            "decision": best,
            "confidence": round(float(confidence), 4),
            "supporting_agents": supporting,
            "disagreement_summary": "; ".join(disagreements)
            if disagreements
            else "No major unresolved conflict recorded.",
            "missing_information": sorted(set(missing)),
            "invalidating_conditions": [
                "Fresh market data required",
                "Risk engine not yet implemented (Phase 4+)",
            ],
            "scores": scores,
            "evidence": supporting,
            "risk_flags": ["analysis_only_no_execution"],
        }
