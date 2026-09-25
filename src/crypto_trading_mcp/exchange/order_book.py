from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class OrderBookLevel:
    price: float
    amount: float


@dataclass
class OrderBook:
    symbol: str
    bids: list[OrderBookLevel] = field(default_factory=list)
    asks: list[OrderBookLevel] = field(default_factory=list)

    def to_dict(self, limit: int = 20) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "bids": [{"price": b.price, "amount": b.amount} for b in self.bids[:limit]],
            "asks": [{"price": a.price, "amount": a.amount} for a in self.asks[:limit]],
            "limit": limit,
        }


def synthetic_book(symbol: str, mid: float, *, spread_bps: float = 10.0) -> OrderBook:
    half = mid * (spread_bps / 10_000.0) / 2.0
    return OrderBook(
        symbol=symbol.upper(),
        bids=[OrderBookLevel(price=mid - half, amount=1.0)],
        asks=[OrderBookLevel(price=mid + half, amount=1.0)],
    )
