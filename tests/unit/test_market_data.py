from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from crypto_trading_mcp.market.data import MockMarketData, PublicCCXTMarketData
from crypto_trading_mcp.market.models import Candle, Ticker


def test_mock_snapshot_fresh():
    data = MockMarketData()
    snap = data.get_snapshot("BTC/USD")
    assert snap.available
    assert not snap.stale
    assert snap.ticker is not None
    assert len(snap.candles) > 50


def test_mock_snapshot_stale():
    data = MockMarketData(force_stale=True, max_age_seconds=30)
    snap = data.get_snapshot("BTC/USD")
    assert snap.stale


def test_mock_snapshot_failure():
    data = MockMarketData(fail=True)
    snap = data.get_snapshot("BTC/USD")
    assert not snap.available
    assert snap.error


def test_public_ccxt_rejects_exchange_outside_allowlist():
    svc = PublicCCXTMarketData(allowed_exchanges={"kraken"})
    with pytest.raises(Exception):
        svc.get_ticker("BTC/USD", exchange_id="not_a_real_exchange_xyz")


def test_ticker_age():
    ticker = Ticker(
        exchange="mock",
        symbol="BTC/USD",
        last=1.0,
        bid=1.0,
        ask=1.0,
        quote_volume=1.0,
        fetched_at=datetime.now(UTC) - timedelta(seconds=10),
    )
    assert ticker.age_seconds >= 9
