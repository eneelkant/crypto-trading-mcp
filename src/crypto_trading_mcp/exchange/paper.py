from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from crypto_trading_mcp.exchange.config import instrument_catalog, load_paper_config
from crypto_trading_mcp.exchange.exceptions import PaperExchangeError
from crypto_trading_mcp.exchange.fees import FeeEngine
from crypto_trading_mcp.exchange.models import (
    AssetClass,
    Balance,
    Fill,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
)
from crypto_trading_mcp.exchange.order_book import synthetic_book
from crypto_trading_mcp.exchange.slippage import SlippageEngine
from crypto_trading_mcp.exchange.trailing import TrailingStopEngine, TrailingStopState
from crypto_trading_mcp.portfolio.manager import PortfolioManager, Position


class PaperExchange:
    """Deterministic simulated exchange. Never talks to real venues."""

    name = "paper"
    supports_live_execution = False

    def __init__(
        self,
        *,
        portfolio: PortfolioManager | None = None,
        config: dict[str, Any] | None = None,
        prices: dict[str, float] | None = None,
        session_id: str = "PAPER_SESSION_LOCAL",
    ) -> None:
        self.config = config or load_paper_config()
        paper = self.config.get("paper") or self.config.get("paper_trading") or {}
        initial = float(paper.get("initial_cash", 10_000))
        self.quote = str(paper.get("quote_currency", "USD"))
        self.session_id = session_id
        self.fee_engine = FeeEngine.from_paper_config(paper)
        self.slippage_engine = SlippageEngine.from_paper_config(paper)
        # Legacy attributes retained for older callers/tests.
        self.fee_rate = self.fee_engine.default_rate
        self.slippage_bps = self.slippage_engine.default_bps
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
        self._order_seq = 0
        self._fill_seq = 0
        self._be_flags: dict[str, bool] = {}
        self._partial_tp: dict[str, dict[str, Any]] = {}
        self._mean_reversion_exit: dict[str, dict[str, Any]] = {}
        self.trailing = TrailingStopEngine()
        self._seen_client_ids: set[str] = set()
        self.failure_mode: str | None = None
        self.stale_symbols: set[str] = set()
        self.flatten_at_eod = bool(paper.get("flatten_at_eod", paper.get("eod_flat_default", False)))

    # --- market data ---
    def set_price(self, symbol: str, price: float) -> None:
        self.prices[symbol.upper()] = float(price)
        self.stale_symbols.discard(symbol.upper())

    def mark_stale(self, symbol: str) -> None:
        self.stale_symbols.add(symbol.upper())

    def get_market_price(self, symbol: str) -> float:
        sym = symbol.upper()
        if sym not in self.prices:
            raise PaperExchangeError(f"No market price for {sym}")
        return self.prices[sym]

    def get_orderbook(self, symbol: str, limit: int = 20) -> dict[str, Any]:
        px = self.get_market_price(symbol)
        return synthetic_book(symbol, px).to_dict(limit=limit)

    def get_balance(self) -> list[Balance]:
        snap = self.portfolio.snapshot(self.prices)
        return [Balance(currency=self.quote, free=snap.available_cash, locked=0.0)]

    def get_positions(self) -> list[dict[str, Any]]:
        return [p.model_dump(mode="json") for p in self.portfolio.snapshot(self.prices).positions]

    # --- failure simulation ---
    def simulate_failure(self, mode: str) -> None:
        self.failure_mode = mode
        if mode in {
            "timeout",
            "rate_limit",
            "connection_error",
            "exchange_unavailable",
            "stale_market_data",
        }:
            self.record_api_failure()

    def clear_failure(self) -> None:
        self.failure_mode = None
        self.record_api_success()

    # --- orders ---
    def create_order(self, order: Order, market_price: float | None = None) -> Order:
        self._order_seq += 1
        order.ensure_id(session_id=self.session_id, sequence=self._order_seq)
        order.exchange = self.name
        order.session_id = self.session_id
        order.instrument_id = order.instrument_id or f"{self._asset_class(order.symbol).value}:{order.symbol.upper()}"

        if order.client_order_id:
            if order.client_order_id in self._seen_client_ids:
                order.status = OrderStatus.REJECTED
                order.reject_reason = "DUPLICATE_ORDER"
                self.orders[order.order_id] = order
                return order
            self._seen_client_ids.add(order.client_order_id)

        if self.halted:
            order.status = OrderStatus.REJECTED
            order.reject_reason = self.halt_reason or "TRADING_HALTED"
            order.updated_at = datetime.now(UTC)
            self.orders[order.order_id] = order
            self._emit("ORDER_REJECTED", order_id=order.order_id, reason=order.reject_reason)
            return order

        if self.failure_mode in {"timeout", "rate_limit", "connection_error", "exchange_unavailable"}:
            order.status = OrderStatus.REJECTED
            order.reject_reason = self.failure_mode.upper()
            self.orders[order.order_id] = order
            self.record_api_failure()
            return order

        if self.failure_mode == "rejected_order":
            order.status = OrderStatus.REJECTED
            order.reject_reason = "SIMULATED_REJECT"
            self.orders[order.order_id] = order
            return order

        if order.quantity <= 0:
            order.status = OrderStatus.REJECTED
            order.reject_reason = "BAD_QUANTITY"
            self.orders[order.order_id] = order
            return order

        if order.symbol.upper() not in self.instruments and not order.symbol.upper().startswith("PREDICT/"):
            # Allow unknown symbols but flag instrument meta as crypto default; invalid if empty.
            if not order.symbol.strip():
                order.status = OrderStatus.REJECTED
                order.reject_reason = "INVALID_INSTRUMENT"
                self.orders[order.order_id] = order
                return order

        px = market_price if market_price is not None else self.prices.get(order.symbol.upper())
        if px is None:
            order.status = OrderStatus.REJECTED
            order.reject_reason = "NO_MARKET_PRICE"
            self.orders[order.order_id] = order
            return order
        if px <= 0:
            order.status = OrderStatus.REJECTED
            order.reject_reason = "BAD_PRICE"
            self.orders[order.order_id] = order
            return order
        if order.symbol.upper() in self.stale_symbols or self.failure_mode == "stale_market_data":
            order.status = OrderStatus.REJECTED
            order.reject_reason = "STALE_MARKET_DATA"
            self.orders[order.order_id] = order
            return order

        order.requested_price = px
        order.instrument_type = self._asset_class(order.symbol)
        if order.status == OrderStatus.CREATED:
            order.transition(OrderStatus.VALIDATED)
        order.transition(OrderStatus.SUBMITTED)
        self.orders[order.order_id] = order
        self._emit("ORDER_SUBMITTED", order_id=order.order_id, symbol=order.symbol)

        if order.order_type == OrderType.MARKET:
            filled = self._fill_market(order, px)
            if self.failure_mode == "partial_fill" and filled.status == OrderStatus.FILLED:
                # Simulate partial then leave remainder cancelled for observability.
                pass
            return filled
        if order.order_type == OrderType.LIMIT:
            if self._limit_triggered(order, px):
                return self._fill_market(order, float(order.limit_price or px), limit_fill=True)
            return order
        if order.order_type in {OrderType.STOP, OrderType.STOP_LIMIT, OrderType.TAKE_PROFIT}:
            return order
        order.transition(OrderStatus.REJECTED)
        order.reject_reason = "UNSUPPORTED_ORDER_TYPE"
        return order

    def cancel_order(self, order_id: str) -> Order:
        order = self.get_order(order_id)
        if order.status in {
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
        }:
            return order
        order.transition(OrderStatus.CANCELLED)
        self._emit("ORDER_CANCELLED", order_id=order.order_id)
        return order

    def expire_order(self, order_id: str) -> Order:
        order = self.get_order(order_id)
        if order.status in {OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED}:
            return order
        order.transition(OrderStatus.EXPIRED)
        return order

    def get_order(self, order_id: str) -> Order:
        if order_id not in self.orders:
            raise KeyError(order_id)
        return self.orders[order_id]

    def get_open_orders(self, symbol: str | None = None) -> list[Order]:
        open_states = {
            OrderStatus.CREATED,
            OrderStatus.VALIDATED,
            OrderStatus.SUBMITTED,
            OrderStatus.PARTIALLY_FILLED,
        }
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
                filled = self._fill_market(order, float(order.limit_price or price), limit_fill=True)
                new_fills.extend(filled.metadata.get("_fills", []))
            elif order.order_type in {OrderType.STOP, OrderType.STOP_LIMIT, OrderType.TAKE_PROFIT}:
                triggered = (
                    self._take_profit_triggered(order, price)
                    if order.order_type == OrderType.TAKE_PROFIT
                    else self._stop_triggered(order, price)
                )
                if triggered:
                    fill_px = (
                        price
                        if order.order_type in {OrderType.STOP, OrderType.TAKE_PROFIT}
                        else float(order.limit_price or price)
                    )
                    self._emit(
                        "STOP_TRIGGERED",
                        order_id=order.order_id,
                        trigger_price=order.stop_price,
                        execution_price=fill_px,
                    )
                    filled = self._fill_market(order, fill_px)
                    new_fills.append(
                        Fill(
                            order_id=filled.order_id or "",
                            symbol=filled.symbol,
                            side=filled.side,
                            quantity=filled.filled_quantity,
                            requested_price=filled.requested_price,
                            fill_price=float(filled.average_fill_price or fill_px),
                            slippage=filled.slippage,
                            fee=filled.fees,
                        )
                    )
        self._manage_open_position(symbol, price)
        return new_fills

    def end_of_day(self) -> dict[str, Any]:
        cancelled = []
        closed = []
        for order in list(self.get_open_orders()):
            self.cancel_order(order.order_id or "")
            cancelled.append(order.order_id)
        if self.flatten_at_eod:
            for symbol in list(self.portfolio.positions.keys()):
                px = self.prices.get(symbol, self.portfolio.positions[symbol].current_price)
                self._exit_position(symbol, px, reason="EOD_FLATTEN")
                closed.append(symbol)
        snap = self.portfolio.snapshot(self.prices)
        self.portfolio.reset_day()
        record = {
            "type": "EOD",
            "cancelled_orders": cancelled,
            "closed_positions": closed,
            "equity": snap.equity,
            "daily_pnl": snap.daily_pnl,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        self.events.append(record)
        return record

    # --- internals ---
    def _emit(self, event_type: str, **payload: Any) -> None:
        self.events.append(
            {
                "type": event_type,
                "session_id": self.session_id,
                "timestamp": datetime.now(UTC).isoformat(),
                **payload,
            }
        )

    def _asset_class(self, symbol: str) -> AssetClass:
        meta = self.instruments.get(symbol.upper())
        if meta:
            return meta.asset_class
        if symbol.upper().startswith("PREDICT/"):
            return AssetClass.PREDICTION_CONTRACT
        return AssetClass.CRYPTO

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

    def _take_profit_triggered(self, order: Order, market_price: float) -> bool:
        # TAKE_PROFIT sell triggers when price rises to stop/limit; buy when falls.
        trigger = order.stop_price if order.stop_price is not None else order.limit_price
        if trigger is None:
            return False
        if order.side in {OrderSide.SELL, OrderSide.SELL_YES, OrderSide.SELL_NO}:
            return market_price >= trigger
        return market_price <= trigger

    def _fill_market(self, order: Order, market_price: float, *, limit_fill: bool = False) -> Order:
        prediction = order.instrument_type == AssetClass.PREDICTION_CONTRACT
        slip_result = self.slippage_engine.apply(
            side=order.side.value,
            market_price=market_price,
            prediction=prediction,
            trade_qty=order.quantity - order.filled_quantity,
        )
        fill_price, slip = slip_result.fill_price, slip_result.slippage_abs
        liquidity = "maker" if limit_fill else "taker"
        if limit_fill and order.limit_price is not None:
            fill_price = float(order.limit_price)
            slip = abs(fill_price - market_price)
            liquidity = "maker"

        remaining = order.quantity - order.filled_quantity
        if self.failure_mode == "partial_fill" and remaining > 0:
            qty = remaining / 2.0
        else:
            qty = remaining

        fee_result = self.fee_engine.calculate(
            notional=qty * fill_price,
            asset_class=order.instrument_type.value,
            liquidity=liquidity,
            exchange=self.name,
        )
        fee = fee_result.fee
        side_portfolio = "LONG" if order.side in {OrderSide.BUY, OrderSide.BUY_YES, OrderSide.BUY_NO} else "SHORT"

        try:
            if side_portfolio == "LONG":
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
            if order.status not in {OrderStatus.REJECTED, OrderStatus.CANCELLED}:
                # May already be SUBMITTED — transition to REJECTED via allowed path.
                if order.status == OrderStatus.SUBMITTED:
                    order.status = OrderStatus.REJECTED
                else:
                    order.transition(OrderStatus.REJECTED)
            order.reject_reason = str(exc)
            order.updated_at = datetime.now(UTC)
            return order

        self._fill_seq += 1
        fill = Fill(
            order_id=order.order_id or "",
            symbol=order.symbol,
            side=order.side,
            quantity=qty,
            requested_price=order.requested_price,
            fill_price=fill_price,
            slippage=slip,
            fee=fee,
            liquidity=liquidity,
            metadata={
                "limit_fill": limit_fill,
                "slippage_bps": slip_result.slippage_bps,
                "fee_schedule": fee_result.schedule,
                "fee_rate": fee_result.rate,
            },
        )
        fill.ensure_id(self._fill_seq)
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
        self._emit(
            "ORDER_FILLED" if order.status == OrderStatus.FILLED else "ORDER_PARTIALLY_FILLED",
            order_id=order.order_id,
            fill_price=fill_price,
            fee=fee,
            slippage=slip,
        )
        pos = self.portfolio.positions.get(order.symbol)
        if pos is not None:
            if order.metadata.get("stop_loss") is not None:
                pos.stop_loss = float(order.metadata["stop_loss"])
            if order.metadata.get("take_profit") is not None:
                pos.take_profit = float(order.metadata["take_profit"])
            pos.strategy_id = order.strategy_id or pos.strategy_id
            pos.strategy_version = order.strategy_version or pos.strategy_version
            self._emit("POSITION_UPDATED", symbol=order.symbol, quantity=pos.quantity)
        return order

    def _manage_open_position(self, symbol: str, price: float) -> None:
        pos = self.portfolio.positions.get(symbol.upper())
        if pos is None:
            return
        pos.mark(price)
        entry = pos.average_entry_price
        stop = pos.stop_loss
        tp = pos.take_profit
        risk = abs(entry - stop) if stop is not None else None
        if risk and risk > 0 and self._be_flags.get(symbol.upper()):
            if pos.side in {"LONG", "BUY"} and price >= entry + risk and (stop is None or stop < entry):
                pos.stop_loss = entry
                self._emit("STOP_MOVED_TO_BREAKEVEN", symbol=symbol.upper(), new_stop=entry)
                self._emit("STOP_UPDATED", symbol=symbol.upper(), new_stop=entry)
            if pos.side in {"SHORT", "SELL"} and price <= entry - risk and (stop is None or stop > entry):
                pos.stop_loss = entry
                self._emit("STOP_MOVED_TO_BREAKEVEN", symbol=symbol.upper(), new_stop=entry)

        partial = self._partial_tp.get(symbol.upper())
        if partial and risk and risk > 0 and not partial.get("done"):
            pct = float(partial.get("exit_quantity_percent", 50)) / 100.0
            hit = price >= entry + risk if pos.side in {"LONG", "BUY"} else price <= entry - risk
            if hit and pct > 0 and symbol.upper() in self.portfolio.positions:
                qty = pos.quantity * pct
                fee = self.fee_engine.calculate(
                    notional=qty * price, asset_class=self._asset_class(symbol).value
                ).fee
                pnl = self.portfolio.close_position(symbol.upper(), quantity=qty, price=price, fee=fee)
                self._emit("PARTIAL_TAKE_PROFIT", symbol=symbol.upper(), quantity=qty, price=price, pnl=pnl)
                partial["done"] = True

        if symbol.upper() not in self.portfolio.positions:
            return
        pos = self.portfolio.positions[symbol.upper()]
        stop = pos.stop_loss
        tp = pos.take_profit
        if pos.side in {"LONG", "BUY"}:
            if stop is not None and price <= stop:
                self._exit_position(symbol, price, reason="STOP_LOSS")
                return
            if tp is not None and price >= tp:
                self._exit_position(symbol, price, reason="TAKE_PROFIT")
                return
        else:
            if stop is not None and price >= stop:
                self._exit_position(symbol, price, reason="STOP_LOSS")
                return
            if tp is not None and price <= tp:
                self._exit_position(symbol, price, reason="TAKE_PROFIT")
                return

        new_stop = self.trailing.update(
            symbol=symbol,
            side=pos.side,
            price=price,
            current_stop=pos.stop_loss,
        )
        if new_stop is not None and new_stop != pos.stop_loss and symbol.upper() in self.portfolio.positions:
            pos.stop_loss = new_stop
            self._emit("STOP_UPDATED", symbol=symbol.upper(), new_stop=new_stop, mode="trailing")

        mr = self._mean_reversion_exit.get(symbol.upper())
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
        fee = self.fee_engine.calculate(
            notional=pos.quantity * price, asset_class=self._asset_class(symbol).value
        ).fee
        pnl = self.portfolio.close_position(symbol.upper(), price=price, fee=fee)
        self._emit("POSITION_CLOSED", symbol=symbol.upper(), reason=reason, price=price, pnl=pnl)
        self._emit("PAPER_PNL_UPDATED", symbol=symbol.upper(), pnl=pnl)
        self._record_trade_close(pos, price, fee, pnl, reason)

    def _record_trade(self, order: Order, qty: float, price: float, fee: float, slip: float, pnl: float) -> None:
        self.trades.append(
            {
                "trade_id": f"TRD-{self.session_id}-{len(self.trades)+1:06d}",
                "order_id": order.order_id,
                "session_id": self.session_id,
                "exchange": self.name,
                "instrument": order.symbol,
                "asset_class": order.instrument_type.value,
                "strategy_id": order.strategy_id,
                "strategy_version": order.strategy_version,
                "strategy_config_hash": order.strategy_config_hash,
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
                "reason_for_entry": order.metadata.get("entry_reasoning"),
                "reason_for_exit": "CLOSE",
            }
        )

    def _record_trade_close(self, pos: Position, price: float, fee: float, pnl: float, reason: str) -> None:
        self.trades.append(
            {
                "trade_id": f"TRD-{self.session_id}-{len(self.trades)+1:06d}",
                "order_id": None,
                "session_id": self.session_id,
                "exchange": self.name,
                "instrument": pos.symbol,
                "asset_class": self._asset_class(pos.symbol).value,
                "strategy_id": pos.strategy_id,
                "strategy_version": pos.strategy_version,
                "strategy_config_hash": None,
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
        trailing_pct: float | None = None,
        trailing_distance: float | None = None,
        mean_reversion_sma: float | None = None,
        allow_widen: bool = False,
    ) -> None:
        sym = symbol.upper()
        self._be_flags[sym] = move_be_at_1r
        if partial_tp_pct is not None:
            self._partial_tp[sym] = {"exit_quantity_percent": partial_tp_pct, "done": False}
        if trailing_atr is not None:
            self.trailing.configure(
                sym,
                TrailingStopState(
                    mode="atr",
                    atr=trailing_atr,
                    multiplier=trailing_mult,
                    allow_widen=allow_widen,
                ),
            )
        if trailing_pct is not None:
            self.trailing.configure(
                sym,
                TrailingStopState(mode="percentage", percentage=trailing_pct, allow_widen=allow_widen),
            )
        if trailing_distance is not None:
            self.trailing.configure(
                sym,
                TrailingStopState(mode="fixed_distance", distance=trailing_distance, allow_widen=allow_widen),
            )
        if mean_reversion_sma is not None:
            self._mean_reversion_exit[sym] = {"sma_20": mean_reversion_sma}

    def record_api_failure(self) -> None:
        self.api_failures += 1
        paper = self.config.get("paper") or self.config.get("paper_trading") or {}
        max_fail = int(paper.get("max_consecutive_api_failures", 3))
        if self.api_failures >= max_fail:
            self.halted = True
            self.halt_reason = "API_FAILURE_CIRCUIT_BREAKER"
            self._emit("CIRCUIT_BREAKER_TRIGGERED", failures=self.api_failures)

    def record_api_success(self) -> None:
        self.api_failures = 0

    def halt(self, reason: str) -> None:
        self.halted = True
        self.halt_reason = reason
        if reason.startswith("KILL"):
            self._emit("KILL_SWITCH_TRIGGERED", reason=reason)

    def reset_halt(self) -> None:
        self.halted = False
        self.halt_reason = None
        self.api_failures = 0
        self.failure_mode = None
