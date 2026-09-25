from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class AssetClass(StrEnum):
    CRYPTO = "CRYPTO"
    EQUITY = "EQUITY"
    ETF = "ETF"
    COMMODITY = "COMMODITY"
    FUTURE = "FUTURE"
    PREDICTION_CONTRACT = "PREDICTION_CONTRACT"


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"
    TAKE_PROFIT = "TAKE_PROFIT"


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    BUY_YES = "BUY_YES"
    SELL_YES = "SELL_YES"
    BUY_NO = "BUY_NO"
    SELL_NO = "SELL_NO"


class OrderStatus(StrEnum):
    CREATED = "CREATED"
    NEW = "CREATED"  # alias
    VALIDATED = "VALIDATED"
    SUBMITTED = "SUBMITTED"
    OPEN = "SUBMITTED"  # alias
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class TimeInForce(StrEnum):
    GTC = "GTC"
    IOC = "IOC"
    DAY = "DAY"


class SettlementType(StrEnum):
    CASH = "CASH"
    PHYSICAL = "PHYSICAL"
    BINARY = "BINARY"


ORDER_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.CREATED: {
        OrderStatus.VALIDATED,
        OrderStatus.SUBMITTED,
        OrderStatus.FILLED,
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.REJECTED,
        OrderStatus.CANCELLED,
    },
    OrderStatus.VALIDATED: {
        OrderStatus.SUBMITTED,
        OrderStatus.REJECTED,
        OrderStatus.CANCELLED,
    },
    OrderStatus.SUBMITTED: {
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED,
        OrderStatus.CANCELLED,
        OrderStatus.EXPIRED,
    },
    OrderStatus.PARTIALLY_FILLED: {
        OrderStatus.FILLED,
        OrderStatus.CANCELLED,
        OrderStatus.EXPIRED,
    },
    OrderStatus.FILLED: set(),
    OrderStatus.CANCELLED: set(),
    OrderStatus.REJECTED: set(),
    OrderStatus.EXPIRED: set(),
}


class TradingHours(BaseModel):
    timezone: str = "UTC"
    sessions: list[str] = Field(default_factory=lambda: ["00:00-23:59"])
    always_open: bool = True


class InstrumentMeta(BaseModel):
    instrument_id: str | None = None
    symbol: str
    asset_class: AssetClass
    quote_currency: str = "USD"
    tick_size: float = 0.01
    lot_size: float = 0.0001
    contract_multiplier: float = 1.0
    multiplier: float = 1.0  # legacy alias of contract_multiplier
    margin_required: float = 0.0
    shortable: bool = True
    trading_hours: TradingHours = Field(default_factory=TradingHours)
    expiration: datetime | None = None
    settlement_type: SettlementType = SettlementType.CASH

    def model_post_init(self, __context: Any) -> None:
        if self.instrument_id is None:
            self.instrument_id = f"{self.asset_class.value}:{self.symbol.upper()}"
        if self.multiplier != 1.0 and self.contract_multiplier == 1.0:
            self.contract_multiplier = self.multiplier
        elif self.contract_multiplier != 1.0:
            self.multiplier = self.contract_multiplier


def deterministic_order_id(
    *,
    session_id: str,
    sequence: int,
    symbol: str,
    side: str,
    quantity: float,
) -> str:
    """Reproducible order IDs for deterministic replay tests."""
    raw = f"{session_id}|{sequence}|{symbol.upper()}|{side.upper()}|{quantity:.10f}"
    digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"ORD-{session_id}-{sequence:06d}-{digest}"


def deterministic_fill_id(*, order_id: str, sequence: int, price: float, quantity: float) -> str:
    raw = f"{order_id}|{sequence}|{price:.10f}|{quantity:.10f}"
    digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"FILL-{sequence:06d}-{digest}"


class Order(BaseModel):
    order_id: str | None = None
    client_order_id: str | None = None
    exchange: str = "paper"
    session_id: str | None = None
    instrument_id: str | None = None
    symbol: str
    instrument_type: AssetClass = AssetClass.CRYPTO
    side: OrderSide
    order_type: OrderType
    quantity: float
    filled_quantity: float = 0.0
    limit_price: float | None = None
    stop_price: float | None = None
    status: OrderStatus = OrderStatus.CREATED
    time_in_force: TimeInForce = TimeInForce.GTC
    strategy_id: str | None = None
    strategy_version: str | None = None
    strategy_config_hash: str | None = None
    model_ids: list[str] = Field(default_factory=list)
    agent_run_id: str | None = None
    requested_price: float | None = None
    average_fill_price: float | None = None
    fees: float = 0.0
    slippage: float = 0.0
    reject_reason: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("order_id", mode="before")
    @classmethod
    def _empty_order_id(cls, value: Any) -> Any:
        return value or None

    def ensure_id(self, *, session_id: str, sequence: int) -> str:
        if self.order_id:
            return self.order_id
        self.order_id = deterministic_order_id(
            session_id=session_id,
            sequence=sequence,
            symbol=self.symbol,
            side=self.side.value,
            quantity=self.quantity,
        )
        self.session_id = self.session_id or session_id
        return self.order_id

    def transition(self, new_status: OrderStatus) -> None:
        # Normalize aliases so NEW/OPEN comparisons work.
        current = OrderStatus(self.status.value)
        target = OrderStatus(new_status.value)
        if current == target:
            return
        allowed = ORDER_TRANSITIONS.get(current, set())
        # Also allow transitions keyed by aliases that share values.
        if target not in allowed:
            # Expand alias membership for transition lookup.
            allowed_values = {s.value for s in allowed}
            if target.value not in allowed_values:
                raise ValueError(f"Invalid order transition {self.status} → {new_status}")
        self.status = target
        self.updated_at = datetime.now(UTC)


class Fill(BaseModel):
    fill_id: str | None = None
    order_id: str
    symbol: str
    side: OrderSide
    quantity: float
    requested_price: float | None = None
    fill_price: float
    slippage: float = 0.0
    fee: float = 0.0
    liquidity: str = "taker"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)

    def ensure_id(self, sequence: int) -> str:
        if self.fill_id:
            return self.fill_id
        self.fill_id = deterministic_fill_id(
            order_id=self.order_id,
            sequence=sequence,
            price=self.fill_price,
            quantity=self.quantity,
        )
        return self.fill_id


class Balance(BaseModel):
    currency: str
    free: float
    locked: float = 0.0

    @property
    def total(self) -> float:
        return self.free + self.locked
