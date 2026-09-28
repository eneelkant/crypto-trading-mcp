from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


class MarketDataFreshness:
    def __init__(self, max_age_seconds: float = 120.0) -> None:
        self.max_age_seconds = max_age_seconds

    def age_seconds(self, timestamp: str | datetime | None) -> float | None:
        if timestamp is None:
            return None
        if isinstance(timestamp, datetime):
            ts = timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=UTC)
        else:
            try:
                ts = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
            except ValueError:
                return None
        return max(0.0, (datetime.now(UTC) - ts).total_seconds())

    def is_fresh(self, timestamp: str | datetime | None) -> bool:
        age = self.age_seconds(timestamp)
        if age is None:
            return False
        return age <= self.max_age_seconds

    def allows_new_live_orders(self, *, fresh: bool, available: bool, exchange_ok: bool) -> bool:
        return bool(fresh and available and exchange_ok)

    def status(self, timestamp: str | datetime | None) -> dict[str, Any]:
        age = self.age_seconds(timestamp)
        fresh = self.is_fresh(timestamp)
        return {
            "fresh": fresh,
            "age_seconds": age,
            "max_age_seconds": self.max_age_seconds,
            "allows_new_live_orders": fresh,
        }
