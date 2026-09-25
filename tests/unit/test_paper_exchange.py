from __future__ import annotations

from crypto_trading_mcp.exchange.models import Order, OrderSide, OrderStatus, OrderType
from crypto_trading_mcp.exchange.paper import PaperExchange


def test_market_order_buy_sell_with_fees_slippage():
    ex = PaperExchange(prices={"BTC/USD": 100.0})
    buy = Order(symbol="BTC/USD", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1)
    filled = ex.create_order(buy, market_price=100.0)
    assert filled.status == OrderStatus.FILLED
    assert filled.average_fill_price is not None
    assert filled.average_fill_price > 100.0  # buy slippage
    assert filled.fees > 0
    assert "BTC/USD" in ex.portfolio.positions

    sell = Order(symbol="BTC/USD", side=OrderSide.SELL, order_type=OrderType.MARKET, quantity=1)
    sold = ex.create_order(sell, market_price=110.0)
    assert sold.status == OrderStatus.FILLED
    assert "BTC/USD" not in ex.portfolio.positions
    assert ex.portfolio.realized_pnl != 0


def test_limit_order_rests_then_fills():
    ex = PaperExchange(prices={"ETH/USD": 100.0})
    order = Order(
        symbol="ETH/USD",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=1,
        limit_price=95.0,
    )
    resting = ex.create_order(order, market_price=100.0)
    assert resting.status == OrderStatus.OPEN
    ex.on_price_update("ETH/USD", 94.0)
    assert ex.get_order(order.order_id).status == OrderStatus.FILLED


def test_stop_loss_and_take_profit():
    ex = PaperExchange(prices={"BTC/USD": 100.0})
    buy = Order(
        symbol="BTC/USD",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=1,
        metadata={"stop_loss": 95.0, "take_profit": 120.0},
    )
    ex.create_order(buy, 100.0)
    ex.configure_position_rules("BTC/USD", move_be_at_1r=True, partial_tp_pct=50)
    # Hit stop
    ex.on_price_update("BTC/USD", 94.0)
    assert "BTC/USD" not in ex.portfolio.positions
    assert any(e["type"] == "POSITION_CLOSED" for e in ex.events)


def test_cancel_order():
    ex = PaperExchange(prices={"SPY": 400.0})
    order = Order(
        symbol="SPY",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=1,
        limit_price=390.0,
    )
    ex.create_order(order, 400.0)
    cancelled = ex.cancel_order(order.order_id)
    assert cancelled.status == OrderStatus.CANCELLED


def test_api_failure_circuit_breaker():
    ex = PaperExchange(prices={"BTC/USD": 1.0})
    ex.record_api_failure()
    ex.record_api_failure()
    ex.record_api_failure()
    assert ex.halted
    order = Order(symbol="BTC/USD", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1)
    rejected = ex.create_order(order, 1.0)
    assert rejected.status == OrderStatus.REJECTED
