from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class RiskReasonCode(StrEnum):
    RISK_OK = "RISK_OK"
    POSITION_LIMIT_EXCEEDED = "POSITION_LIMIT_EXCEEDED"
    TRADE_SIZE_LIMIT_EXCEEDED = "TRADE_SIZE_LIMIT_EXCEEDED"
    EXPOSURE_LIMIT_EXCEEDED = "EXPOSURE_LIMIT_EXCEEDED"
    DAILY_LOSS_LIMIT = "DAILY_LOSS_LIMIT"
    DRAWDOWN_LIMIT = "DRAWDOWN_LIMIT"
    TRADE_COUNT_LIMIT = "TRADE_COUNT_LIMIT"
    COOLDOWN_ACTIVE = "COOLDOWN_ACTIVE"
    SLIPPAGE_LIMIT = "SLIPPAGE_LIMIT"
    LEVERAGE_LIMIT = "LEVERAGE_LIMIT"
    PAIR_NOT_ALLOWED = "PAIR_NOT_ALLOWED"
    STALE_MARKET_DATA = "STALE_MARKET_DATA"
    STOP_LOSS_REQUIRED = "STOP_LOSS_REQUIRED"
    INVALID_STOP = "INVALID_STOP"
    RISK_REWARD_TOO_LOW = "RISK_REWARD_TOO_LOW"
    KILL_SWITCH_ACTIVE = "KILL_SWITCH_ACTIVE"
    INSUFFICIENT_LIQUIDITY = "INSUFFICIENT_LIQUIDITY"
    INVALID_TRADE = "INVALID_TRADE"
    STRATEGY_DISABLED = "STRATEGY_DISABLED"
    STRATEGY_DATA_UNAVAILABLE = "STRATEGY_DATA_UNAVAILABLE"
    TRADING_HALTED = "TRADING_HALTED"
    INSUFFICIENT_CASH = "INSUFFICIENT_CASH"
    INSUFFICIENT_CONFIDENCE = "INSUFFICIENT_CONFIDENCE"
    NO_VALID_MODEL = "NO_VALID_MODEL"


class GlobalRiskLimits(BaseModel):
    max_position_pct: float = 0.10
    max_trade_pct: float = 0.02
    max_portfolio_exposure_pct: float = 0.50
    max_daily_loss_pct: float = 0.03
    max_drawdown_pct: float = 0.10
    max_trades_per_day: int = 20
    max_slippage_pct: float = 0.005
    max_leverage: float = 1.0
    require_stop_loss: bool = True
    min_liquidity_usd: float = 100_000
    min_confidence: float = 0.55
    allowed_pairs: list[str] = Field(default_factory=list)


class EffectiveRiskLimits(BaseModel):
    """Stricter of global and strategy constraints."""

    risk_per_trade_pct: float
    max_daily_loss_pct: float
    max_drawdown_pct: float
    max_trades_per_day: int
    cooldown_bars: int
    min_risk_reward: float
    max_position_pct: float
    max_trade_pct: float
    max_portfolio_exposure_pct: float
    max_slippage_pct: float
    max_leverage: float
    require_stop_loss: bool
    min_liquidity_usd: float
    min_confidence: float
    allowed_pairs: list[str]


class TradeProposal(BaseModel):
    symbol: str
    side: str
    quantity: float
    notional: float
    entry_price: float
    stop_loss: float | None = None
    take_profit: float | None = None
    current_price: float
    estimated_fees: float = 0.0
    estimated_slippage_pct: float = 0.0
    leverage: float = 1.0
    confidence: float = 0.0
    model_ids: list[str] = Field(default_factory=list)
    strategy_id: str | None = None
    strategy_version: str | None = None
    liquidity_usd: float | None = None
    market_data_stale: bool = False
    bars_since_last_trade: int | None = None


class PortfolioRiskSnapshot(BaseModel):
    equity: float
    available_cash: float
    positions_exposure: float
    daily_pnl: float
    drawdown_pct: float
    trades_today: int
    kill_switch_active: bool = False
    trading_halted: bool = False
    halt_reasons: list[str] = Field(default_factory=list)


class RiskDecision(BaseModel):
    approved: bool
    reason_codes: list[RiskReasonCode]
    warnings: list[str] = Field(default_factory=list)
    max_allowed_quantity: float = 0.0
    max_allowed_notional: float = 0.0
    risk_per_trade: float = 0.0
    portfolio_exposure: float = 0.0
    daily_loss: float = 0.0
    drawdown: float = 0.0
    effective_limits: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
