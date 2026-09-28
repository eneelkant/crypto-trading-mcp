from __future__ import annotations

import json
import os
from typing import Any, Callable

import httpx

from crypto_trading_mcp.config.settings import get_settings
from crypto_trading_mcp.credentials.models import ExchangeEnvironment
from crypto_trading_mcp.exchange.auth import delta_india_signature, utc_timestamp_ms
from crypto_trading_mcp.exchange.base import ExchangeAdapter
from crypto_trading_mcp.exchange.exceptions import LiveExecutionBlocked
from crypto_trading_mcp.exchange.health import ExchangeHealth
from crypto_trading_mcp.exchange.models import Balance, Order, OrderSide, OrderType


class DeltaExchangeIndiaAdapter(ExchangeAdapter):
    """Delta Exchange India adapter with HMAC-SHA256 auth. Live prod orders gated."""

    name = "delta_india"
    supports_live_execution = True

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        api_secret: str | None = None,
        transport: Callable[..., httpx.Response] | None = None,
        environment: ExchangeEnvironment | str = ExchangeEnvironment.MOCK,
        max_clock_skew_seconds: int = 30,
    ) -> None:
        self.base_url = (
            base_url
            or os.getenv("DELTA_API_BASE_URL")
            or "https://api.india.delta.exchange"
        ).rstrip("/")
        self.api_key = api_key if api_key is not None else os.getenv("DELTA_API_KEY")
        self.api_secret = api_secret if api_secret is not None else os.getenv("DELTA_API_SECRET")
        self._transport = transport
        self.health = ExchangeHealth(self.name)
        if isinstance(environment, str):
            environment = ExchangeEnvironment(environment)
        self.environment = environment
        self.max_clock_skew_seconds = max_clock_skew_seconds

    def _assert_live_orders_allowed(self) -> None:
        settings = get_settings()
        if self.environment in {ExchangeEnvironment.SANDBOX, ExchangeEnvironment.TESTNET}:
            if self._transport is None:
                raise LiveExecutionBlocked(
                    "Delta sandbox/testnet orders require injected transport mocks"
                )
            return
        if settings.trading_mode != "live" or not settings.live_trading_enabled:
            raise LiveExecutionBlocked(
                "Delta India live order execution blocked: "
                "TRADING_MODE must be live and LIVE_TRADING_ENABLED=true"
            )
        if self.environment != ExchangeEnvironment.PRODUCTION_TRADING:
            raise LiveExecutionBlocked(
                f"Delta orders blocked in environment {self.environment.value}"
            )
        raise LiveExecutionBlocked("Delta India production create/cancel not enabled")

    def sign(
        self,
        *,
        method: str,
        request_path: str,
        query_params: str = "",
        body: str = "",
        timestamp: str | None = None,
    ) -> dict[str, str]:
        if not self.api_secret or not self.api_key:
            raise LiveExecutionBlocked("Delta India credentials not configured")
        ts = timestamp or utc_timestamp_ms()
        # Basic clock skew guard for provided timestamps
        try:
            skew = abs(int(time_ms()) - int(ts)) / 1000.0
            if skew > self.max_clock_skew_seconds:
                raise LiveExecutionBlocked("LIVE_GATE_CLOCK_SKEW")
        except LiveExecutionBlocked:
            raise
        except Exception:
            pass
        signature = delta_india_signature(
            secret=self.api_secret,
            method=method,
            timestamp=ts,
            request_path=request_path,
            query_params=query_params,
            body=body,
        )
        return {
            "api-key": self.api_key,
            "timestamp": ts,
            "signature": signature,
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        auth: bool = False,
        query_params: str = "",
        body: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        headers = dict(kwargs.pop("headers", {}) or {})
        if auth:
            headers.update(
                self.sign(
                    method=method,
                    request_path=path,
                    query_params=query_params,
                    body=body,
                )
            )
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
        return self._request("GET", f"/v2/tickers/{symbol}")

    def get_market_price(self, symbol: str) -> float:
        data = self.get_ticker(symbol)
        result = data.get("result") or data
        return float(result.get("close") or result.get("mark_price") or result.get("last") or 0.0)

    def get_orderbook(self, symbol: str, limit: int = 20) -> dict[str, Any]:
        return self._request("GET", f"/v2/l2orderbook/{symbol}", params={"depth": limit})

    def get_market_info(self, symbol: str) -> dict[str, Any]:
        return self._request("GET", f"/v2/products/{symbol}")

    def get_account(self) -> dict[str, Any]:
        if not self.api_key:
            return {"balances": [], "note": "no_credentials", "TRADING_MODE": "paper"}
        return self._request("GET", "/v2/wallet/balances", auth=True)

    def get_balances(self) -> list[Balance]:
        return self.get_balance()

    def get_balance(self) -> list[Balance]:
        account = self.get_account()
        rows = account.get("result") or account.get("balances") or []
        out: list[Balance] = []
        if isinstance(rows, list):
            for row in rows:
                asset = str(row.get("asset_symbol") or row.get("currency") or "USD")
                free = float(row.get("available_balance") or row.get("free") or 0.0)
                used = float(row.get("order_margin") or row.get("used") or 0.0)
                out.append(Balance(currency=asset, free=free, locked=used))
        return out

    def get_positions(self) -> list[dict[str, Any]]:
        if not self.api_key:
            return []
        data = self._request("GET", "/v2/positions", auth=True)
        result = data.get("result") or []
        return result if isinstance(result, list) else []

    def get_open_orders(self, symbol: str | None = None) -> list[Order]:
        if not self.api_key:
            return []
        data = self._request("GET", "/v2/orders", auth=True)
        rows = data.get("result") or []
        out: list[Order] = []
        for row in rows if isinstance(rows, list) else []:
            if symbol and str(row.get("product_symbol") or row.get("symbol")) != symbol:
                continue
            side_raw = str(row.get("side") or "buy").upper()
            type_raw = str(row.get("order_type") or "limit").upper()
            px = row.get("limit_price") or row.get("price")
            out.append(
                Order(
                    order_id=str(row.get("id") or ""),
                    symbol=str(row.get("product_symbol") or row.get("symbol") or ""),
                    side=OrderSide.BUY if side_raw.startswith("BUY") else OrderSide.SELL,
                    quantity=float(row.get("size") or row.get("quantity") or 0),
                    order_type=OrderType.MARKET if type_raw == "MARKET" else OrderType.LIMIT,
                    limit_price=float(px) if px is not None else None,
                )
            )
        return out

    def get_order_history(self, symbol: str | None = None) -> list[dict[str, Any]]:
        if not self.api_key:
            return []
        data = self._request("GET", "/v2/orders/history", auth=True)
        rows = data.get("result") or []
        return rows if isinstance(rows, list) else []

    def get_order(self, order_id: str) -> Order:
        data = self._request("GET", f"/v2/orders/{order_id}", auth=True)
        row = data.get("result") or data
        side_raw = str(row.get("side") or "buy").upper()
        type_raw = str(row.get("order_type") or "limit").upper()
        return Order(
            order_id=str(row.get("id") or order_id),
            symbol=str(row.get("product_symbol") or row.get("symbol") or ""),
            side=OrderSide.BUY if side_raw.startswith("BUY") else OrderSide.SELL,
            quantity=float(row.get("size") or 0),
            order_type=OrderType.MARKET if type_raw == "MARKET" else OrderType.LIMIT,
            limit_price=float(row.get("limit_price") or 0) if row.get("limit_price") else None,
        )

    def submit_order(self, order: Order, market_price: float | None = None) -> Order:
        return self.create_order(order, market_price=market_price)

    def create_order(self, order: Order, market_price: float | None = None) -> Order:
        self._assert_live_orders_allowed()
        body = json.dumps(
            {
                "product_symbol": order.symbol,
                "side": order.side.lower(),
                "size": order.quantity,
                "order_type": (order.order_type or "market").lower(),
            }
        )
        data = self._request("POST", "/v2/orders", auth=True, body=body)
        row = data.get("result") or data
        return Order(
            order_id=str(row.get("id") or order.order_id or "delta-sim"),
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            order_type=order.order_type,
            limit_price=order.limit_price,
        )

    def cancel_order(self, order_id: str) -> Order:
        self._assert_live_orders_allowed()
        data = self._request("DELETE", f"/v2/orders/{order_id}", auth=True)
        row = data.get("result") or data
        return Order(
            order_id=str(row.get("id") or order_id),
            symbol=str(row.get("product_symbol") or "BTCUSD"),
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


def time_ms() -> int:
    import time

    return int(time.time() * 1000)
