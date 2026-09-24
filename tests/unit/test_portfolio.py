from __future__ import annotations

from crypto_trading_mcp.portfolio.manager import PortfolioManager


def test_open_increase_partial_full_close_and_pnl():
    pm = PortfolioManager(starting_cash=10_000)
    pm.open_position(symbol="BTC/USD", side="LONG", quantity=1, price=100, fee=1)
    snap = pm.snapshot(marks={"BTC/USD": 110})
    assert snap.unrealized_pnl == 10
    assert snap.fees == 1

    pm.open_position(symbol="BTC/USD", side="LONG", quantity=1, price=120, fee=1)
    pos = pm.positions["BTC/USD"]
    assert pos.quantity == 2
    assert pos.average_entry_price == 110

    realized = pm.close_position("BTC/USD", quantity=1, price=130, fee=1)
    assert realized == (130 - 110) * 1 - 1
    assert pm.positions["BTC/USD"].quantity == 1

    pm.close_position("BTC/USD", price=100, fee=0)
    assert "BTC/USD" not in pm.positions
    snap = pm.snapshot()
    assert snap.realized_pnl != 0
    assert snap.equity == snap.cash


def test_short_conceptual_pnl():
    pm = PortfolioManager(starting_cash=10_000)
    pm.open_position(symbol="ETH/USD", side="SHORT", quantity=1, price=100, fee=0)
    snap = pm.snapshot(marks={"ETH/USD": 90})
    assert snap.unrealized_pnl == 10


def test_drawdown_and_daily_pnl():
    pm = PortfolioManager(starting_cash=1000)
    pm.open_position(symbol="BTC/USD", side="LONG", quantity=1, price=100, fee=0)
    snap = pm.snapshot(marks={"BTC/USD": 80})
    assert snap.drawdown_pct > 0
    assert snap.daily_pnl < 0
