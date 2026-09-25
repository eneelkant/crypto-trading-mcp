"""Integration: dashboard + paper cycle + phase6 backtest visibility."""

from __future__ import annotations

from fastapi.testclient import TestClient

from crypto_trading_mcp.dashboard.app import create_app
from crypto_trading_mcp.dashboard.browser import reset_browser_gate
from crypto_trading_mcp.dashboard.config import DashboardSettings
from crypto_trading_mcp.dashboard.event_bus import reset_event_bus
from crypto_trading_mcp.dashboard.state import DashboardState, set_dashboard_state


def test_full_demo_and_backtest_flow(monkeypatch):
    monkeypatch.setenv("DASHBOARD_AUTO_OPEN", "false")
    monkeypatch.setenv("DASHBOARD_HEADLESS", "true")
    reset_event_bus()
    reset_browser_gate()
    state = DashboardState()
    set_dashboard_state(state)
    client = TestClient(create_app(DashboardSettings(auto_open=False)))

    assert client.get("/api/health").json()["status"] == "ok"
    demo = client.post("/api/actions/demo-cycle").json()
    assert demo["TRADING_MODE"] == "PAPER"
    agents = client.get("/api/agents").json()
    assert len(agents) == 16
    completed = [a for a in agents if a["status"] == "COMPLETED"]
    assert len(completed) >= 5
    portfolio = client.get("/api/portfolio").json()
    assert "equity" in portfolio
    bt = client.post("/api/actions/run-backtest?bars=40").json()
    assert "backtest_id" in bt
    listed = client.get("/api/backtests").json()
    assert listed["latest"]
    wf = client.post("/api/actions/run-walk-forward?bars=60").json()
    assert "folds" in wf
    bench = client.post("/api/actions/run-benchmark?bars=40").json()
    assert "BUY_AND_HOLD" in bench
