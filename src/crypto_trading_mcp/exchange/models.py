from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol
from uuid import uuid4

from pydantic import BaseModel, Field


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


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    BUY_YES = "BUY_YES"
    SELL_YES = "SELL_YES"
    BUY_NO = "BUY_NO"
    SELL_NO = "SELL_NO"


class OrderStatus(StrEnum):
    NEW = "NEW"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class TimeInForce(StrEnum):
    GTC = "GTC"
    IOC = "IOC"
    DAY = "DAY"


ORDER_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.NEW: {
        OrderStatus.OPEN,
        OrderStatus.FILLED,
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.REJECTED,
        OrderStatus.CANCELLED,
    },
    OrderStatus.OPEN: {
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


class InstrumentMeta(BaseModel):
    symbol: str
    asset_class: AssetClass
    tick_size: float = 0.01
    lot_size: float = 0.0001
    multiplier: float = 1.0
    quote_currency: str = "USD"


class Order(BaseModel):
    order_id: str = Field(default_factory=lambda: str(uuid4()))
    client_order_id: str | None = None
    exchange: str = "paper"
    symbol: str
    instrument_type: AssetClass = AssetClass.CRYPTO
    side: OrderSide
    order_type: OrderType
    quantity: float
    filled_quantity: float = 0.0
    limit_price: float | None = None
    stop_price: float | None = None
    status: OrderStatus = OrderStatus.NEW
    time_in_force: TimeInForce = TimeInForce.GTC
    strategy_id: str | None = None
    strategy_version: str | None = None
    model_ids: list[str] = Field(default_factory=list)
    agent_run_id: str | None = None
    requested_price: float | None = None
    average_fill_price: float | None = None
    fees: float = 0.0
    slippage: float = 0.0
    reject_reason: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)

    def transition(self, new_status: OrderStatus) -> None:
        allowed = ORDER_TRANSITIONS.get(self.status, set())
        if new_status not in allowed:
            raise ValueError(f"Invalid order transition {self.status} → {new_status}")
        self.status = new_status
        self.updated_at = datetime.now(UTC)


class Fill(BaseModel):
    fill_id: str = Field(default_factory=lambda: str(uuid4()))
    order_id: str
    symbol: str
    side: OrderSide
    quantity: float
    requested_price: float | None = None
    fill_price: float
    slippage: float = 0.0
    fee: float = 0.0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


class Balance(BaseModel):
    currency: str
    free: float
    locked: float = 0.0

    @property
    def total(self) -> float:
        return self.free + self.locked


class ExchangeAdapter(Protocol):
    name: str

    def get_balance(self) -> list[Balance]: ...

    def get_positions(self) -> list[dict[str, Any]]: ...

    def get_market_price(self, symbol: str) -> float: ...

    def get_orderbook(self, symbol: str, limit: int = 20) -> dict[str, Any]: ...

    def create_order(self, order: Order, market_price: float) -> Order: ...

    def cancel_order(self, order_id: str) -> Order: ...

    def get_order(self, order_id: str) -> Order: ...

    def get_open_orders(self, symbol: str | None = None) -> list[Order]: ...
