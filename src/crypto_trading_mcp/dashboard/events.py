from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class EventSeverity(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class EventType(StrEnum):
    AGENT_STARTED = "AgentStarted"
    AGENT_COMPLETED = "AgentCompleted"
    AGENT_FAILED = "AgentFailed"
    AGENT_MESSAGE = "AgentMessage"
    MARKET_DATA_UPDATED = "MarketDataUpdated"
    TECHNICAL_ANALYSIS_UPDATED = "TechnicalAnalysisUpdated"
    STRATEGY_SIGNAL_GENERATED = "StrategySignalGenerated"
    BULL_ANALYSIS = "BullAnalysis"
    BEAR_ANALYSIS = "BearAnalysis"
    CONSENSUS_GENERATED = "ConsensusGenerated"
    RISK_CHECK_STARTED = "RiskCheckStarted"
    RISK_APPROVED = "RiskApproved"
    RISK_REJECTED = "RiskRejected"
    TRADE_PLAN_CREATED = "TradePlanCreated"
    ORDER_CREATED = "OrderCreated"
    ORDER_VALIDATED = "OrderValidated"
    ORDER_SUBMITTED = "OrderSubmitted"
    ORDER_OPENED = "OrderOpened"
    ORDER_PARTIALLY_FILLED = "OrderPartiallyFilled"
    ORDER_FILLED = "OrderFilled"
    ORDER_CANCELLED = "OrderCancelled"
    ORDER_EXPIRED = "OrderExpired"
    ORDER_REJECTED = "OrderRejected"
    POSITION_OPENED = "PositionOpened"
    POSITION_UPDATED = "PositionUpdated"
    POSITION_CLOSED = "PositionClosed"
    PORTFOLIO_UPDATED = "PortfolioUpdated"
    PNL_UPDATED = "PnLUpdated"
    BACKTEST_STARTED = "BacktestStarted"
    BACKTEST_PROGRESS = "BacktestProgress"
    BACKTEST_COMPLETED = "BacktestCompleted"
    WALK_FORWARD_STARTED = "WalkForwardStarted"
    WALK_FORWARD_PROGRESS = "WalkForwardProgress"
    WALK_FORWARD_COMPLETED = "WalkForwardCompleted"
    SENSITIVITY_STARTED = "SensitivityStarted"
    SENSITIVITY_COMPLETED = "SensitivityCompleted"
    MONTE_CARLO_STARTED = "MonteCarloStarted"
    MONTE_CARLO_COMPLETED = "MonteCarloCompleted"
    BENCHMARK_STARTED = "BenchmarkStarted"
    BENCHMARK_COMPLETED = "BenchmarkCompleted"
    PREDICTION_BACKTEST_STARTED = "PredictionBacktestStarted"
    PREDICTION_BACKTEST_COMPLETED = "PredictionBacktestCompleted"
    MCP_TOOL_CALLED = "MCPToolCalled"
    LLM_REQUEST_STARTED = "LLMRequestStarted"
    LLM_REQUEST_COMPLETED = "LLMRequestCompleted"
    LLM_PROVIDER_UNAVAILABLE = "LLMProviderUnavailable"
    EXCHANGE_CONNECTED = "ExchangeConnected"
    EXCHANGE_DISCONNECTED = "ExchangeDisconnected"
    CIRCUIT_BREAKER_TRIGGERED = "CircuitBreakerTriggered"
    KILL_SWITCH_ACTIVATED = "KillSwitchActivated"
    SYSTEM_HEALTH_CHANGED = "SystemHealthChanged"
    DASHBOARD_STARTED = "DashboardStarted"
    LEARNING_STARTED = "LearningStarted"
    TRADE_POSTMORTEM_STARTED = "TradePostmortemStarted"
    TRADE_POSTMORTEM_COMPLETED = "TradePostmortemCompleted"
    TRADE_CLASSIFIED = "TradeClassified"
    FAILURE_MEMORY_UPDATED = "FailureMemoryUpdated"
    SUCCESS_MEMORY_UPDATED = "SuccessMemoryUpdated"
    MEMORY_RETRIEVAL_COMPLETED = "MemoryRetrievalCompleted"
    LEARNING_CONTEXT_READY = "LearningContextReady"
    BRIER_UPDATED = "BrierUpdated"
    CALIBRATION_UPDATED = "CalibrationUpdated"
    KELLY_ADAPTED = "KellyAdapted"
    REGIME_DETECTED = "RegimeDetected"
    DRIFT_DETECTED = "DriftDetected"
    REFLECTION_STARTED = "ReflectionStarted"
    REFLECTION_COMPLETED = "ReflectionCompleted"
    RETRAINING_STARTED = "RetrainingStarted"
    RETRAINING_COMPLETED = "RetrainingCompleted"
    MODEL_VERSION_CREATED = "ModelVersionCreated"
    CHALLENGER_CREATED = "ChallengerCreated"
    CHALLENGER_VALIDATED = "ChallengerValidated"
    CHALLENGER_REJECTED = "ChallengerRejected"
    CHAMPION_UPDATED = "ChampionUpdated"
    LEARNING_PROPOSAL_CREATED = "LearningProposalCreated"
    LEARNING_PROPOSAL_ACCEPTED = "LearningProposalAccepted"
    LEARNING_PROPOSAL_REJECTED = "LearningProposalRejected"
    LEARNING_ROLLBACK = "LearningRollback"


SECRET_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "api_secret",
        "secret",
        "password",
        "token",
        "authorization",
        "private_key",
        "wallet",
        "prompt",
        "system_prompt",
        "chain_of_thought",
        "reasoning",
        "hidden_reasoning",
    }
)


def sanitize_payload(payload: Any) -> Any:
    """Strip secrets and private reasoning from event payloads."""
    if isinstance(payload, dict):
        out: dict[str, Any] = {}
        for key, value in payload.items():
            lk = str(key).lower()
            if lk in {
                "chain_of_thought",
                "hidden_reasoning",
                "raw_prompt",
                "system_prompt",
                "reasoning",
                "prompt",
            } or "chain_of_thought" in lk:
                continue
            if lk in SECRET_KEYS or any(s in lk for s in ("secret", "credential", "private_key", "api_key")):
                out[key] = "[REDACTED]"
                continue
            out[key] = sanitize_payload(value)
        return out
    if isinstance(payload, list):
        return [sanitize_payload(v) for v in payload]
    return payload


class DashboardEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    event_type: EventType | str
    run_id: str | None = None
    agent_id: str | None = None
    symbol: str | None = None
    trading_mode: str = "paper"
    payload: dict[str, Any] = Field(default_factory=dict)
    severity: EventSeverity = EventSeverity.INFO

    def model_post_init(self, __context: Any) -> None:
        self.payload = sanitize_payload(self.payload) if isinstance(self.payload, dict) else {}

    def to_dict(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        data["payload"] = sanitize_payload(data.get("payload") or {})
        return data
