from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from crypto_trading_mcp.config.settings import REPO_ROOT, get_settings


class ComplianceConfig(BaseModel):
    enabled: bool = True
    blocked_strategies: list[str] = Field(default_factory=list)
    blocked_asset_classes: list[str] = Field(default_factory=list)
    require_paper_mode: bool = True
    max_turnover_usd_per_day: float = 1_000_000
    allow_prediction_markets: bool = True
    allow_futures: bool = True


class TaxSimulationConfig(BaseModel):
    enabled: bool = True
    disclaimer: str = "Configurable simulation model. Not tax advice."
    vda_enabled: bool = True
    vda_rate: float = 0.30
    vda_asset_classes: list[str] = Field(default_factory=lambda: ["CRYPTO"])
    tds_enabled: bool = True
    tds_rate: float = 0.01
    tds_asset_classes: list[str] = Field(default_factory=lambda: ["CRYPTO"])
    loss_setoff_allowed: bool = False
    equity_transaction_tax: float = 0.001
    commodity_transaction_tax: float = 0.0005
    default_transaction_tax: float = 0.0


def load_compliance_config(path: Path | None = None) -> tuple[ComplianceConfig, TaxSimulationConfig]:
    path = path or (REPO_ROOT / "config" / "compliance.yaml")
    if not path.exists():
        return ComplianceConfig(), TaxSimulationConfig()
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    c = data.get("compliance") or {}
    t = data.get("tax_simulation") or {}
    vda = t.get("vda") or {}
    tds = t.get("tds") or {}
    tx = t.get("transaction_tax") or {}
    compliance = ComplianceConfig(
        enabled=bool(c.get("enabled", True)),
        blocked_strategies=list(c.get("blocked_strategies") or []),
        blocked_asset_classes=list(c.get("blocked_asset_classes") or []),
        require_paper_mode=bool(c.get("require_paper_mode", True)),
        max_turnover_usd_per_day=float(c.get("max_turnover_usd_per_day", 1_000_000)),
        allow_prediction_markets=bool(c.get("allow_prediction_markets", True)),
        allow_futures=bool(c.get("allow_futures", True)),
    )
    tax = TaxSimulationConfig(
        enabled=bool(t.get("enabled", True)),
        disclaimer=str(t.get("disclaimer") or TaxSimulationConfig().disclaimer),
        vda_enabled=bool(vda.get("enabled", True)),
        vda_rate=float(vda.get("rate", 0.30)),
        vda_asset_classes=list(vda.get("apply_to_asset_classes") or ["CRYPTO"]),
        tds_enabled=bool(tds.get("enabled", True)),
        tds_rate=float(tds.get("rate", 0.01)),
        tds_asset_classes=list(tds.get("apply_to_asset_classes") or ["CRYPTO"]),
        loss_setoff_allowed=bool(t.get("loss_setoff_allowed", False)),
        equity_transaction_tax=float(tx.get("equity_rate", 0.001)),
        commodity_transaction_tax=float(tx.get("commodity_rate", 0.0005)),
        default_transaction_tax=float(tx.get("default_rate", 0.0)),
    )
    return compliance, tax


class ComplianceDecision(BaseModel):
    approved: bool
    reason_codes: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class CompliancePolicy:
    """Pre-trade compliance gate. Runs before Risk Engine / PaperExchange."""

    def __init__(self, config: ComplianceConfig | None = None) -> None:
        self.config = config or load_compliance_config()[0]

    def evaluate(
        self,
        *,
        strategy_id: str | None,
        asset_class: str,
        notional: float,
        daily_turnover: float,
    ) -> ComplianceDecision:
        reasons: list[str] = []
        settings = get_settings()
        if self.config.require_paper_mode:
            if settings.trading_mode != "paper" or settings.live_trading_enabled:
                reasons.append("COMPLIANCE_BLOCKED")
                reasons.append("PAPER_MODE_REQUIRED")
        if not self.config.enabled:
            return ComplianceDecision(approved=True, reason_codes=["COMPLIANCE_DISABLED"])
        if strategy_id and strategy_id in self.config.blocked_strategies:
            reasons.append("COMPLIANCE_BLOCKED")
            reasons.append("STRATEGY_BLOCKED")
        if asset_class in self.config.blocked_asset_classes:
            reasons.append("COMPLIANCE_BLOCKED")
            reasons.append("ASSET_CLASS_BLOCKED")
        if asset_class == "PREDICTION_CONTRACT" and not self.config.allow_prediction_markets:
            reasons.append("COMPLIANCE_BLOCKED")
            reasons.append("PREDICTION_MARKETS_DISABLED")
        if asset_class == "FUTURE" and not self.config.allow_futures:
            reasons.append("COMPLIANCE_BLOCKED")
            reasons.append("FUTURES_DISABLED")
        if daily_turnover + notional > self.config.max_turnover_usd_per_day:
            reasons.append("COMPLIANCE_BLOCKED")
            reasons.append("TURNOVER_LIMIT")
        return ComplianceDecision(approved=not reasons, reason_codes=reasons or ["COMPLIANCE_OK"])


class TaxSimulator:
    """Configurable tax/friction accounting. Not legal advice."""

    def __init__(self, config: TaxSimulationConfig | None = None) -> None:
        self.config = config or load_compliance_config()[1]

    def apply(
        self,
        *,
        gross_pnl: float,
        fees: float,
        notional: float,
        asset_class: str,
    ) -> dict[str, Any]:
        if not self.config.enabled:
            return {
                "gross_pnl": gross_pnl,
                "fees": fees,
                "transaction_tax": 0.0,
                "tds": 0.0,
                "net_pnl_before_income_tax": gross_pnl - fees,
                "estimated_tax": 0.0,
                "disclaimer": self.config.disclaimer,
            }
        if asset_class in {"EQUITY", "ETF"}:
            tx = notional * self.config.equity_transaction_tax
        elif asset_class == "COMMODITY":
            tx = notional * self.config.commodity_transaction_tax
        else:
            tx = notional * self.config.default_transaction_tax
        tds = 0.0
        estimated = 0.0
        net = gross_pnl - fees - tx
        if asset_class in self.config.tds_asset_classes and self.config.tds_enabled and notional > 0:
            tds = notional * self.config.tds_rate
            net -= tds
        if asset_class in self.config.vda_asset_classes and self.config.vda_enabled and gross_pnl > 0:
            estimated = gross_pnl * self.config.vda_rate
            if not self.config.loss_setoff_allowed and gross_pnl < 0:
                estimated = 0.0
        return {
            "gross_pnl": gross_pnl,
            "fees": fees,
            "transaction_tax": tx,
            "tds": tds,
            "net_pnl_before_income_tax": net,
            "estimated_tax": estimated,
            "disclaimer": self.config.disclaimer,
        }
