from __future__ import annotations

from crypto_trading_mcp.dashboard.app import create_app
from crypto_trading_mcp.dashboard.cycle import run_paper_demo_cycle
from crypto_trading_mcp.dashboard.event_bus import reset_event_bus
from crypto_trading_mcp.learning.engine import get_learning_engine
from fastapi.testclient import TestClient


def test_e2e_learning_lifecycle_on_dashboard():
    reset_event_bus()
    get_learning_engine(reset=True)
    app = create_app()
    client = TestClient(app)
    health = client.get("/api/health")
    assert health.status_code == 200

    demo = run_paper_demo_cycle(symbol="BTC/USD", price=100.0)
    assert demo["Live Execution"] == "DISABLED"

    status = client.get("/api/learning/status")
    assert status.status_code == 200
    body = status.json()
    assert body["safety"]["LIVE_TRADING_ENABLED"] is False
    if demo.get("executed"):
        assert body["trades_processed"] >= 1

    cal = client.get("/api/learning/calibration")
    assert cal.status_code == 200
    mem = client.get("/api/learning/memory")
    assert mem.status_code == 200
    audit = client.get("/api/learning/audit")
    assert audit.status_code == 200
