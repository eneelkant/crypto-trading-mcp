"""Phase 7 dashboard unit tests."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from crypto_trading_mcp.dashboard.app import create_app
from crypto_trading_mcp.dashboard.browser import open_dashboard_browser, reset_browser_gate
from crypto_trading_mcp.dashboard.config import DashboardSettings, load_dashboard_config
from crypto_trading_mcp.dashboard.cycle import run_paper_demo_cycle
from crypto_trading_mcp.dashboard.event_bus import EventBus, get_event_bus, reset_event_bus
from crypto_trading_mcp.dashboard.events import EventType, sanitize_payload
from crypto_trading_mcp.dashboard.state import DashboardState, set_dashboard_state


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("DASHBOARD_AUTO_OPEN", "false")
    monkeypatch.setenv("DASHBOARD_HEADLESS", "true")
    reset_event_bus()
    reset_browser_gate()
    state = DashboardState()
    set_dashboard_state(state)
    app = create_app(DashboardSettings(auto_open=False, host="127.0.0.1", port=8050))
    return TestClient(app)


def test_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["TRADING_MODE"] == "PAPER"
    assert body["LIVE_TRADING_ENABLED"] is False


def test_agents_sixteen(client):
    res = client.get("/api/agents")
    assert res.status_code == 200
    agents = res.json()
    assert len(agents) == 16


def test_sanitize_secrets():
    payload = sanitize_payload(
        {
            "api_key": "secret",
            "decision": "BUY",
            "chain_of_thought": "private",
            "nested": {"password": "x", "ok": 1},
        }
    )
    assert payload["api_key"] == "[REDACTED]"
    assert "chain_of_thought" not in payload
    assert payload["nested"]["password"] == "[REDACTED]"
    assert payload["nested"]["ok"] == 1


def test_event_bus_history():
    reset_event_bus()
    bus = get_event_bus(history_limit=10)
    bus.emit(EventType.AGENT_STARTED, agent_id="strategy", payload={"api_key": "nope"})
    hist = bus.history(limit=5)
    assert hist
    assert hist[-1]["payload"]["api_key"] == "[REDACTED]"


def test_browser_disabled(monkeypatch):
    reset_browser_gate()
    monkeypatch.setenv("DASHBOARD_HEADLESS", "true")
    settings = DashboardSettings(auto_open=False)
    out = open_dashboard_browser(settings)
    assert out["opened"] is False


def test_browser_blocks_non_local():
    reset_browser_gate()
    settings = DashboardSettings(host="example.com", port=8050, auto_open=True)
    out = open_dashboard_browser(settings, force=True)
    assert out["opened"] is False
    assert out["reason"] == "NON_LOCAL_URL_BLOCKED"


def test_demo_cycle_paper_only(client):
    # ensure settings paper
    result = run_paper_demo_cycle(price=100.0)
    assert result["TRADING_MODE"] == "PAPER"
    assert result["LIVE_TRADING_ENABLED"] is False
    # events streamed
    events = client.get("/api/events?limit=50").json()
    types = {e["event_type"] for e in events}
    assert "StrategySignalGenerated" in types or "AgentCompleted" in types


def test_kill_switch_action(client):
    res = client.post("/api/actions/kill-switch")
    assert res.status_code == 200
    assert res.json()["activated"] is True
    risk = client.get("/api/risk").json()
    assert risk["kill_switch"]["active"] is True


def test_backtest_action(client):
    res = client.post("/api/actions/run-backtest?bars=50")
    assert res.status_code == 200
    body = res.json()
    assert body["TRADING_MODE"] == "PAPER"
    assert "backtest_id" in body


def test_no_live_enable_endpoint(client):
    # There should be no endpoint that flips live trading on.
    res = client.post("/api/actions/enable-live")
    assert res.status_code in {404, 405, 422}


def test_market_indicators_server_side(client):
    res = client.get("/api/market/BTC-USD?bars=40")
    assert res.status_code == 200
    body = res.json()
    assert "indicators" in body
    assert "rsi_14" in body["indicators"]


def test_config_defaults():
    cfg = load_dashboard_config()
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 8050
