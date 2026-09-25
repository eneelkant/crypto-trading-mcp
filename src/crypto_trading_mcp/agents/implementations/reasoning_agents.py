from __future__ import annotations

import json
from typing import Any

from crypto_trading_mcp.agents.base import BaseAgent
from crypto_trading_mcp.orchestration.context import ExecutionContext
from crypto_trading_mcp.providers.external import (
    UnavailableMacroEventProvider,
    UnavailableOnChainProvider,
    UnavailableSentimentProvider,
)


class SentimentAgent(BaseAgent):
    agent_id = "sentiment"
    name = "Sentiment Agent"
    config_key = "sentiment"
    responsibility = "Surface sentiment only from configured providers; never fabricate."

    def __init__(self, provider: Any | None = None) -> None:
        self.provider = provider or UnavailableSentimentProvider()

    async def analyze(self, context: ExecutionContext) -> dict[str, Any]:
        result = self.provider.fetch(context.symbol)
        if result.status == "UNAVAILABLE":
            return {
                "status": "UNAVAILABLE",
                "decision": None,
                "confidence": 0.0,
                "reason": result.reason,
                "evidence": [],
                "classification": None,
                "risk_flags": ["sentiment_unavailable"],
            }
        interpretation = self.llm_json(
            context,
            system="Sentiment agent. Classify provided sources only. Return JSON.",
            prompt=json.dumps(result.to_dict(), default=str),
        )
        return {
            "status": "AVAILABLE",
            "confidence": float(interpretation.get("confidence", 0.5)),
            "classification": interpretation.get("classification"),
            "summary": interpretation.get("summary"),
            "sources": result.sources,
            "evidence": interpretation.get("evidence", []),
            "decision": None,
        }


class OnChainAgent(BaseAgent):
    agent_id = "on_chain"
    name = "On-Chain Intelligence"
    config_key = "on_chain"
    responsibility = "On-chain metrics only when a provider exists; never fabricate."

    def __init__(self, provider: Any | None = None) -> None:
        self.provider = provider or UnavailableOnChainProvider()

    async def analyze(self, context: ExecutionContext) -> dict[str, Any]:
        result = self.provider.fetch(context.symbol)
        if result.status == "UNAVAILABLE":
            return {
                "status": "UNAVAILABLE",
                "decision": None,
                "confidence": 0.0,
                "reason": result.reason,
                "risk_flags": ["on_chain_unavailable"],
                "evidence": [],
            }
        interpretation = self.llm_json(
            context,
            system="On-chain agent. Use provided metrics only. Return JSON.",
            prompt=json.dumps(result.to_dict(), default=str),
        )
        return {
            "status": "AVAILABLE",
            "confidence": float(interpretation.get("confidence", 0.5)),
            "metrics": result.data,
            "summary": interpretation.get("summary"),
            "evidence": interpretation.get("evidence", []),
            "decision": None,
        }


class MacroEventAgent(BaseAgent):
    agent_id = "macro_event"
    name = "Macro / Event Agent"
    config_key = "macro_event"
    responsibility = "Macro/event risk only from configured calendars; never fabricate."

    def __init__(self, provider: Any | None = None) -> None:
        self.provider = provider or UnavailableMacroEventProvider()

    async def analyze(self, context: ExecutionContext) -> dict[str, Any]:
        result = self.provider.fetch(context.symbol)
        if result.status == "UNAVAILABLE":
            return {
                "status": "UNAVAILABLE",
                "event_risk": "unknown",
                "trade_restriction": False,
                "reason": result.reason,
                "confidence": 0.0,
                "risk_flags": ["macro_unavailable"],
                "decision": None,
                "evidence": [],
            }
        interpretation = self.llm_json(
            context,
            system="Macro/Event agent. Return JSON with event_risk and trade_restriction.",
            prompt=json.dumps(result.to_dict(), default=str),
        )
        return {
            "status": "AVAILABLE",
            "event_risk": interpretation.get("event_risk", "low"),
            "trade_restriction": bool(interpretation.get("trade_restriction", False)),
            "reason": interpretation.get("reason", ""),
            "confidence": float(interpretation.get("confidence", 0.5)),
            "evidence": interpretation.get("evidence", []),
            "decision": None,
        }


