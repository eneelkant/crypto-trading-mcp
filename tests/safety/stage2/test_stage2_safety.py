from __future__ import annotations

import pytest

from crypto_trading_mcp.ci.safety_gates import run_all_gates
from crypto_trading_mcp.config.settings import get_settings
from crypto_trading_mcp.live import LiveExecutionPolicy, LiveTradingGate, TradingStage
from crypto_trading_mcp.sandbox.delta_sandbox import DeltaIndiaSandboxAdapter
from crypto_trading_mcp.sandbox.endpoints import SandboxEndpointError


def test_defaults_still_paper():
    s = get_settings()
    assert s.trading_mode == "paper"
    assert s.live_trading_enabled is False


def test_ci_gates_still_pass():
    assert run_all_gates()["ok"] is True


def test_live_gate_blocked_in_stage2_paper():
    gate = LiveTradingGate()
    result = gate.evaluate(
        LiveExecutionPolicy(
            trading_mode="paper",
            live_trading_enabled=False,
            stage=TradingStage.STAGE_2_CLOUD_PAPER,
            cloud_paper_isolated=True,
            credentials_healthy=True,
            credentials_allow_trading=True,
            market_data_fresh=True,
            exchange_healthy=True,
            reconciliation_ok=True,
            order_valid=True,
            exchange="delta_india",
            exchange_allowlist=["delta_india"],
        )
    )
    assert result["approved"] is False
    assert result["Live Execution"] == "DISABLED"


def test_adapter_rejects_production_host():
    with pytest.raises(SandboxEndpointError):
        DeltaIndiaSandboxAdapter(base_url="https://api.india.delta.exchange", use_local_harness=True)
