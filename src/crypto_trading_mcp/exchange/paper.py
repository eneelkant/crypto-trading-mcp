from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from crypto_trading_mcp.exchange.config import instrument_catalog, load_paper_config
from crypto_trading_mcp.exchange.models import (
    AssetClass,
    Balance,
    Fill,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
)
from crypto_trading_mcp.portfolio.manager import PortfolioManager, Position


class PaperExchangeError(RuntimeError):
    pass


class PaperExchange:
    """Deterministic simulated exchange. Never talks to real venues."""

    name = "paper"

    def __init__(
        self,
        *,
        portfolio: PortfolioManager | None = None,
        config: dict[str, Any] | None = None,
        prices: dict[str, float] | None = None,
    ) -> None:
        self.config = config or load_paper_config()
        paper = self.config.get("paper", {})
        initial = float(paper.get("initial_cash", 10_000))
        self.quote = str(paper.get("quote_currency", "USD"))
        self.fee_rate = float((paper.get("fees") or {}).get("default_rate", 0.001))
        slip = paper.get("slippage") or {}
        self.slippage_bps = float(slip.get("value", 5)) if slip.get("mode", "fixed_bps") == "fixed_bps" else 5.0
        self.portfolio = portfolio or PortfolioManager(starting_cash=initial)
        self.instruments = instrument_catalog(self.config)
        self.prices: dict[str, float] = {k.upper(): float(v) for k, v in (prices or {}).items()}
        self.orders: dict[str, Order] = {}
        self.fills: list[Fill] = []
        self.events: list[dict[str, Any]] = []
        self.trades: list[dict[str, Any]] = []
        self.api_failures = 0
        self.halted = False
        self.halt_reason: str | None = None

    # --- market data ---
    def set_price(self, symbol: str, price: float) -> None:
        self.prices[symbol.upper()] = float(price)

    def get_market_price(self, symbol: str) -> float:
        sym = symbol.upper()
        if sym not in self.prices:
            raise PaperExchangeError(f"No market price for {sym}")
        return self.prices[sym]

    def get_orderbook(self, symbol: str, limit: int = 20) -> dict[str, Any]:
        px = self.get_market_price(symbol)
        return {
            "symbol": symbol.upper(),
            "bids": [{"price": px * 0.999, "amount": 1.0}],
            "asks": [{"price": px * 1.001, "amount": 1.0}],
            "limit": limit,
        }

    def get_balance(self) -> list[Balance]:
        snap = self.portfolio.snapshot(self.prices)
        return [Balance(currency=self.quote, free=snap.available_cash, locked=0.0)]

    def get_positions(self) -> list[dict[str, Any]]:
        return [p.model_dump(mode="json") for p in self.portfolio.snapshot(self.prices).positions]

    # --- orders ---
    def create_order(self, order: Order, market_price: float | None = None) -> Order:
        if self.halted:
            order.status = OrderStatus.REJECTED
            order.reject_reason = self.halt_reason or "TRADING_HALTED"
            order.updated_at = datetime.now(UTC)
            self.orders[order.order_id] = order
            return order

        px = market_price if market_price is not None else self.prices.get(order.symbol.upper())
        if px is None:
            order.status = OrderStatus.REJECTED
            order.reject_reason = "NO_MARKET_PRICE"
            self.orders[order.order_id] = order
            return order

        order.requested_price = px
        order.instrument_type = self._asset_class(order.symbol)
        order.transition(OrderStatus.OPEN)
        self.orders[order.order_id] = order

        if order.order_type == OrderType.MARKET:
            return self._fill_market(order, px)
        if order.order_type == OrderType.LIMIT:
            if self._limit_triggered(order, px):
                return self._fill_market(order, float(order.limit_price or px), limit_fill=True)
            return order
        if order.order_type in {OrderType.STOP, OrderType.STOP_LIMIT}:
            # Resting until stop triggers on mark updates.
            return order
        order.transition(OrderStatus.REJECTED)
        order.reject_reason = "UNSUPPORTED_ORDER_TYPE"
        return order

    def cancel_order(self, order_id: str) -> Order:
        order = self.get_order(order_id)
        if order.status in {OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED}:
            return order
        order.transition(OrderStatus.CANCELLED)
        return order

    def get_order(self, order_id: str) -> Order:
        if order_id not in self.orders:
            raise KeyError(order_id)
        return self.orders[order_id]

    def get_open_orders(self, symbol: str | None = None) -> list[Order]:
        open_states = {OrderStatus.NEW, OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED}
        orders = [o for o in self.orders.values() if o.status in open_states]
        if symbol:
            orders = [o for o in orders if o.symbol.upper() == symbol.upper()]
        return orders

    def on_price_update(self, symbol: str, price: float) -> list[Fill]:
        """Advance resting stops/limits and manage protective exits."""
        self.set_price(symbol, price)
        new_fills: list[Fill] = []
        for order in list(self.get_open_orders(symbol)):
            if order.order_type == OrderType.LIMIT and self._limit_triggered(order, price):
                new_fills.extend(self._fill_market(order, float(order.limit_price or price), limit_fill=True).metadata.get("_fills", []))
            elif order.order_type in {OrderType.STOP, OrderType.STOP_LIMIT}:
                if self._stop_triggered(order, price):
                    fill_px = price if order.order_type == OrderType.STOP else float(order.limit_price or price)
                    self.events.append(
                        {
                            "type": "STOP_TRIGGERED",
                            "order_id": order.order_id,
                            "trigger_price": order.stop_price,
                            "execution_price": fill_px,
                            "timestamp": datetime.now(UTC).isoformat(),
                        }
                    )
                    filled = self._fill_market(order, fill_px)
                    new_fills.append(
                        Fill(
                            order_id=filled.order_id,
                            symbol=filled.symbol,
                            side=filled.side,
                            quantity=filled.filled_quantity,
                            requested_price=filled.requested_price,
                            fill_price=float(filled.average_fill_price or fill_px),
                            slippage=filled.slippage,
                            fee=filled.fees,
                        )
                    )
        # Position protective management
        self._manage_open_position(symbol, price)
        return new_fills

    # --- internals ---
    def _asset_class(self, symbol: str) -> AssetClass:
        meta = self.instruments.get(symbol.upper())
        if meta:
            return meta.asset_class
        if symbol.upper().startswith("PREDICT/"):
            return AssetClass.PREDICTION_CONTRACT
        return AssetClass.CRYPTO

    def _slippage_amount(self, price: float) -> float:
        return price * (self.slippage_bps / 10_000.0)

    def _apply_slippage(self, side: OrderSide, market_price: float, *, prediction: bool = False) -> tuple[float, float]:
        slip = self._slippage_amount(market_price)
        if prediction:
            # Prediction contracts priced in [0,1]; slippage still applied but clamped.
            if side in {OrderSide.BUY, OrderSide.BUY_YES, OrderSide.BUY_NO}:
                fill = min(1.0, market_price + slip)
            else:
                fill = max(0.0, market_price - slip)
            return fill, abs(fill - market_price)
        if side in {OrderSide.BUY, OrderSide.BUY_YES, OrderSide.BUY_NO}:
            fill = market_price + slip
        else:
            fill = market_price - slip
        return fill, abs(fill - market_price)

    def _limit_triggered(self, order: Order, market_price: float) -> bool:
        if order.limit_price is None:
            return False
        if order.side in {OrderSide.BUY, OrderSide.BUY_YES, OrderSide.BUY_NO}:
            return market_price <= order.limit_price
        return market_price >= order.limit_price

    def _stop_triggered(self, order: Order, market_price: float) -> bool:
        if order.stop_price is None:
            return False
        if order.side in {OrderSide.SELL, OrderSide.SELL_YES, OrderSide.SELL_NO}:
            return market_price <= order.stop_price
        return market_price >= order.stop_price

    def _fill_market(self, order: Order, market_price: float, *, limit_fill: bool = False) -> Order:
        prediction = order.instrument_type == AssetClass.PREDICTION_CONTRACT
        fill_price, slip = self._apply_slippage(order.side, market_price, prediction=prediction)
        if limit_fill and order.limit_price is not None:
            # Fill at limit or better (deterministic: use limit).
            fill_price = float(order.limit_price)
            slip = abs(fill_price - market_price)
        qty = order.quantity - order.filled_quantity
        fee = abs(qty * fill_price) * self.fee_rate
        side_portfolio = "LONG" if order.side in {OrderSide.BUY, OrderSide.BUY_YES, OrderSide.BUY_NO} else "SHORT"

        try:
            if side_portfolio == "LONG":
                # Opening / adding long, or covering short via BUY.
                if order.symbol in self.portfolio.positions and self.portfolio.positions[order.symbol].side in {
                    "SHORT",
                    "SELL",
                }:
                    self.portfolio.close_position(order.symbol, quantity=qty, price=fill_price, fee=fee)
                else:
                    self.portfolio.open_position(
                        symbol=order.symbol,
                        side="LONG",
                        quantity=qty,
                        price=fill_price,
                        fee=fee,
                        stop_loss=order.metadata.get("stop_loss"),
                        take_profit=order.metadata.get("take_profit"),
                        strategy_id=order.strategy_id,
                        strategy_version=order.strategy_version,
                    )
            else:
                if order.symbol in self.portfolio.positions and self.portfolio.positions[order.symbol].side in {
                    "LONG",
                    "BUY",
                }:
                    pnl = self.portfolio.close_position(
                        order.symbol, quantity=qty, price=fill_price, fee=fee
                    )
                    self._record_trade(order, qty, fill_price, fee, slip, pnl)
                else:
                    self.portfolio.open_position(
                        symbol=order.symbol,
                        side="SHORT",
                        quantity=qty,
                        price=fill_price,
                        fee=fee,
                        stop_loss=order.metadata.get("stop_loss"),
                        take_profit=order.metadata.get("take_profit"),
                        strategy_id=order.strategy_id,
                        strategy_version=order.strategy_version,
                    )
        except Exception as exc:  # noqa: BLE001
            order.transition(OrderStatus.REJECTED)
            order.reject_reason = str(exc)
            return order

        fill = Fill(
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=qty,
            requested_price=order.requested_price,
            fill_price=fill_price,
            slippage=slip,
            fee=fee,
            metadata={"limit_fill": limit_fill},
        )
        self.fills.append(fill)
        order.filled_quantity += qty
        order.average_fill_price = fill_price
        order.fees += fee
        order.slippage = slip
        if order.filled_quantity + 1e-12 >= order.quantity:
            order.transition(OrderStatus.FILLED)
        else:
            order.transition(OrderStatus.PARTIALLY_FILLED)
        order.metadata["_fills"] = [fill]
        # Attach protective stops from metadata if opening.
        pos = self.portfolio.positions.get(order.symbol)
        if pos is not None:
            if order.metadata.get("stop_loss") is not None:
                pos.stop_loss = float(order.metadata["stop_loss"])
            if order.metadata.get("take_profit") is not None:
                pos.take_profit = float(order.metadata["take_profit"])
            pos.strategy_id = order.strategy_id or pos.strategy_id
            pos.strategy_version = order.strategy_version or pos.strategy_version
        return order

    def _manage_open_position(self, symbol: str, price: float) -> None:
        pos = self.portfolio.positions.get(symbol.upper())
        if pos is None:
            return
        pos.mark(price)
        entry = pos.average_entry_price
        # Breakeven move at +1R
        if pos.metadata_breakeven_enabled() if hasattr(pos, "metadata_breakeven_enabled") else False:
            pass
        stop = pos.stop_loss
        tp = pos.take_profit
        # 1R breakeven from metadata stored on exchange events
        risk = None
        if stop is not None:
            risk = abs(entry - stop)
        if risk and risk > 0:
            move_be = bool(pos.__dict__.get("move_be_at_1r", False)) or bool(
                getattr(self, "_be_flags", {}).get(symbol.upper())
            )
            if move_be:
                if pos.side in {"LONG", "BUY"} and price >= entry + risk and stop < entry:
                    pos.stop_loss = entry
                    self.events.append(
                        {
                            "type": "STOP_MOVED_TO_BREAKEVEN",
                            "symbol": symbol.upper(),
                            "new_stop": entry,
                            "timestamp": datetime.now(UTC).isoformat(),
                        }
                    )
                if pos.side in {"SHORT", "SELL"} and price <= entry - risk and (stop is None or stop > entry):
                    pos.stop_loss = entry
                    self.events.append(
                        {
                            "type": "STOP_MOVED_TO_BREAKEVEN",
                            "symbol": symbol.upper(),
                            "new_stop": entry,
                            "timestamp": datetime.now(UTC).isoformat(),
                        }
                    )

        # Partial TP at 1R
        partial = getattr(self, "_partial_tp", {}).get(symbol.upper())
        if partial and risk and risk > 0 and not partial.get("done"):
            pct = float(partial.get("exit_quantity_percent", 50)) / 100.0
            hit = (
                price >= entry + risk
                if pos.side in {"LONG", "BUY"}
                else price <= entry - risk
            )
            if hit and pct > 0:
                qty = pos.quantity * pct
                pnl = self.portfolio.close_position(symbol.upper(), quantity=qty, price=price, fee=qty * price * self.fee_rate)
                self.events.append(
                    {
                        "type": "PARTIAL_TAKE_PROFIT",
                        "symbol": symbol.upper(),
                        "quantity": qty,
                        "price": price,
                        "pnl": pnl,
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                )
                partial["done"] = True

        # Full stop / TP
        if pos.side in {"LONG", "BUY"}:
            if stop is not None and price <= stop:
                self._exit_position(symbol, price, reason="STOP_LOSS")
            elif tp is not None and price >= tp:
                self._exit_position(symbol, price, reason="TAKE_PROFIT")
        else:
            if stop is not None and price >= stop:
                self._exit_position(symbol, price, reason="STOP_LOSS")
            elif tp is not None and price <= tp:
                self._exit_position(symbol, price, reason="TAKE_PROFIT")

        # Trailing ATR stop
        trail = getattr(self, "_trailing", {}).get(symbol.upper())
        if trail and symbol.upper() in self.portfolio.positions:
            atr = float(trail.get("atr", 0))
            mult = float(trail.get("multiplier", 2.0))
            pos = self.portfolio.positions[symbol.upper()]
            if atr > 0:
                if pos.side in {"LONG", "BUY"}:
                    new_stop = price - atr * mult
                    if pos.stop_loss is None or new_stop > pos.stop_loss:
                        pos.stop_loss = new_stop
                else:
                    new_stop = price + atr * mult
                    if pos.stop_loss is None or new_stop < pos.stop_loss:
                        pos.stop_loss = new_stop

        # Mean reversion exit toward SMA
        mr = getattr(self, "_mean_reversion_exit", {}).get(symbol.upper())
        if mr and symbol.upper() in self.portfolio.positions:
            sma = mr.get("sma_20")
            if isinstance(sma, (int, float)):
                pos = self.portfolio.positions[symbol.upper()]
                if pos.side in {"LONG", "BUY"} and price <= sma:
                    self._exit_position(symbol, price, reason="MEAN_REVERSION_SMA")
                elif pos.side in {"SHORT", "SELL"} and price >= sma:
                    self._exit_position(symbol, price, reason="MEAN_REVERSION_SMA")

    def _exit_position(self, symbol: str, price: float, reason: str) -> None:
        if symbol.upper() not in self.portfolio.positions:
            return
        pos = self.portfolio.positions[symbol.upper()]
        fee = pos.quantity * price * self.fee_rate
        pnl = self.portfolio.close_position(symbol.upper(), price=price, fee=fee)
        self.events.append(
            {
                "type": "POSITION_CLOSED",
                "symbol": symbol.upper(),
                "reason": reason,
                "price": price,
                "pnl": pnl,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        self._record_trade_close(pos, price, fee, pnl, reason)

    def _record_trade(self, order: Order, qty: float, price: float, fee: float, slip: float, pnl: float) -> None:
        self.trades.append(
            {
                "trade_id": str(uuid4()),
                "order_id": order.order_id,
                "exchange": self.name,
                "instrument": order.symbol,
                "asset_class": order.instrument_type.value,
                "strategy_id": order.strategy_id,
                "strategy_version": order.strategy_version,
                "model_ids": order.model_ids,
                "agent_run_id": order.agent_run_id,
                "entry": None,
                "exit": price,
                "quantity": qty,
                "gross_pnl": pnl + fee,
                "fees": fee,
                "tax_friction": 0.0,
                "slippage": slip,
                "net_pnl": pnl,
                "entry_time": None,
                "exit_time": datetime.now(UTC).isoformat(),
                "reason_for_entry": None,
                "reason_for_exit": "CLOSE",
            }
        )

    def _record_trade_close(self, pos: Position, price: float, fee: float, pnl: float, reason: str) -> None:
        self.trades.append(
            {
                "trade_id": str(uuid4()),
                "order_id": None,
                "exchange": self.name,
                "instrument": pos.symbol,
                "asset_class": self._asset_class(pos.symbol).value,
                "strategy_id": pos.strategy_id,
                "strategy_version": pos.strategy_version,
                "model_ids": [],
                "agent_run_id": None,
                "entry": pos.average_entry_price,
                "exit": price,
                "quantity": pos.quantity,
                "gross_pnl": pnl + fee,
                "fees": fee,
                "tax_friction": 0.0,
                "slippage": 0.0,
                "net_pnl": pnl,
                "entry_time": pos.opened_at.isoformat(),
                "exit_time": datetime.now(UTC).isoformat(),
                "reason_for_entry": None,
                "reason_for_exit": reason,
            }
        )

    def configure_position_rules(
        self,
        symbol: str,
        *,
        move_be_at_1r: bool = False,
        partial_tp_pct: float | None = None,
        trailing_atr: float | None = None,
        trailing_mult: float = 2.0,
        mean_reversion_sma: float | None = None,
    ) -> None:
        sym = symbol.upper()
        if not hasattr(self, "_be_flags"):
            self._be_flags = {}
        if not hasattr(self, "_partial_tp"):
            self._partial_tp = {}
        if not hasattr(self, "_trailing"):
            self._trailing = {}
        if not hasattr(self, "_mean_reversion_exit"):
            self._mean_reversion_exit = {}
        self._be_flags[sym] = move_be_at_1r
        if partial_tp_pct is not None:
            self._partial_tp[sym] = {"exit_quantity_percent": partial_tp_pct, "done": False}
        if trailing_atr is not None:
            self._trailing[sym] = {"atr": trailing_atr, "multiplier": trailing_mult}
        if mean_reversion_sma is not None:
            self._mean_reversion_exit[sym] = {"sma_20": mean_reversion_sma}

    def record_api_failure(self) -> None:
        self.api_failures += 1
        max_fail = int(self.config.get("paper", {}).get("max_consecutive_api_failures", 3))
        if self.api_failures >= max_fail:
            self.halted = True
            self.halt_reason = "API_FAILURE_CIRCUIT_BREAKER"

    def record_api_success(self) -> None:
        self.api_failures = 0

    def halt(self, reason: str) -> None:
        self.halted = True
        self.halt_reason = reason

    def reset_halt(self) -> None:
        self.halted = False
        self.halt_reason = None
        self.api_failures = 0
