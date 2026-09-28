from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from crypto_trading_mcp.live.stages import TradingStage


class LiveGateReason(str, Enum):
    LIVE_GATE_OK = "LIVE_GATE_OK"
    LIVE_GATE_MODE_BLOCKED = "LIVE_GATE_MODE_BLOCKED"
    LIVE_GATE_FLAG_BLOCKED = "LIVE_GATE_FLAG_BLOCKED"
    LIVE_GATE_STAGE_NOT_ALLOWED = "LIVE_GATE_STAGE_NOT_ALLOWED"
    LIVE_GATE_CREDENTIAL_FAILURE = "LIVE_GATE_CREDENTIAL_FAILURE"
    LIVE_GATE_PERMISSION_FAILURE = "LIVE_GATE_PERMISSION_FAILURE"
    LIVE_GATE_MARKET_DATA_STALE = "LIVE_GATE_MARKET_DATA_STALE"
    LIVE_GATE_EXCHANGE_UNAVAILABLE = "LIVE_GATE_EXCHANGE_UNAVAILABLE"
    LIVE_GATE_RISK_ENGINE_FAILURE = "LIVE_GATE_RISK_ENGINE_FAILURE"
    LIVE_GATE_RECONCILIATION_FAILURE = "LIVE_GATE_RECONCILIATION_FAILURE"
    LIVE_GATE_KILL_SWITCH = "LIVE_GATE_KILL_SWITCH"
    LIVE_GATE_DAILY_LOSS = "LIVE_GATE_DAILY_LOSS"
    LIVE_GATE_DRAWDOWN = "LIVE_GATE_DRAWDOWN"
    LIVE_GATE_POSITION_LIMIT = "LIVE_GATE_POSITION_LIMIT"
    LIVE_GATE_EXPOSURE_LIMIT = "LIVE_GATE_EXPOSURE_LIMIT"
    LIVE_GATE_DUPLICATE_ORDER = "LIVE_GATE_DUPLICATE_ORDER"
    LIVE_GATE_CLOCK_SKEW = "LIVE_GATE_CLOCK_SKEW"
    LIVE_GATE_INVALID_ORDER = "LIVE_GATE_INVALID_ORDER"
    LIVE_GATE_EXCHANGE_NOT_ALLOWLISTED = "LIVE_GATE_EXCHANGE_NOT_ALLOWLISTED"
    LIVE_GATE_INSTRUMENT_NOT_ALLOWLISTED = "LIVE_GATE_INSTRUMENT_NOT_ALLOWLISTED"
    LIVE_GATE_CLOUD_PAPER_ISOLATION = "LIVE_GATE_CLOUD_PAPER_ISOLATION"


class LiveExecutionPolicy(BaseModel):
    """Declarative policy inputs for the live trading gate (fail-closed)."""

    trading_mode: str = "paper"
    live_trading_enabled: bool = False
    stage: TradingStage = TradingStage.STAGE_1_LOCAL_PAPER
    kill_switch_active: bool = False
    exchange_allowlist: list[str] = Field(default_factory=lambda: ["paper", "mock"])
    instrument_allowlist: list[str] = Field(default_factory=list)
    credentials_healthy: bool = False
    credentials_allow_trading: bool = False
    market_data_fresh: bool = False
    exchange_healthy: bool = False
    risk_engine_healthy: bool = True
    reconciliation_ok: bool = False
    clock_skew_ok: bool = True
    idempotency_ok: bool = True
    order_valid: bool = False
    daily_loss_ok: bool = True
    drawdown_ok: bool = True
    exposure_ok: bool = True
    position_ok: bool = True
    duplicate: bool = False
    cloud_paper_isolated: bool = False
    exchange: str = "paper"
    symbol: str = ""

    def mode_allows_live(self) -> bool:
        return self.trading_mode == "live" and self.live_trading_enabled
