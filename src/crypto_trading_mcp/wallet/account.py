from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class CustodyModel(str, Enum):
    CENTRALIZED_EXCHANGE = "CENTRALIZED_EXCHANGE"
    BLOCKCHAIN_WALLET = "BLOCKCHAIN_WALLET"
    PAPER_SIMULATED = "PAPER_SIMULATED"


class AccountSnapshot(BaseModel):
    custody: CustodyModel = CustodyModel.CENTRALIZED_EXCHANGE
    exchange: str
    balances: list[dict[str, Any]] = Field(default_factory=list)
    available_balances: dict[str, float] = Field(default_factory=dict)
    positions: list[dict[str, Any]] = Field(default_factory=list)
    margin: dict[str, Any] = Field(default_factory=dict)
    collateral: dict[str, Any] = Field(default_factory=dict)
    open_orders: list[dict[str, Any]] = Field(default_factory=list)
    fills: list[dict[str, Any]] = Field(default_factory=list)
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0

    def requires_blockchain_private_key(self) -> bool:
        return self.custody == CustodyModel.BLOCKCHAIN_WALLET


def cex_trading_requires_blockchain_key() -> bool:
    """Canonical answer for Coinbase/Delta CEX API trading."""
    return False
