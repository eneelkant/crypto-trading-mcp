from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class FundingRate(BaseModel):
    symbol: str
    rate: float
    timestamp: str | None = None
    source: str = "unknown"


class OpenInterest(BaseModel):
    symbol: str
    open_interest: float
    timestamp: str | None = None
    source: str = "unknown"


class LiquidationEvent(BaseModel):
    symbol: str
    side: str
    quantity: float
    price: float
    timestamp: str | None = None
    source: str = "unknown"


class ExtendedMarketDataProvider:
    """Optional funding / OI / liquidation hooks. Default: unavailable."""

    def get_funding(self, symbol: str) -> FundingRate | None:
        return None

    def get_open_interest(self, symbol: str) -> OpenInterest | None:
        return None

    def get_liquidations(self, symbol: str, *, limit: int = 20) -> list[LiquidationEvent]:
        return []

    def status(self) -> dict[str, Any]:
        return {
            "funding": False,
            "open_interest": False,
            "liquidations": False,
            "note": "extended feeds not configured",
        }
