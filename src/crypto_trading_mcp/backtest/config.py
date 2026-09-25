from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from crypto_trading_mcp.backtest.models import stable_hash
from crypto_trading_mcp.config.settings import REPO_ROOT


class BacktestConfig(BaseModel):
    initial_capital: float = 100_000.0
    base_currency: str = "USD"
    commission_enabled: bool = True
    slippage_enabled: bool = True
    include_fees: bool = True
    include_slippage: bool = True
    prevent_lookahead: bool = True
    prevent_data_leakage: bool = True
    closed_candle_only: bool = True
    execution_model: str = "paper_exchange"
    use_strategy_risk_rules: bool = True
    agent_mode: str = "deterministic"
    llm_enabled: bool = False
    llm_cache_enabled: bool = True
    random_seed: int = 42
    reports_dir: str = "reports/backtests"
    tax_enabled: bool = False
    raw: dict[str, Any] = Field(default_factory=dict)

    def config_hash(self) -> str:
        payload = self.model_dump(exclude={"raw"})
        return stable_hash(payload)[:16]


def load_backtest_config(path: Path | None = None) -> BacktestConfig:
    path = path or (REPO_ROOT / "config" / "backtesting.yaml")
    if not path.exists():
        return BacktestConfig()
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    bt = data.get("backtesting") or {}
    tax = bt.get("tax_simulation") or {}
    sizing = bt.get("position_sizing") or {}
    commission = bt.get("commission") or {}
    slip = bt.get("slippage") or {}
    return BacktestConfig(
        initial_capital=float(bt.get("initial_capital", 100_000)),
        base_currency=str(bt.get("base_currency", "USD")),
        commission_enabled=bool(commission.get("enabled", True)),
        slippage_enabled=bool(slip.get("enabled", True)),
        include_fees=bool(bt.get("include_fees", True)),
        include_slippage=bool(bt.get("include_slippage", True)),
        prevent_lookahead=bool(bt.get("prevent_lookahead", True)),
        prevent_data_leakage=bool(bt.get("prevent_data_leakage", True)),
        closed_candle_only=bool(bt.get("closed_candle_only", True)),
        execution_model=str(bt.get("execution_model", "paper_exchange")),
        use_strategy_risk_rules=bool(sizing.get("use_strategy_risk_rules", True)),
        agent_mode=str(bt.get("agent_mode", "deterministic")),
        llm_enabled=bool(bt.get("llm_enabled", False)),
        llm_cache_enabled=bool(bt.get("llm_cache_enabled", True)),
        random_seed=int(bt.get("random_seed", 42)),
        reports_dir=str(bt.get("reports_dir", "reports/backtests")),
        tax_enabled=bool(tax.get("tax_enabled", False)),
        raw=data if isinstance(data, dict) else {},
    )


def walk_forward_settings(config: BacktestConfig | None = None) -> dict[str, Any]:
    cfg = config or load_backtest_config()
    wf = (cfg.raw.get("walk_forward") or {}) if cfg.raw else {}
    return {
        "enabled": bool(wf.get("enabled", True)),
        "training_days": int(wf.get("training_days", 180)),
        "validation_days": int(wf.get("validation_days", 60)),
        "test_days": int(wf.get("test_days", 60)),
        "step_days": int(wf.get("step_days", 30)),
    }
