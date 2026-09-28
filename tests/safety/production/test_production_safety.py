from __future__ import annotations

from crypto_trading_mcp.ci.safety_gates import run_all_gates
from crypto_trading_mcp.config.settings import get_settings
from crypto_trading_mcp.live import LiveExecutionPolicy, LiveTradingGate, TradingStage


def test_defaults_disable_live():
    s = get_settings()
    assert s.trading_mode == "paper"
    assert s.live_trading_enabled is False
    assert s.real_money_enabled is False


def test_ci_safety_gates_pass():
    assert run_all_gates()["ok"] is True


def test_even_optimistic_policy_blocked_in_paper():
    gate = LiveTradingGate()
    result = gate.evaluate(
        LiveExecutionPolicy(
            trading_mode="paper",
            live_trading_enabled=True,
            stage=TradingStage.STAGE_6_AUTONOMOUS_LIVE,
            kill_switch_active=False,
            credentials_healthy=True,
            credentials_allow_trading=True,
            market_data_fresh=True,
            exchange_healthy=True,
            risk_engine_healthy=True,
            reconciliation_ok=True,
            clock_skew_ok=True,
            idempotency_ok=True,
            order_valid=True,
            daily_loss_ok=True,
            drawdown_ok=True,
            exposure_ok=True,
            position_ok=True,
            exchange="coinbase",
            exchange_allowlist=["coinbase"],
            symbol="BTC/USD",
            instrument_allowlist=["BTC/USD"],
        )
    )
    assert result["approved"] is False