class StrategyAgent(BaseAgent):
    agent_id = "strategy"
    name = "Strategy Agent"
    config_key = "strategy"
    responsibility = "Combine analytical agents into a non-executable strategy hypothesis."

    async def analyze(self, context: ExecutionContext) -> dict[str, Any]:
        bundle = {
            key: (msg.payload if msg else None)
            for key, msg in (
                ("market_intelligence", context.get("market_intelligence")),
                ("technical_analysis", context.get("technical_analysis")),
                ("trend", context.get("trend")),
                ("sentiment", context.get("sentiment")),
                ("on_chain", context.get("on_chain")),
                ("macro_event", context.get("macro_event")),
            )
        }
        market = bundle.get("market_intelligence") or {}
        if market.get("decision") == "NO_TRADE" or market.get("status") in {
            "UNAVAILABLE",
            "STALE",
        }:
            return {
                "decision": "NO_TRADE",
                "market_regime": market.get("market_regime", "unknown"),
                "direction": "NO_TRADE",
                "strategy_type": "none",
                "entry_conditions": [],
                "exit_conditions": [],
                "invalidation_conditions": ["Market data stale or unavailable"],
                "time_horizon": "none",
                "confidence": 0.0,
                "supporting_evidence": [],
                "contradicting_evidence": ["Missing/stale market data"],
                "risk_flags": ["stale_or_missing_market_data"],
            }

        knowledge = context.artifacts.get("strategy_knowledge")
        interpretation = self.llm_json(
            context,
            system=(
                "You are the Strategy agent. Produce a hypothesis only — never an order. "
                "Use strategy_knowledge as a reference specification, not a profitability guarantee. "
                "Return JSON with market_regime, direction, strategy_type, entry_conditions, "
                "exit_conditions, invalidation_conditions, time_horizon, confidence, "
                "supporting_evidence, contradicting_evidence, supporting_model_ids."
            ),
            prompt=json.dumps(
                {"analysis": bundle, "strategy_knowledge": knowledge},
                default=str,
            ),
        )
        direction = str(interpretation.get("direction", "NEUTRAL")).upper()
        if direction not in {"LONG", "SHORT", "NEUTRAL", "NO_TRADE", "HOLD"}:
            direction = "NEUTRAL"
        return {
            "market_regime": interpretation.get(
                "market_regime", context.artifacts.get("market_regime", "unknown")
            ),
            "direction": direction,
            "strategy_type": interpretation.get("strategy_type", "unspecified"),
            "entry_conditions": list(interpretation.get("entry_conditions", [])),
            "exit_conditions": list(interpretation.get("exit_conditions", [])),
            "invalidation_conditions": list(
                interpretation.get("invalidation_conditions", [])
            ),
            "time_horizon": interpretation.get("time_horizon", "swing"),
            "confidence": float(interpretation.get("confidence", 0.5)),
            "supporting_evidence": list(interpretation.get("supporting_evidence", [])),
            "contradicting_evidence": list(
                interpretation.get("contradicting_evidence", [])
            ),
            "evidence": list(interpretation.get("supporting_evidence", [])),
            "decision": direction,
        }


class BullAnalystAgent(BaseAgent):
    agent_id = "bull"
    name = "Bull Analyst"
    config_key = "bull"
    responsibility = "Independent strongest bullish case. Does not read Bear output."

    async def analyze(self, context: ExecutionContext) -> dict[str, Any]:
        # Intentionally exclude bear outputs for independence.
        inputs = {
            "market_intelligence": _payload(context, "market_intelligence"),
            "technical_analysis": _payload(context, "technical_analysis"),
            "trend": _payload(context, "trend"),
            "sentiment": _payload(context, "sentiment"),
            "on_chain": _payload(context, "on_chain"),
            "macro_event": _payload(context, "macro_event"),
            "strategy": _payload(context, "strategy"),
        }
        interpretation = self.llm_json(
            context,
            system=(
                "You are the Bull Analyst. Build the strongest evidence-based LONG case. "
                "Do not invent unavailable alternative data. Return JSON."
            ),
            prompt=json.dumps(inputs, default=str),
        )
        return {
            "thesis": interpretation.get("thesis", ""),
            "supporting_evidence": list(interpretation.get("supporting_evidence", [])),
            "catalysts": list(interpretation.get("catalysts", [])),
            "technical_confirmation": list(
                interpretation.get("technical_confirmation", [])
            ),
            "risks_to_thesis": list(interpretation.get("risks_to_thesis", [])),
            "confidence": float(interpretation.get("confidence", 0.5)),
            "evidence": list(interpretation.get("supporting_evidence", [])),
            "decision": "LONG",
        }


class BearAnalystAgent(BaseAgent):
    agent_id = "bear"
    name = "Bear Analyst"
    config_key = "bear"
    responsibility = "Independent strongest bearish case. Does not read Bull output."

    async def analyze(self, context: ExecutionContext) -> dict[str, Any]:
        # Intentionally exclude bull outputs for independence.
        inputs = {
            "market_intelligence": _payload(context, "market_intelligence"),
            "technical_analysis": _payload(context, "technical_analysis"),
            "trend": _payload(context, "trend"),
            "sentiment": _payload(context, "sentiment"),
            "on_chain": _payload(context, "on_chain"),
            "macro_event": _payload(context, "macro_event"),
            "strategy": _payload(context, "strategy"),
        }
        interpretation = self.llm_json(
            context,
            system=(
                "You are the Bear Analyst. Build the strongest evidence-based SHORT case. "
                "Do not invent unavailable alternative data. Return JSON."
            ),
            prompt=json.dumps(inputs, default=str),
        )
        return {
            "thesis": interpretation.get("thesis", ""),
            "supporting_evidence": list(interpretation.get("supporting_evidence", [])),
            "downside_catalysts": list(interpretation.get("downside_catalysts", [])),
            "technical_weakness": list(interpretation.get("technical_weakness", [])),
            "risks_to_thesis": list(interpretation.get("risks_to_thesis", [])),
            "confidence": float(interpretation.get("confidence", 0.5)),
            "evidence": list(interpretation.get("supporting_evidence", [])),
            "decision": "SHORT",
        }


def _payload(context: ExecutionContext, agent_id: str) -> dict[str, Any] | None:
    message = context.get(agent_id)
    return message.payload if message else None
