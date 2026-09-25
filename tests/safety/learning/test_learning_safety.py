from __future__ import annotations

import pytest

from crypto_trading_mcp.config.settings import get_settings
from crypto_trading_mcp.learning.config import LearningConfig
from crypto_trading_mcp.learning.engine import LearningEngine
from crypto_trading_mcp.learning.kelly import bounded_kelly_multiplier
from crypto_trading_mcp.risk.config import load_risk_config


def test_learning_cannot_enable_live_or_weaken_safety():
    settings = get_settings()
    assert settings.trading_mode == "paper" or settings.trading_mode.value == "paper" or str(settings.trading_mode).lower() == "paper"
    assert settings.live_trading_enabled is False
    cfg = LearningConfig()
    with pytest.raises(PermissionError):
        LearningConfig(automatic_live_deployment=True).assert_safety()
    with pytest.raises(PermissionError):
        LearningConfig(learning_can_modify_hard_risk_limits=True).assert_safety()
    with pytest.raises(PermissionError):
        LearningConfig(learning_can_disable_kill_switch=True).assert_safety()
    with pytest.raises(PermissionError):
        LearningConfig(learning_can_create_exchange_orders=True).assert_safety()
    cfg.assert_safety()


def test_kelly_cannot_override_risk_limits():
    risk = load_risk_config()
    result = bounded_kelly_multiplier(
        win_probability=0.99, payoff_ratio=10.0, config=LearningConfig(), calibration_degraded=False
    )
    assert result["can_override_risk_limits"] is False
    # Risk hard limits still present independently
    assert risk.risk.max_drawdown_pct is not None or hasattr(risk.risk, "max_position_size")


def test_engine_status_safety_block():
    eng = LearningEngine(config=LearningConfig())
    safety = eng.status()["safety"]
    assert safety["automatic_live_deployment"] is False
    assert safety["LIVE_TRADING_ENABLED"] is False
    assert safety["TRADING_MODE"] == "paper"
