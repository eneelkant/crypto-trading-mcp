"""E2E-style dashboard checks using TestClient (no external browser required)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from crypto_trading_mcp.dashboard.app import create_app
from crypto_trading_mcp.dashboard.browser import reset_browser_gate
from crypto_trading_mcp.dashboard.config import DashboardSettings
from crypto_trading_mcp.dashboard.event_bus import reset_event_bus
from crypto_trading_mcp.dashboard.state import DashboardState, set_dashboard_state


def test_e2e_command_center_flow(monkeypatch):
    monkeypatch.setenv("DASHBOARD_AUTO_OPEN", "false")
    monkeypatch.setenv("DASHBOARD_HEADLESS", "true")
    reset_event_bus()
    reset_browser_gate()
    set_dashboard_state(DashboardState())
    client = TestClient(create_app(DashboardSettings(auto_open=False)))

    assert client.get("/").status_code == 200
    assert client.get("/api/health").json()["LIVE_TRADING_ENABLED"] is False
    assert len(client.get("/api/agents").json()) == 16
    demo = client.post("/api/actions/demo-cycle").json()
    assert demo["executed"] in {True, False}
    assert demo["LIVE_TRADING_ENABLED"] is False
    events = client.get("/api/events?limit=100").json()
    assert any(e["event_type"] in {"StrategySignalGenerated", "ConsensusGenerated", "OrderFilled", "RiskRejected", "RiskApproved"} for e in events)
    assert client.get("/api/portfolio").json()["TRADING_MODE"] == "PAPER"
    assert client.post("/api/actions/run-backtest?bars=30").json().get("backtest_id")
