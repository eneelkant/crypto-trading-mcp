from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from typing import Any, Callable

import httpx

from crypto_trading_mcp.config.settings import get_settings
from crypto_trading_mcp.credentials.models import ExchangeEnvironment
from crypto_trading_mcp.exchange.base import ExchangeAdapter
from crypto_trading_mcp.exchange.exceptions import LiveExecutionBlocked
from crypto_trading_mcp.exchange.health import ExchangeHealth
from crypto_trading_mcp.exchange.models import Balance, Order, OrderSide, OrderType


class CoinbaseAdapter(ExchangeAdapter):
    """Coinbase adapter with auth architecture; production orders remain gated."""

    name = "coinbase"
    supports_live_execution = True

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        api_secret: str | None = None,
        transport: Callable[..., httpx.Response] | None = None,
        environment: ExchangeEnvironment | str = ExchangeEnvironment.MOCK,
    ) -> None:
        self.base_url = (base_url or "https://api.coinbase.com").rstrip("/")
        self.api_key = api_key if api_key is not None else os.getenv("COINBASE_API_KEY")
        self.api_secret = api_secret if api_secret is not None else os.getenv("COINBASE_API_SECRET")
        self._transport = transport
        self.health = ExchangeHealth(self.name)
        if isinstance(environment, str):
            environment = ExchangeEnvironment(environment)
        self.environment = environment

    def _assert_live_orders_allowed(self) -> None:
        settings = get_settings()
        # SANDBOX/TESTNET may exercise order lifecycle via injected transport only.
        if self.environment in {ExchangeEnvironment.SANDBOX, ExchangeEnvironment.TESTNET}:
            if self._transport is None:
                raise LiveExecutionBlocked(
                    "Coinbase sandbox/testnet orders require injected transport mocks"
                )
            return
        if settings.trading_mode != "live" or not settings.live_trading_enabled:
            raise LiveExecutionBlocked(
                "Coinbase live order execution blocked: "
                "TRADING_MODE must be live and LIVE_TRADING_ENABLED=true"
            )
        if self.environment != ExchangeEnvironment.PRODUCTION_TRADING:
            raise LiveExecutionBlocked(
                f"Coinbase orders blocked in environment {self.environment.value}"
            )
        raise LiveExecutionBlocked("Coinbase production create/cancel not enabled")

    def sign(self, method: str, path: str, body: str = "", timestamp: str | None = None) -> dict[str, str]:
        """HMAC signature helper for authenticated Coinbase-style requests.

        Production Advanced Trade often uses JWT; this provides a testable HMAC
        envelope and keeps secrets out of return values beyond headers for transport.
        """
        if not self.api_key or not self.api_secret:
            raise LiveExecutionBlocked("Coinbase credentials not configured")
        ts = timestamp or str(int(time.time()))
        message = f"{ts}{method.upper()}{path}{body}"
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return {
            "CB-ACCESS-KEY": self.api_key,
            "CB-ACCESS-SIGN": signature,
            "CB-ACCESS-TIMESTAMP": ts,
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        auth: bool = False,
        body: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        headers = dict(kwargs.pop("headers", {}) or {})
        if auth:
            headers.update(self.sign(method, path, body=body))
        try:
            if self._transport is not None:
                response = self._transport(
                    method, url, headers=headers, content=body or None, **kwargs
                )
            else:
                response = httpx.request(
                    method, url, headers=headers, content=body or None, timeout=10.0, **kwargs
                )
            if getattr(response, "status_code", 200) >= 400:
                raise RuntimeError(f"HTTP {response.status_code}")
            data = response.json()
            self.health.mark_ok()
            return data if isinstance(data, dict) else {"data": data}
        except Exception as exc:  # noqa: BLE001
            self.health.mark_error(str(exc))
            raise

    def get_ticker(self, symbol: str) -> dict[str, Any]:
        return self._request("GET", f"/api/v3/brokerage/market/products/{symbol}/ticker")

    def get_market_price(self, symbol: str) -> float:
        data = self.get_ticker(symbol)
        price = data.get("price") or data.get("last")
        if price is None and isinstance(data.get("trades"), list) and data["trades"]:
            price = data["trades"][0].get("price")
        return float(price or 0.0)

    def get_orderbook(self, symbol: str, limit: int = 20) -> dict[str, Any]:
        return self._request(
            "GET",
            "/api/v3/brokerage/market/product_book",
            params={"product_id": symbol, "limit": limit},
        )

    def get_market_info(self, symbol: str) -> dict[str, Any]:
        return self._request("GET", f"/api/v3/brokerage/market/products/{symbol}")

    def get_account(self) -> dict[str, Any]:
        if not self.api_key:
            return {"balances": [], "note": "no_credentials", "TRADING_MODE": "paper"}
        return self._request("GET", "/api/v3/brokerage/accounts", auth=True)

    def get_balances(self) -> list[Balance]:
        return self.get_balance()

    def get_balance(self) -> list[Balance]:
        account = self.get_account()
        rows = account.get("accounts") or account.get("balances") or []
        out: list[Balance] = []
        for row in rows:
            currency = str(
                row.get("currency")
                or row.get("available_balance", {}).get("currency")
                or "USD"
            )
            avail = row.get("available_balance", {})
            free = float(avail.get("value") or row.get("available") or row.get("free") or 0.0)
            locked = float(row.get("hold", {}).get("value") or row.get("locked") or 0.0)
            out.append(Balance(currency=currency, free=free, locked=locked))
        return out

    def get_positions(self) -> list[dict[str, Any]]:
        # Spot-oriented; futures products would extend this.
        if not self.api_key:
            return []
        data = self._request("GET", "/api/v3/brokerage/accounts", auth=True)
        return data.get("positions") or []

    def get_open_orders(self, symbol: str | None = None) -> list[Order]:
        if not self.api_key:
            return []
        data = self._request("GET", "/api/v3/brokerage/orders/historical/batch", auth=True)
        rows = data.get("orders") or data.get("result") or []
        out: list[Order] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            if symbol and str(row.get("symbol") or row.get("product_id")) != symbol:
                continue
            side_raw = str(row.get("side") or "BUY").upper()
            type_raw = str(row.get("order_type") or "LIMIT").upper()
            out.append(
                Order(
                    order_id=str(row.get("order_id") or row.get("id") or ""),
                    symbol=str(row.get("symbol") or row.get("product_id") or ""),
                    side=OrderSide.BUY if side_raw.startswith("BUY") else OrderSide.SELL,
                    quantity=float(row.get("quantity") or row.get("size") or 0),
                    order_type=OrderType.MARKET if type_raw == "MARKET" else OrderType.LIMIT,
                    limit_price=float(row.get("price") or 0) if row.get("price") is not None else None,
                )
            )
        return out

    def get_order_history(self, symbol: str | None = None) -> list[dict[str, Any]]:
        if not self.api_key:
            return []
        data = self._request("GET", "/api/v3/brokerage/orders/historical/batch", auth=True)
        rows = data.get("orders") or []
        return rows if isinstance(rows, list) else []

    def get_order(self, order_id: str) -> Order:
        if self.environment == ExchangeEnvironment.PRODUCTION_TRADING:
            settings = get_settings()
            if settings.trading_mode != "live" or not settings.live_trading_enabled:
                raise LiveExecutionBlocked("Coinbase authenticated get_order requires live mode")
        data = self._request("GET", f"/api/v3/brokerage/orders/historical/{order_id}", auth=True)
        row = data.get("order") or data
        side_raw = str(row.get("side") or "BUY").upper()
        type_raw = str(row.get("order_type") or "LIMIT").upper()
        px = row.get("average_filled_price") or row.get("price")
        return Order(
            order_id=str(row.get("order_id") or order_id),
            symbol=str(row.get("product_id") or row.get("symbol") or ""),
            side=OrderSide.BUY if side_raw.startswith("BUY") else OrderSide.SELL,
            quantity=float(row.get("filled_size") or row.get("quantity") or 0),
            order_type=OrderType.MARKET if type_raw == "MARKET" else OrderType.LIMIT,
            limit_price=float(px) if px is not None else None,
        )

    def submit_order(self, order: Order, market_price: float | None = None) -> Order:
        return self.create_order(order, market_price=market_price)

    def create_order(self, order: Order, market_price: float | None = None) -> Order:
        self._assert_live_orders_allowed()
        body = json.dumps(
            {
                "product_id": order.symbol,
                "side": order.side,
                "size": order.quantity,
            }
        )
        data = self._request("POST", "/api/v3/brokerage/orders", auth=True, body=body)
        return Order(
            order_id=str(data.get("order_id") or data.get("id") or order.order_id or "cb-sim"),
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            order_type=order.order_type,
            limit_price=order.limit_price,
        )

    def cancel_order(self, order_id: str) -> Order:
        self._assert_live_orders_allowed()
        data = self._request(
            "POST",
            "/api/v3/brokerage/orders/batch_cancel",
            auth=True,
            body=json.dumps({"order_ids": [order_id]}),
        )
        return Order(
            order_id=order_id,
            symbol=str(data.get("symbol") or "BTC-USD"),
            side=OrderSide.BUY,
            quantity=0.0,
            order_type=OrderType.LIMIT,
        )

    def cancel_all_open_orders(self) -> dict[str, Any]:
        opens = self.get_open_orders()
        failures: list[str] = []
        cancelled: list[str] = []
        for order in opens:
            try:
                oid = order.order_id or ""
                self.cancel_order(oid)
                cancelled.append(oid)
            except Exception as exc:  # noqa: BLE001
                failures.append(str(exc))
        return {"cancelled": cancelled, "failures": failures}

    def status(self) -> dict[str, Any]:
        base = self.health.status()
        base.update(
            {
                "environment": self.environment.value,
                "has_api_key": bool(self.api_key),
                "LIVE_TRADING_ENABLED": False,
            }
        )
        return base
