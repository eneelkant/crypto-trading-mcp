from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class SettlementResult:
    settlement_id: str
    market_id: str
    symbol: str
    winning_outcome: str
    settlement_value: float
    pnl: float
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "settlement_id": self.settlement_id,
            "market_id": self.market_id,
            "symbol": self.symbol,
            "winning_outcome": self.winning_outcome,
            "settlement_value": self.settlement_value,
            "pnl": self.pnl,
            "timestamp": self.timestamp,
        }


def prediction_settlement_value(*, held_outcome: str, winning_outcome: str) -> float:
    """YES/NO binary settlement: winning outcome pays 1, otherwise 0."""
    return 1.0 if held_outcome.upper() == winning_outcome.upper() else 0.0


def build_settlement_record(
    *,
    market_id: str,
    symbol: str,
    winning_outcome: str,
    settlement_value: float,
    pnl: float,
    settlement_id: str | None = None,
) -> SettlementResult:
    return SettlementResult(
        settlement_id=settlement_id or str(uuid4()),
        market_id=market_id,
        symbol=symbol,
        winning_outcome=winning_outcome.upper(),
        settlement_value=settlement_value,
        pnl=pnl,
        timestamp=datetime.now(UTC).isoformat(),
    )
