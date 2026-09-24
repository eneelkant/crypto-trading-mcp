from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from crypto_trading_mcp.config.settings import REPO_ROOT


class LearningConfig(BaseModel):
    enabled: bool = True
    memory_enabled: bool = True
    failure_log: str = "references/failure_log.json"
    similarity_threshold: float = 0.80
    max_retrieved_cases: int = 5
    post_mortem_enabled: bool = True
    post_mortem_trigger: str = "ON_TRADE_CLOSE"
    rolling_window_trades: int = 50
    max_acceptable_brier_score: float = 0.25
    retraining_enabled: bool = True
    interval_trades: int = 100
    primary_model: str = "XGBoost_Classifier"
    optional_model: str = "RandomForest"
    validation: str = "OUT_OF_SAMPLE_WALK_FORWARD"
    min_sample_size: int = 20
    kelly_base_fraction: float = 0.25
    kelly_degraded_fraction: float = 0.125
    kelly_min_multiplier: float = 0.25
    kelly_max_multiplier: float = 1.0
    regime_enabled: bool = True
    drift_enabled: bool = True
    brier_degrade_delta: float = 0.05
    winrate_degrade_delta: float = 0.15
    automatic_live_deployment: bool = False
    learning_can_modify_hard_risk_limits: bool = False
    learning_can_disable_kill_switch: bool = False
    learning_can_create_exchange_orders: bool = False
    reflection_enabled: bool = True
    after_every_trade: bool = True
    raw: dict[str, Any] = Field(default_factory=dict)

    def assert_safety(self) -> None:
        if self.automatic_live_deployment:
            raise PermissionError("automatic_live_deployment must remain false")
        if self.learning_can_modify_hard_risk_limits:
            raise PermissionError("learning cannot modify hard risk limits")
        if self.learning_can_disable_kill_switch:
            raise PermissionError("learning cannot disable kill switch")
        if self.learning_can_create_exchange_orders:
            raise PermissionError("learning cannot create exchange orders")


def load_learning_config(path: Path | None = None) -> LearningConfig:
    path = path or (REPO_ROOT / "config" / "self_learning.yaml")
    if not path.exists():
        cfg = LearningConfig()
        cfg.assert_safety()
        return cfg
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    sl = data.get("self_learning") or {}
    memory = sl.get("memory") or {}
    post = sl.get("post_mortem") or {}
    cal = sl.get("calibration") or {}
    retrain = sl.get("retraining") or {}
    kelly = sl.get("kelly") or {}
    drift = sl.get("drift") or {}
    safety = sl.get("safety") or {}
    reflection = sl.get("reflection") or {}
    cfg = LearningConfig(
        enabled=bool(sl.get("enabled", True)),
        memory_enabled=bool(memory.get("enabled", True)),
        failure_log=str(memory.get("failure_log", "references/failure_log.json")),
        similarity_threshold=float(memory.get("similarity_threshold", 0.80)),
        max_retrieved_cases=int(memory.get("max_retrieved_cases", 5)),
        post_mortem_enabled=bool(post.get("enabled", True)),
        post_mortem_trigger=str(post.get("trigger", "ON_TRADE_CLOSE")),
        rolling_window_trades=int(cal.get("rolling_window_trades", 50)),
        max_acceptable_brier_score=float(cal.get("max_acceptable_brier_score", 0.25)),
        retraining_enabled=bool(retrain.get("enabled", True)),
        interval_trades=int(retrain.get("interval_trades", 100)),
        primary_model=str(retrain.get("model", "XGBoost_Classifier")),
        optional_model=str(retrain.get("optional_model", "RandomForest")),
        validation=str(retrain.get("validation", "OUT_OF_SAMPLE_WALK_FORWARD")),
        min_sample_size=int(retrain.get("min_sample_size", 20)),
        kelly_base_fraction=float(kelly.get("base_fraction", 0.25)),
        kelly_degraded_fraction=float(kelly.get("degraded_fraction", 0.125)),
        kelly_min_multiplier=float(kelly.get("min_multiplier", 0.25)),
        kelly_max_multiplier=float(kelly.get("max_multiplier", 1.0)),
        regime_enabled=bool((sl.get("regime") or {}).get("enabled", True)),
        drift_enabled=bool(drift.get("enabled", True)),
        brier_degrade_delta=float(drift.get("brier_degrade_delta", 0.05)),
        winrate_degrade_delta=float(drift.get("winrate_degrade_delta", 0.15)),
        automatic_live_deployment=bool(safety.get("automatic_live_deployment", False)),
        learning_can_modify_hard_risk_limits=bool(
            safety.get("learning_can_modify_hard_risk_limits", False)
        ),
        learning_can_disable_kill_switch=bool(
            safety.get("learning_can_disable_kill_switch", False)
        ),
        learning_can_create_exchange_orders=bool(
            safety.get("learning_can_create_exchange_orders", False)
        ),
        reflection_enabled=bool(reflection.get("enabled", True)),
        after_every_trade=bool(reflection.get("after_every_trade", True)),
        raw=data if isinstance(data, dict) else {},
    )
    cfg.assert_safety()
    return cfg
