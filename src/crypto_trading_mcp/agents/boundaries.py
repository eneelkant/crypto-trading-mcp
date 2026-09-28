from __future__ import annotations

from typing import Any


# Target 16-agent / subsystem map (Phase 1 architecture).
AGENT_BOUNDARIES: dict[str, dict[str, Any]] = {
    "market_intelligence": {
        "kind": "llm_agent",
        "may": ["interpret", "summarize", "compare_signals"],
        "may_not": ["override_risk", "submit_orders", "change_credentials", "change_mode"],
        "influences_trade": "indirect",
    },
    "technical_analysis": {
        "kind": "llm_agent",
        "may": ["interpret", "summarize"],
        "may_not": ["override_risk", "submit_orders"],
        "influences_trade": "indirect",
    },
    "trend": {
        "kind": "llm_agent",
        "may": ["interpret", "hypothesize"],
        "may_not": ["override_risk", "submit_orders"],
        "influences_trade": "indirect",
    },
    "sentiment": {
        "kind": "llm_agent",
        "may": ["summarize_untrusted_context"],
        "may_not": ["fabricate_missing_data", "override_risk", "submit_orders"],
        "influences_trade": "indirect",
    },
    "on_chain": {
        "kind": "llm_agent",
        "may": ["summarize_untrusted_context"],
        "may_not": ["fabricate_missing_data", "override_risk", "submit_orders"],
        "influences_trade": "indirect",
    },
    "macro_event": {
        "kind": "llm_agent",
        "may": ["summarize_untrusted_context"],
        "may_not": ["fabricate_missing_data", "override_risk", "submit_orders"],
        "influences_trade": "indirect",
    },
    "strategy": {
        "kind": "llm_agent",
        "may": ["propose_direction", "structure_hypothesis"],
        "may_not": ["override_risk", "submit_orders", "change_limits"],
        "influences_trade": "proposal_input",
    },
    "bull": {
        "kind": "llm_agent",
        "may": ["argue_bull_case"],
        "may_not": ["override_risk", "submit_orders"],
        "influences_trade": "consensus_input",
    },
    "bear": {
        "kind": "llm_agent",
        "may": ["argue_bear_case"],
        "may_not": ["override_risk", "submit_orders"],
        "influences_trade": "consensus_input",
    },
    "consensus": {
        "kind": "llm_agent",
        "may": ["emit_structured_decision"],
        "may_not": ["override_risk", "submit_orders", "disable_kill_switch"],
        "influences_trade": "signal",
    },
    "risk_manager": {
        "kind": "deterministic",
        "may": ["approve_or_reject", "enforce_limits"],
        "may_not": ["be_overridden_by_llm"],
        "influences_trade": "hard_gate",
        "implementation": "RiskEngine",
    },
    "portfolio_manager": {
        "kind": "deterministic",
        "may": ["track_exposure", "cash_constraints"],
        "may_not": ["bypass_risk"],
        "influences_trade": "constraints",
        "implementation": "PortfolioManager",
    },
    "trade_planner": {
        "kind": "deterministic",
        "may": ["size_and_structure_plan"],
        "may_not": ["raise_hard_limits"],
        "influences_trade": "plan",
        "implementation": "TradePlan",
    },
    "execution": {
        "kind": "deterministic",
        "may": ["submit_via_adapter_after_gates"],
        "may_not": ["skip_live_gate", "skip_risk"],
        "influences_trade": "orders",
        "implementation": "PaperTradingEngine / ExchangeAdapter",
    },
    "reflection_learning": {
        "kind": "deterministic_plus_llm",
        "may": ["post_mortem", "retrieve_memory"],
        "may_not": ["auto_deploy_live", "disable_safety"],
        "influences_trade": "post_trade",
        "implementation": "LearningEngine",
    },
    "performance_judge": {
        "kind": "deterministic",
        "may": ["score_metrics", "calibration"],
        "may_not": ["place_orders"],
        "influences_trade": "evaluation_only",
        "implementation": "performance.metrics + learning calibration",
    },
}


LLM_FORBIDDEN = [
    "override deterministic risk",
    "override position limits",
    "override daily loss",
    "override drawdown",
    "override kill switch",
    "bypass order validation",
    "submit arbitrary exchange requests",
    "change credentials",
    "change trading mode",
    "disable safety gates",
]


def continuous_loop_policy() -> dict[str, Any]:
    """AutonomousPaperLoop uses deterministic fallback when full debate unavailable."""
    return {
        "full_debate_required": False,
        "fallback": "deterministic_paper_path",
        "fabrication_forbidden": True,
        "risk_engine_required": True,
        "live_execution": "DISABLED",
    }


def public_boundaries() -> dict[str, Any]:
    return {
        "agents": AGENT_BOUNDARIES,
        "llm_forbidden": LLM_FORBIDDEN,
        "continuous_loop": continuous_loop_policy(),
        "registered_llm_agents": 10,
        "deterministic_subsystems": 6,
        "target_total": 16,
    }
