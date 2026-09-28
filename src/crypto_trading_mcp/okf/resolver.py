"""Resolve OKF guidelines against system risk config (stricter wins)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from crypto_trading_mcp.okf.loader import load_and_validate_okf
from crypto_trading_mcp.risk.models import GlobalRiskLimits


@dataclass
class ConfigConflict:
    field_name: str
    okf_value: float | int
    system_value: float | int
    effective_value: float | int
    reason_code: str
    note: str


@dataclass
class ResolvedOKFConstraints:
    version: str
    hash: str
    bundle_name: str
    max_risk_per_trade_pct: float
    max_daily_loss_pct: float
    max_drawdown_pct: float
    kelly_base_fraction: float
    kelly_degraded_fraction: float
    brier_threshold: float
    memory_block_confidence: float
    max_trades_per_day: int
    cooldown_bars: int
    kill_switch_file: str
    correlation_enabled: bool
    risk_on_assets: list[str]
    correlated_long_blockers: list[str]
    low_turnover_enabled: bool
    preferred_styles: list[str]
    forbidden_styles: list[str]
    exchange_target: str
    exchange_base_url: str
    exchange_auth_type: str
    max_clock_skew_seconds: int
    rate_limit_units_per_5min: int
    tax_reference: dict[str, Any]
    strategy_ids: list[str]
    ensemble_weights: dict[str, float]
    ml_model: str
    ml_features: list[str]
    ml_optional: bool
    conflicts: list[ConfigConflict] = field(default_factory=list)
    executable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "hash": self.hash,
            "bundle_name": self.bundle_name,
            "max_risk_per_trade_pct": self.max_risk_per_trade_pct,
            "max_daily_loss_pct": self.max_daily_loss_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "kelly_base_fraction": self.kelly_base_fraction,
            "kelly_degraded_fraction": self.kelly_degraded_fraction,
            "brier_threshold": self.brier_threshold,
            "memory_block_confidence": self.memory_block_confidence,
            "max_trades_per_day": self.max_trades_per_day,
            "cooldown_bars": self.cooldown_bars,
            "kill_switch_file": self.kill_switch_file,
            "correlation_enabled": self.correlation_enabled,
            "risk_on_assets": list(self.risk_on_assets),
            "correlated_long_blockers": list(self.correlated_long_blockers),
            "low_turnover_enabled": self.low_turnover_enabled,
            "preferred_styles": list(self.preferred_styles),
            "forbidden_styles": list(self.forbidden_styles),
            "exchange_target": self.exchange_target,
            "exchange_base_url": self.exchange_base_url,
            "exchange_auth_type": self.exchange_auth_type,
            "max_clock_skew_seconds": self.max_clock_skew_seconds,
            "rate_limit_units_per_5min": self.rate_limit_units_per_5min,
            "tax_reference": dict(self.tax_reference),
            "strategy_ids": list(self.strategy_ids),
            "ensemble_weights": dict(self.ensemble_weights),
            "ml_model": self.ml_model,
            "ml_features": list(self.ml_features),
            "ml_optional": self.ml_optional,
            "conflicts": [
                {
                    "field": c.field_name,
                    "okf_value": c.okf_value,
                    "system_value": c.system_value,
                    "effective_value": c.effective_value,
                    "reason_code": c.reason_code,
                    "note": c.note,
                }
                for c in self.conflicts
            ],
            "executable": False,
            "note": "OKF is a guideline specification; deterministic RiskEngine retains authority.",
        }


def _stricter_min(
    field_name: str,
    okf: float | int,
    system: float | int,
    conflicts: list[ConfigConflict],
) -> float | int:
    effective = min(okf, system)
    if okf != system:
        winner = "system" if system < okf else "okf"
        conflicts.append(
            ConfigConflict(
                field_name=field_name,
                okf_value=okf,
                system_value=system,
                effective_value=effective,
                reason_code=f"OKF_SYSTEM_CONFLICT_{field_name.upper()}",
                note=(
                    f"OKF={okf} system={system}; applying stricter ({winner}) "
                    f"value={effective}. No silent overwrite."
                ),
            )
        )
    return effective


class OKFConfigResolver:
    """Load OKF and merge with GlobalRiskLimits using stricter-wins policy."""

    def __init__(self, loaded: dict[str, Any] | None = None) -> None:
        self.loaded = loaded or load_and_validate_okf()
        self.data: dict[str, Any] = self.loaded["data"]

    def resolve(self, system: GlobalRiskLimits) -> ResolvedOKFConstraints:
        data = self.data
        risk = data["risk_management_citadel"]
        pos = risk["position_sizing"]
        breakers = risk["hard_circuit_breakers"]
        corr = risk.get("correlation_filter") or {}
        turnover = risk.get("low_turnover") or {}
        learning = data["self_learning_agent_framework"]
        exch = data["regulatory_and_tax_compliance"]["exchange_api_spec"]
        tax = data["regulatory_and_tax_compliance"]["rules"]
        ml = learning.get("machine_learning") or {}

        conflicts: list[ConfigConflict] = []

        okf_risk = float(pos["max_risk_per_trade_percent"]) / 100.0
        okf_daily = float(breakers["max_daily_loss_percent"]) / 100.0
        okf_dd = float(breakers["max_portfolio_drawdown_percent"]) / 100.0
        okf_trades = int(turnover.get("max_trades_per_day_cap", system.max_trades_per_day))
        okf_cooldown = int(turnover.get("min_cooldown_bars", 0))

        eff_risk = float(
            _stricter_min("max_risk_per_trade_pct", okf_risk, system.max_trade_pct, conflicts)
        )
        eff_daily = float(
            _stricter_min("max_daily_loss_pct", okf_daily, system.max_daily_loss_pct, conflicts)
        )
        eff_dd = float(
            _stricter_min("max_drawdown_pct", okf_dd, system.max_drawdown_pct, conflicts)
        )
        eff_trades = int(
            _stricter_min("max_trades_per_day", okf_trades, system.max_trades_per_day, conflicts)
        )

        # Kelly: OKF quarter-Kelly (0.25); never raise system kelly_fraction.
        okf_kelly = 0.25
        eff_kelly = float(
            _stricter_min("kelly_fraction", okf_kelly, system.kelly_fraction, conflicts)
        )
        # Degraded multiplier: OKF says 0.25x of base when Brier breaches.
        okf_degraded = eff_kelly * 0.25
        # Keep at least as strict as existing learning degraded (0.125 default).
        eff_degraded = min(okf_degraded, 0.125)

        strategies = data.get("trading_models_and_strategies") or []
        strategy_ids = [str(s["model_id"]) for s in strategies if isinstance(s, dict)]
        ensemble: dict[str, float] = {}
        for s in strategies:
            if isinstance(s, dict) and s.get("ensemble_weights"):
                ensemble = {k: float(v) for k, v in s["ensemble_weights"].items()}

        pred_check = learning.get("pre_trade_memory_check") or {}
        brier = learning.get("brier_score_recalibration") or {}

        return ResolvedOKFConstraints(
            version=str(self.loaded["version"]),
            hash=str(self.loaded["hash"]),
            bundle_name=str(self.loaded["bundle_name"]),
            max_risk_per_trade_pct=eff_risk,
            max_daily_loss_pct=eff_daily,
            max_drawdown_pct=eff_dd,
            kelly_base_fraction=eff_kelly,
            kelly_degraded_fraction=eff_degraded,
            brier_threshold=float(brier.get("threshold", 0.25)),
            memory_block_confidence=float(pred_check.get("block_confidence_threshold", 0.80)),
            max_trades_per_day=eff_trades,
            cooldown_bars=max(okf_cooldown, 0),
            kill_switch_file=str(breakers.get("kill_switch_trigger_file", "STOP")),
            correlation_enabled=bool(corr.get("enabled", True)),
            risk_on_assets=[str(a) for a in (corr.get("risk_on_assets") or [])],
            correlated_long_blockers=[
                str(a) for a in (corr.get("correlated_long_blockers") or [])
            ],
            low_turnover_enabled=bool(turnover.get("enabled", True)),
            preferred_styles=[str(s) for s in (turnover.get("preferred_styles") or [])],
            forbidden_styles=[str(s) for s in (turnover.get("forbidden_styles") or [])],
            exchange_target=str(exch.get("target_exchange")),
            exchange_base_url=str(exch.get("base_url")),
            exchange_auth_type=str(exch.get("auth_type")),
            max_clock_skew_seconds=int(exch.get("max_clock_skew_seconds", 5)),
            rate_limit_units_per_5min=int(exch.get("rate_limit_units_per_5min", 10000)),
            tax_reference={
                "jurisdiction": data["regulatory_and_tax_compliance"].get("jurisdiction"),
                "rules": dict(tax),
                "disclaimer": data["regulatory_and_tax_compliance"].get("disclaimer"),
                "is_tax_advice": False,
                "affects_execution": False,
            },
            strategy_ids=strategy_ids,
            ensemble_weights=ensemble,
            ml_model=str(ml.get("model", "XGBoost Classifier")),
            ml_features=[str(f) for f in (ml.get("features") or [])],
            ml_optional=bool(ml.get("optional", True)),
            conflicts=conflicts,
        )

    def apply_to_limits(self, system: GlobalRiskLimits) -> tuple[GlobalRiskLimits, ResolvedOKFConstraints]:
        """Apply OKF stricter bounds that map onto GlobalRiskLimits fields.

        OKF max_risk_per_trade is stop-distance risk enforced via
        risk_per_trade_pct in merge_effective_limits — not a silent overwrite
        of max_trade_pct notional.
        """
        resolved = self.resolve(system)
        updated = system.model_copy(
            update={
                "max_daily_loss_pct": resolved.max_daily_loss_pct,
                "max_drawdown_pct": resolved.max_drawdown_pct,
                "max_trades_per_day": resolved.max_trades_per_day,
                "kelly_fraction": resolved.kelly_base_fraction,
            }
        )
        return updated, resolved
