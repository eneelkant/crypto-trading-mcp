from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from crypto_trading_mcp.config.settings import REPO_ROOT, get_settings
from crypto_trading_mcp.risk.models import GlobalRiskLimits
from crypto_trading_mcp.strategy.schema import StrategyConfig


class KillSwitchState(BaseModel):
    active: bool = False
    reason: str | None = None


class RiskConfig(BaseModel):
    risk: GlobalRiskLimits = Field(default_factory=GlobalRiskLimits)
    circuit_breakers: dict[str, bool] = Field(default_factory=dict)
    kill_switch: KillSwitchState = Field(default_factory=KillSwitchState)
    default_strategy_id: str = "multi_model_po3_vwap"


def load_risk_config(path: Path | None = None) -> RiskConfig:
    path = path or (REPO_ROOT / "config" / "risk.yaml")
    if not path.exists():
        return RiskConfig()
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return RiskConfig.model_validate(data)


class KillSwitch:
    """System-level kill switch. LLMs cannot disable it."""

    def __init__(self, initial: KillSwitchState | None = None) -> None:
        self._state = initial or KillSwitchState()

    def activate(self, reason: str = "operator") -> None:
        self._state = KillSwitchState(active=True, reason=reason)

    def deactivate(self, *, operator_authorized: bool = False) -> None:
        if not operator_authorized:
            raise PermissionError("Kill switch can only be deactivated by an operator")
        self._state = KillSwitchState(active=False, reason=None)

    def status(self) -> KillSwitchState:
        return self._state

    @property
    def active(self) -> bool:
        return self._state.active


def merge_effective_limits(
    global_limits: GlobalRiskLimits,
    strategy: StrategyConfig | None,
) -> dict[str, Any]:
    """Always take the stricter (safer) bound between global and strategy."""
    strat_risk_pct = None
    strat_daily = None
    strat_trades = None
    strat_cooldown = 0
    strat_min_rr = 1.0
    if strategy is not None:
        rm = strategy.risk_management
        # strategy stores percent as 1.0 meaning 1%; global uses fraction 0.02.
        strat_risk_pct = rm.risk_per_trade_percent / 100.0
        strat_daily = rm.circuit_breakers.max_daily_loss_percent / 100.0
        strat_trades = rm.circuit_breakers.max_trades_per_day
        strat_cooldown = rm.circuit_breakers.cooldown_bars_between_trades
        strat_min_rr = rm.min_risk_reward_ratio

    risk_per_trade = (
        min(global_limits.max_trade_pct, strat_risk_pct)
        if strat_risk_pct is not None
        else global_limits.max_trade_pct
    )
    max_daily = (
        min(global_limits.max_daily_loss_pct, strat_daily)
        if strat_daily is not None
        else global_limits.max_daily_loss_pct
    )
    max_trades = (
        min(global_limits.max_trades_per_day, strat_trades)
        if strat_trades is not None
        else global_limits.max_trades_per_day
    )
    return {
        "risk_per_trade_pct": risk_per_trade,
        "max_daily_loss_pct": max_daily,
        "max_drawdown_pct": global_limits.max_drawdown_pct,
        "max_trades_per_day": max_trades,
        "cooldown_bars": strat_cooldown,
        "min_risk_reward": strat_min_rr,
        "max_position_pct": global_limits.max_position_pct,
        "max_trade_pct": global_limits.max_trade_pct,
        "max_portfolio_exposure_pct": global_limits.max_portfolio_exposure_pct,
        "max_slippage_pct": global_limits.max_slippage_pct,
        "max_leverage": global_limits.max_leverage,
        "require_stop_loss": global_limits.require_stop_loss,
        "min_liquidity_usd": global_limits.min_liquidity_usd,
        "min_confidence": global_limits.min_confidence,
        "allowed_pairs": list(global_limits.allowed_pairs),
    }


def normalize_symbol(symbol: str) -> str:
    return symbol.replace("-", "/").upper()


def pair_allowed(symbol: str, allowed: list[str]) -> bool:
    if not allowed:
        return True
    candidates = {
        symbol.upper(),
        symbol.replace("-", "/").upper(),
        symbol.replace("/", "").upper(),
        symbol.replace("-", "").upper(),
        symbol.replace("/", "-").upper(),
    }
    allowed_norm = {a.upper() for a in allowed} | {
        a.replace("-", "/").upper() for a in allowed
    } | {a.replace("/", "").upper() for a in allowed}
    return bool(candidates & allowed_norm)
