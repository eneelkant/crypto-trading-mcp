from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Sequence
from uuid import uuid4

from crypto_trading_mcp.market.models import Candle, OrderBook, OrderBookLevel, Ticker


def utc_now() -> datetime:
    return datetime.now(UTC)


def normalize_ticker(raw: dict[str, Any], *, symbol: str, source: str) -> Ticker:
    return Ticker(
        exchange=source,
        symbol=str(raw.get("symbol") or symbol).upper(),
        last=float(raw.get("last") or raw.get("price") or raw.get("close") or 0.0),
        bid=float(raw["bid"]) if raw.get("bid") is not None else None,
        ask=float(raw["ask"]) if raw.get("ask") is not None else None,
        quote_volume=float(raw["quoteVolume"]) if raw.get("quoteVolume") is not None else None,
        fetched_at=utc_now(),
    )


def normalize_candles(rows: Sequence[Any]) -> list[Candle]:
    out: list[Candle] = []
    for row in rows:
        if isinstance(row, Candle):
            out.append(row)
            continue
        ts_raw, o, h, l, c, v = row[:6]
        if isinstance(ts_raw, (int, float)):
            ts = datetime.fromtimestamp(
                (ts_raw / 1000.0) if ts_raw > 10_000_000_000 else ts_raw, tz=UTC
            )
        else:
            ts = utc_now()
        out.append(
            Candle(
                timestamp=ts,
                open=float(o),
                high=float(h),
                low=float(l),
                close=float(c),
                volume=float(v),
            )
        )
    return out


def normalize_order_book(raw: dict[str, Any], *, symbol: str, source: str) -> OrderBook:
    bids = [OrderBookLevel(price=float(p), amount=float(a)) for p, a, *_ in (raw.get("bids") or [])]
    asks = [OrderBookLevel(price=float(p), amount=float(a)) for p, a, *_ in (raw.get("asks") or [])]
    return OrderBook(
        exchange=source,
        symbol=symbol.upper(),
        bids=bids,
        asks=asks,
        fetched_at=utc_now(),
    )


def enrich_record(payload: dict[str, Any], *, symbol: str, source: str) -> dict[str, Any]:
    out = dict(payload)
    out.setdefault("symbol", symbol.upper())
    out.setdefault("source", source)
    out.setdefault("timestamp", utc_now().isoformat())
    out.setdefault("received_at", utc_now().isoformat())
    out.setdefault("sequence_id", out.get("sequence_id") or out.get("nonce") or str(uuid4())[:12])
    return out
