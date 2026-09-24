from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class Position(BaseModel):
    symbol: str
    side: str
    quantity: float
    average_entry_price: float
    current_price: float
    market_value: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    fees: float = 0.0
    stop_loss: float | None = None
    take_profit: float | None = None
    strategy_id: str | None = None
    strategy_version: str | None = None
    opened_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def mark(self, price: float) -> None:
        self.current_price = price
        self.market_value = abs(self.quantity) * price
        if self.side.upper() in {"LONG", "BUY"}:
            self.unrealized_pnl = (price - self.average_entry_price) * self.quantity
        else:
            self.unrealized_pnl = (self.average_entry_price - price) * self.quantity


class PortfolioSnapshot(BaseModel):
    cash: float
    equity: float
    available_cash: float
    positions_exposure: float
    realized_pnl: float
    unrealized_pnl: float
    fees: float
    daily_pnl: float
    drawdown_pct: float
    peak_equity: float
    positions: list[Position] = Field(default_factory=list)
    trades_today: int = 0
    last_trade_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class PortfolioManager:
    """Deterministic accounting portfolio. No exchange execution."""

    def __init__(self, starting_cash: float = 10_000.0) -> None:
        self.cash = float(starting_cash)
        self.realized_pnl = 0.0
        self.fees_paid = 0.0
        self.peak_equity = float(starting_cash)
        self.day_start_equity = float(starting_cash)
        self.positions: dict[str, Position] = {}
        self.trades_today = 0
        self.last_trade_at: datetime | None = None

    def snapshot(self, marks: dict[str, float] | None = None) -> PortfolioSnapshot:
        marks = marks or {}
        positions: list[Position] = []
        unrealized = 0.0
        exposure = 0.0
        equity = self.cash
        for symbol, pos in self.positions.items():
            if symbol in marks:
                pos.mark(marks[symbol])
            else:
                pos.mark(pos.current_price)
            positions.append(pos.model_copy(deep=True))
            unrealized += pos.unrealized_pnl
            exposure += pos.market_value
            if pos.side.upper() in {"LONG", "BUY"}:
                equity += pos.market_value
            else:
                # Short proceeds already in cash; subtract current liability.
                equity -= pos.market_value

        self.peak_equity = max(self.peak_equity, equity)
        drawdown = (
            0.0
            if self.peak_equity <= 0
            else max(0.0, (self.peak_equity - equity) / self.peak_equity)
        )
        return PortfolioSnapshot(
            cash=self.cash,
            equity=equity,
            available_cash=max(self.cash, 0.0),
            positions_exposure=exposure,
            realized_pnl=self.realized_pnl,
            unrealized_pnl=unrealized,
            fees=self.fees_paid,
            daily_pnl=equity - self.day_start_equity,
            drawdown_pct=drawdown,
            peak_equity=self.peak_equity,
            positions=positions,
            trades_today=self.trades_today,
            last_trade_at=self.last_trade_at,
        )

    def open_position(
        self,
        *,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        fee: float = 0.0,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        strategy_id: str | None = None,
        strategy_version: str | None = None,
    ) -> Position:
        if quantity <= 0 or price <= 0:
            raise ValueError("quantity and price must be positive")
        notional = quantity * price
        side_u = side.upper()
        if side_u in {"LONG", "BUY"}:
            cost = notional + fee
            if cost > self.cash + 1e-9:
                raise ValueError("Insufficient cash")
            self.cash -= cost
        elif side_u in {"SHORT", "SELL"}:
            self.cash += notional - fee
        else:
            raise ValueError(f"Unsupported side: {side}")

        self.fees_paid += fee
        existing = self.positions.get(symbol)
        if existing and existing.side.upper() == side_u:
            total_qty = existing.quantity + quantity
            existing.average_entry_price = (
                (existing.average_entry_price * existing.quantity) + (price * quantity)
            ) / total_qty
            existing.quantity = total_qty
            existing.fees += fee
            existing.mark(price)
            position = existing
        else:
            if existing:
                raise ValueError("Close opposite position before opening reverse side")
            position = Position(
                symbol=symbol,
                side=side_u,
                quantity=quantity,
                average_entry_price=price,
                current_price=price,
                market_value=notional,
                fees=fee,
                stop_loss=stop_loss,
                take_profit=take_profit,
                strategy_id=strategy_id,
                strategy_version=strategy_version,
            )
            self.positions[symbol] = position
        self.trades_today += 1
        self.last_trade_at = datetime.now(UTC)
        return position

    def close_position(
        self,
        symbol: str,
        *,
        quantity: float | None = None,
        price: float,
        fee: float = 0.0,
    ) -> float:
        if symbol not in self.positions:
            raise KeyError(f"No position for {symbol}")
        pos = self.positions[symbol]
        qty = pos.quantity if quantity is None else quantity
        if qty <= 0 or qty > pos.quantity + 1e-12:
            raise ValueError("Invalid close quantity")
        if pos.side.upper() in {"LONG", "BUY"}:
            pnl = (price - pos.average_entry_price) * qty - fee
            self.cash += qty * price - fee
        else:
            pnl = (pos.average_entry_price - price) * qty - fee
            self.cash -= qty * price + fee
        self.realized_pnl += pnl
        self.fees_paid += fee
        pos.realized_pnl += pnl
        pos.fees += fee
        if abs(pos.quantity - qty) < 1e-12:
            del self.positions[symbol]
        else:
            pos.quantity -= qty
            pos.mark(price)
        self.trades_today += 1
        self.last_trade_at = datetime.now(UTC)
        return pnl

    def reset_day(self) -> None:
        snap = self.snapshot()
        self.day_start_equity = snap.equity
        self.trades_today = 0
