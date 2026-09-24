from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class OrderFlowResult:
    status: str  # AVAILABLE | UNAVAILABLE
    cvd: float | None = None
    reason: str | None = None

    def to_dict(self) -> dict:
        return {"status": self.status, "cvd": self.cvd, "reason": self.reason}


class OrderFlowProvider(Protocol):
    def fetch(self, symbol: str) -> OrderFlowResult: ...


class UnavailableOrderFlowProvider:
    def fetch(self, symbol: str) -> OrderFlowResult:
        return OrderFlowResult(
            status="UNAVAILABLE",
            reason=(
                f"No reliable CVD/order-flow source configured for {symbol}. "
                "M3 must not claim confirmation."
            ),
        )
