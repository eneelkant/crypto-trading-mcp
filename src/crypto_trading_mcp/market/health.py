from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from crypto_trading_mcp.market.models import Candle, MarketSnapshot, Ticker


class MarketDataHealth:
    def __init__(self, max_age_seconds: float = 120.0) -> None:
        self.max_age_seconds = max_age_seconds
        self.last_error: str | None = None
        self.last_ok_at: datetime | None = None

    def mark_ok(self) -> None:
        self.last_ok_at = datetime.now(UTC)
        self.last_error = None

    def mark_error(self, message: str) -> None:
        self.last_error = message

    def is_stale_ticker(self, ticker: Ticker) -> bool:
        return ticker.age_seconds > self.max_age_seconds

    def is_stale_candles(self, candles: list[Candle]) -> bool:
        if not candles:
            return True
        age = (datetime.now(UTC) - candles[-1].timestamp).total_seconds()
        return age > self.max_age_seconds

    def snapshot_allows_new_trade(self, snapshot: MarketSnapshot) -> bool:
        if snapshot.error or snapshot.stale or not snapshot.available:
            return False
        return True

    def status(self) -> dict[str, Any]:
        return {
            "max_age_seconds": self.max_age_seconds,
            "last_ok_at": None if self.last_ok_at is None else self.last_ok_at.isoformat(),
            "last_error": self.last_error,
            "ok": self.last_error is None,
        }
