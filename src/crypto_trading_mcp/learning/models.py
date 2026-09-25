from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class TradeOutcome(StrEnum):
    WIN = "WIN"
    LOSS = "LOSS"
    BREAKEVEN = "BREAKEVEN"


class FailureCategory(StrEnum):
    BAD_PREDICTION = "BAD_PREDICTION"
    HIGH_SLIPPAGE = "HIGH_SLIPPAGE"
    MARKET_REGIME_SHIFT = "MARKET_REGIME_SHIFT"
    BAD_TIMING_OR_EXECUTION = "BAD_TIMING_OR_EXECUTION"
    EXTERNAL_SHOCK = "EXTERNAL_SHOCK"
    NORMAL_VARIANCE = "NORMAL_VARIANCE"
    UNKNOWN = "UNKNOWN"


class SuccessCategory(StrEnum):
    GOOD_PREDICTION = "GOOD_PREDICTION"
    GOOD_EXECUTION = "GOOD_EXECUTION"
    REGIME_ALIGNED = "REGIME_ALIGNED"
    UNKNOWN = "UNKNOWN"


class MarketRegime(StrEnum):
    TRENDING_UP = "TRENDING_UP"
    TRENDING_DOWN = "TRENDING_DOWN"
    RANGING = "RANGING"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    BREAKOUT = "BREAKOUT"
    MEAN_REVERTING = "MEAN_REVERTING"
    UNKNOWN = "UNKNOWN"


class ProposalStatus(StrEnum):
    PROPOSED = "PROPOSED"
    BACKTESTING = "BACKTESTING"
    VALIDATION = "VALIDATION"
    OOS_TESTING = "OOS_TESTING"
    PAPER_TESTING = "PAPER_TESTING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    ROLLED_BACK = "ROLLED_BACK"


class ChallengerDecision(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class DriftType(StrEnum):
    MODEL_DRIFT = "MODEL_DRIFT"
    FEATURE_DRIFT = "FEATURE_DRIFT"
    PERFORMANCE_DRIFT = "PERFORMANCE_DRIFT"
    CALIBRATION_DRIFT = "CALIBRATION_DRIFT"


class TradeLearningRecord(BaseModel):
    trade_id: str
    strategy_id: str | None = None
    strategy_version: str | None = None
    model_id: str | None = None
    model_version: str | None = None
    config_hash: str | None = None
    backtest_reference: str | None = None
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())

    symbol: str
    timeframe: str | None = None
    market_regime: MarketRegime = MarketRegime.UNKNOWN
    features: dict[str, float | None] = Field(default_factory=dict)

    side: str | None = None
    entry_price: float | None = None
    exit_price: float | None = None
    quantity: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    holding_period: float | None = None
    gross_pnl: float = 0.0
    fees: float = 0.0
    slippage: float = 0.0
    net_pnl: float = 0.0
    mae: float | None = None
    mfe: float | None = None

    agent_predictions: dict[str, Any] = Field(default_factory=dict)
    consensus_confidence: float | None = None
    predicted_probability: float | None = None
    market_probability: float | None = None
    edge: float | None = None
    kelly_value: float | None = None
    kelly_multiplier: float = 1.0
    position_sizing_multiplier: float = 1.0
    risk_decision: str | None = None
    execution_quality: str | None = None

    outcome: TradeOutcome = TradeOutcome.BREAKEVEN
    failure_categories: list[FailureCategory] = Field(default_factory=list)
    success_categories: list[SuccessCategory] = Field(default_factory=list)
    lesson: str | None = None
    memory_id: str = Field(default_factory=lambda: f"MEM-{uuid4().hex[:12]}")
    similar_case_ids: list[str] = Field(default_factory=list)
    brier_score: float | None = None
    drift_state: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class LearningContext(BaseModel):
    similar_case_count: int = 0
    similar_failure_count: int = 0
    similar_success_count: int = 0
    common_failure_patterns: list[str] = Field(default_factory=list)
    common_success_patterns: list[str] = Field(default_factory=list)
    average_outcome: float | None = None
    historical_confidence: float | None = None
    recommended_caution: bool = False
    regime: MarketRegime = MarketRegime.UNKNOWN
    brier_status: str = "UNKNOWN"
    drift_status: str = "OK"
    cases: list[dict[str, Any]] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class LearningProposal(BaseModel):
    proposal_id: str = Field(default_factory=lambda: f"LP-{uuid4().hex[:10]}")
    parent_version: str | None = None
    candidate_version: str | None = None
    reason: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    data_window: str | None = None
    backtest_reference: str | None = None
    walk_forward_reference: str | None = None
    oos_reference: str | None = None
    risk_analysis: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    status: ProposalStatus = ProposalStatus.PROPOSED
    warning_flags: list[str] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ModelVersion(BaseModel):
    model_version: str
    training_dataset_hash: str
    feature_hash: str
    configuration_hash: str
    training_date: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    seed: int = 42
    training_window: str | None = None
    validation_window: str | None = None
    oos_window: str | None = None
    brier_score: float | None = None
    log_loss: float | None = None
    accuracy: float | None = None
    precision: float | None = None
    recall: float | None = None
    calibration: float | None = None
    drawdown_impact: float | None = None
    strategy_impact: float | None = None
    decision: ChallengerDecision | None = None
    decision_reasons: list[str] = Field(default_factory=list)
    champion: bool = False

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ReflectionRecord(BaseModel):
    reflection_id: str = Field(default_factory=lambda: f"REF-{uuid4().hex[:10]}")
    trade_id: str | None = None
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    what_happened: str
    what_was_expected: str
    what_actually_happened: str
    contributors: list[str] = Field(default_factory=list)
    prediction_correct: bool | None = None
    execution_correct: bool | None = None
    regime_correct: bool | None = None
    confidence_calibrated: bool | None = None
    pattern_to_remember: str | None = None
    what_should_be_tested: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
