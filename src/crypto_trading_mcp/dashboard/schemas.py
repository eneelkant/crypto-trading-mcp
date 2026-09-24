from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    TRADING_MODE: str = "PAPER"
    LIVE_TRADING_ENABLED: bool = False
    uptime_seconds: float = 0.0


class KillSwitchRequest(BaseModel):
    reason: str = "dashboard_emergency_stop"


class ActionResponse(BaseModel):
    ok: bool = True
    detail: dict[str, Any] = Field(default_factory=dict)
    TRADING_MODE: str = "PAPER"
    LIVE_TRADING_ENABLED: bool = False
