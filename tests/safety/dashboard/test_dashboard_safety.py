"""Dashboard safety: secrets, no live activation, resilience of event bus."""

from __future__ import annotations

from crypto_trading_mcp.dashboard.cycle import run_paper_demo_cycle
from crypto_trading_mcp.dashboard.event_bus import EventBus
from crypto_trading_mcp.dashboard.events import EventType
from crypto_trading_mcp.dashboard.state import DashboardState
from crypto_trading_mcp.exchange.exceptions import LiveExecutionBlocked
from crypto_trading_mcp.exchange.factory import create_exchange


def test_dashboard_cannot_resolve_live_exchange():
    try:
        create_exchange("coinbase")
        assert False, "should block"
    except LiveExecutionBlocked:
        pass


def test_event_listener_failure_does_not_break_bus():
    bus = EventBus(history_limit=20)

    def bad(_event):
        raise RuntimeError("listener boom")

    bus.subscribe(bad)
    event = bus.emit(EventType.SYSTEM_HEALTH_CHANGED, payload={"ok": True})
    assert event.event_id
    assert bus.publish_errors >= 1


def test_demo_uses_risk_and_paper_not_live():
    state = DashboardState()
    out = run_paper_demo_cycle(state=state, price=100.0)
    assert out["LIVE_TRADING_ENABLED"] is False
    assert state.paper.settings.live_trading_enabled is False
    assert state.settings.trading_mode == "paper"
