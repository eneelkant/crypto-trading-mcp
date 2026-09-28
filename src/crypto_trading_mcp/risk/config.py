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
    *,
    okf_constraints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Always take the stricter (safer) bound between global, strategy, and OKF."""
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
    max_drawdown = global_limits.max_drawdown_pct
    kelly = global_limits.kelly_fraction
    cooldown = strat_cooldown
    conflicts: list[dict[str, Any]] = []

    if okf_constraints:
        okf_risk = float(okf_constraints.get("max_risk_per_trade_pct", risk_per_trade))
        okf_daily = float(okf_constraints.get("max_daily_loss_pct", max_daily))
        okf_dd = float(okf_constraints.get("max_drawdown_pct", max_drawdown))
        okf_trades = int(okf_constraints.get("max_trades_per_day", max_trades))
        okf_kelly = float(okf_constraints.get("kelly_base_fraction", kelly))
        okf_cooldown = int(okf_constraints.get("cooldown_bars", 0))

        def _min_field(name: str, current: float | int, okf_val: float | int) -> float | int:
            effective = min(current, okf_val)
            if current != okf_val:
                conflicts.append(
                    {
                        "field": name,
                        "system_or_strategy": current,
                        "okf": okf_val,
                        "effective": effective,
                        "reason_code": f"OKF_SYSTEM_CONFLICT_{name.upper()}",
                    }
                )
            return effective

        risk_per_trade = float(_min_field("max_risk_per_trade_pct", risk_per_trade, okf_risk))
        max_daily = float(_min_field("max_daily_loss_pct", max_daily, okf_daily))
        max_drawdown = float(_min_field("max_drawdown_pct", max_drawdown, okf_dd))
        max_trades = int(_min_field("max_trades_per_day", max_trades, okf_trades))
        kelly = float(_min_field("kelly_fraction", kelly, okf_kelly))
        cooldown = max(cooldown, okf_cooldown)

    min_rr = max(global_limits.min_risk_reward, strat_min_rr)
    return {
        "risk_per_trade_pct": risk_per_trade,
        "max_daily_loss_pct": max_daily,
        "max_drawdown_pct": max_drawdown,
        "max_trades_per_day": max_trades,
        "cooldown_bars": cooldown,
        "min_risk_reward": min_rr,
        "max_position_pct": global_limits.max_position_pct,
        "max_trade_pct": global_limits.max_trade_pct,
        "max_portfolio_exposure_pct": global_limits.max_portfolio_exposure_pct,
        "max_slippage_pct": global_limits.max_slippage_pct,
        "max_leverage": global_limits.max_leverage,
        "require_stop_loss": global_limits.require_stop_loss,
        "min_liquidity_usd": global_limits.min_liquidity_usd,
        "min_confidence": global_limits.min_confidence,
        "kelly_fraction": kelly,
        "max_consecutive_api_failures": global_limits.max_consecutive_api_failures,
        "allowed_pairs": list(global_limits.allowed_pairs),
        "okf_conflicts": conflicts,
    }


def normalize_symbol(symbol: str) -> str:
    return symbol.replace("-", "/").upper()


def pair_allowed(symbol: str, allowed: list[str]) -> bool:
    if not allowed:
        return True
    sym = symbol.upper()
    candidates = {
        sym,
        sym.replace("-", "/"),
        sym.replace("/", ""),
        sym.replace("-", ""),
        sym.replace("/", "-"),
    }
    allowed_norm = {a.upper() for a in allowed}
    if candidates & allowed_norm:
        return True
    # Prefix wildcards e.g. PREDICT/*
    for pattern in allowed_norm:
        if pattern.endswith("/*") and sym.startswith(pattern[:-1]):
            return True
    # Also compare slash-normalized forms
    allowed_slash = {a.replace("-", "/").upper() for a in allowed}
    return bool(candidates & allowed_slash)
