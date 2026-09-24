from __future__ import annotations

from crypto_trading_mcp.dashboard.cycle import run_paper_demo_cycle
from crypto_trading_mcp.dashboard.event_bus import get_event_bus, reset_event_bus
from crypto_trading_mcp.dashboard.state import get_dashboard_state
from crypto_trading_mcp.learning.engine import get_learning_engine
from crypto_trading_mcp.learning.models import TradeLearningRecord


def test_trade_close_to_memory_and_eventbus(tmp_path, monkeypatch):
    reset_event_bus()
    eng = get_learning_engine(reset=True)
    bus = get_event_bus()
    before = len(bus.history(limit=5000))
    rec = TradeLearningRecord(
        trade_id="INT-1",
        symbol="BTC/USD",
        net_pnl=-2.0,
        predicted_probability=0.8,
        entry_price=100,
        exit_price=98,
        slippage=0.8,
        execution_quality="POOR",
    )
    out = eng.on_trade_close(rec)
    assert out["post_mortem"]["trade_id"] == "INT-1"
    assert eng.memory.summary()["total"] >= 1
    hist = bus.history(limit=5000)
    assert len(hist) > before
    types = {str(e["event_type"]) for e in hist}
    assert any("Postmortem" in t or "Learning" in t or "Brier" in t for t in types)


def test_demo_cycle_includes_learning():
    reset_event_bus()
    get_learning_engine(reset=True)
    state = get_dashboard_state()
    out = run_paper_demo_cycle(state=state, symbol="BTC/USD", price=100.0)
    assert out["TRADING_MODE"] == "PAPER"
    assert out["LIVE_TRADING_ENABLED"] is False
    if out.get("executed"):
        assert out.get("learning") is not None
        assert out["learning"]["trades_processed"] >= 1
