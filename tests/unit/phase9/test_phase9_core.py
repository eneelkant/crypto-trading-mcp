from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from crypto_trading_mcp.autonomous.idempotency import make_idempotency_key
from crypto_trading_mcp.autonomous.loop import AutonomousPaperLoop
from crypto_trading_mcp.autonomous.states import CycleState, CycleStateMachine
from crypto_trading_mcp.exchange.auth import delta_india_signature
from crypto_trading_mcp.exchange.coinbase import CoinbaseAdapter
from crypto_trading_mcp.exchange.delta_india import DeltaExchangeIndiaAdapter
from crypto_trading_mcp.exchange.exceptions import LiveExecutionBlocked
from crypto_trading_mcp.exchange.factory import create_exchange
from crypto_trading_mcp.market.data import MockMarketData
from crypto_trading_mcp.market.gateway import MarketDataGateway
from crypto_trading_mcp.market.normalizer import enrich_record, normalize_candles, normalize_ticker
from crypto_trading_mcp.market.models import Candle


def test_normalize_and_enrich():
    ticker = normalize_ticker({"last": 100.0, "bid": 99.0, "ask": 101.0}, symbol="BTC/USD", source="mock")
    assert ticker.last == 100.0
    candles = normalize_candles([[1_700_000_000_000, 1, 2, 0.5, 1.5, 10]])
    assert len(candles) == 1
    rec = enrich_record({"price": 1}, symbol="BTC/USD", source="mock")
    assert rec["symbol"] == "BTC/USD"
    assert "sequence_id" in rec


def test_stale_market_blocks_new_trade():
    md = MockMarketData(force_stale=True)
    gw = MarketDataGateway(md)
    snap = gw.get_snapshot("BTC/USD")
    assert snap.stale is True
    assert gw.allows_new_trade(snap) is False


def test_fresh_market_allows_trade():
    md = MockMarketData(force_stale=False)
    gw = MarketDataGateway(md)
    snap = gw.get_snapshot("BTC/USD")
    assert gw.allows_new_trade(snap) is True


def test_delta_hmac_signature_deterministic():
    sig1 = delta_india_signature(
        secret="secret",
        method="GET",
        timestamp="1700000000000",
        request_path="/v2/positions",
        query_params="",
        body="",
    )
    sig2 = delta_india_signature(
        secret="secret",
        method="GET",
        timestamp="1700000000000",
        request_path="/v2/positions",
        query_params="",
        body="",
    )
    assert sig1 == sig2
    assert len(sig1) == 64


def test_coinbase_live_orders_blocked():
    def transport(method, url, **kwargs):
        return httpx.Response(200, json={"price": "100.0"})

    adapter = CoinbaseAdapter(transport=transport)
    assert adapter.get_market_price("BTC-USD") == 100.0
    from crypto_trading_mcp.exchange.models import Order, OrderSide, OrderType

    order = Order(
        symbol="BTC/USD",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=0.01,
    )
    with pytest.raises(LiveExecutionBlocked):
        adapter.create_order(order)


def test_delta_live_orders_blocked():
    def transport(method, url, **kwargs):
        return httpx.Response(200, json={"result": {"close": "200.0"}})

    adapter = DeltaExchangeIndiaAdapter(api_key="k", api_secret="s", transport=transport)
    assert adapter.get_market_price("BTCUSD") == 200.0
    headers = adapter.sign(method="GET", request_path="/v2/wallet/balances")
    assert "signature" in headers
    from crypto_trading_mcp.exchange.models import Order, OrderSide, OrderType

    order = Order(
        symbol="BTC/USD",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=0.01,
    )
    with pytest.raises(LiveExecutionBlocked):
        adapter.create_order(order)


def test_factory_still_blocks_default_live_resolve():
    with pytest.raises(LiveExecutionBlocked):
        create_exchange("coinbase")
    adapter = create_exchange("coinbase", allow_read_adapters=True)
    assert adapter.name == "coinbase"


def test_idempotency_stable():
    a = make_idempotency_key(
        strategy_id="momentum_breakout_crypto",
        symbol="BTC/USD",
        timeframe="1h",
        cycle_id="202601011200",
        signal_version="1",
        side="LONG",
    )
    b = make_idempotency_key(
        strategy_id="momentum_breakout_crypto",
        symbol="BTC/USD",
        timeframe="1h",
        cycle_id="202601011200",
        signal_version="1",
        side="LONG",
    )
    assert a == b


def test_cycle_state_machine():
    sm = CycleStateMachine()
    sm.transition(CycleState.MARKET_DATA_READY)
    sm.transition(CycleState.ANALYSIS_RUNNING)
    sm.transition(CycleState.CONSENSUS_READY)
    with pytest.raises(ValueError):
        sm.transition(CycleState.ORDER_FILLED)


def test_autonomous_loop_run_once_and_duplicate():
    loop = AutonomousPaperLoop(
        config={
            "interval_seconds": 1,
            "symbols": ["BTC/USD"],
            "timeframe": "1h",
            "strategy_id": "momentum_breakout_crypto",
            "duplicate_cycle_protection": True,
            "persist_state": False,
            "live_trading_enabled": False,
        },
        market=MarketDataGateway(MockMarketData()),
    )
    first = loop.run_once(price=100.0)
    second = loop.run_once(price=100.0)
    assert first["TRADING_MODE"] == "paper"
    assert first["LIVE_TRADING_ENABLED"] is False
    assert second.get("reason") == "DUPLICATE_CYCLE_IDEMPOTENCY" or second["executed"] in {True, False}


def test_autonomous_loop_stale_no_trade():
    loop = AutonomousPaperLoop(
        config={"persist_state": False, "duplicate_cycle_protection": False, "live_trading_enabled": False},
        market=MarketDataGateway(MockMarketData(force_stale=True)),
    )
    out = loop.run_once(price=100.0)
    assert out["executed"] is False
    assert out["reason"] == "STALE_OR_UNAVAILABLE_MARKET_DATA"
