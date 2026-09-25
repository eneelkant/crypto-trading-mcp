from __future__ import annotations

import os
from typing import Any, Callable

import httpx

from crypto_trading_mcp.config.settings import get_settings
from crypto_trading_mcp.exchange.base import ExchangeAdapter
from crypto_trading_mcp.exchange.exceptions import LiveExecutionBlocked
from crypto_trading_mcp.exchange.health import ExchangeHealth
from crypto_trading_mcp.exchange.models import Balance, Order


class CoinbaseAdapter(ExchangeAdapter):
    """Coinbase adapter. Public market data OK; live orders blocked unless enabled."""

    name = "coinbase"
    supports_live_execution = True

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        api_secret: str | None = None,
        transport: Callable[..., httpx.Response] | None = None,
    ) -> None:
        self.base_url = (base_url or "https://api.coinbase.com").rstrip("/")
        self.api_key = api_key if api_key is not None else os.getenv("COINBASE_API_KEY")
        self.api_secret = api_secret if api_secret is not None else os.getenv("COINBASE_API_SECRET")
        self._transport = transport
        self.health = ExchangeHealth(self.name)

    def _assert_live_orders_allowed(self) -> None:
        settings = get_settings()
        if settings.trading_mode != "live" or not settings.live_trading_enabled:
            raise LiveExecutionBlocked(
                "Coinbase live order execution blocked: "
                "TRADING_MODE must be live and LIVE_TRADING_ENABLED=true"
            )

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            if self._transport is not None:
                response = self._transport(method, url, **kwargs)
            else:
                response = httpx.request(method, url, timeout=10.0, **kwargs)
            if getattr(response, "status_code", 200) >= 400:
                raise RuntimeError(f"HTTP {response.status_code}")
            data = response.json()
            self.health.mark_ok()
            return data if isinstance(data, dict) else {"data": data}
        except Exception as exc:  # noqa: BLE001
            self.health.mark_error(str(exc))
            raise

    # --- public market data ---
    def get_ticker(self, symbol: str) -> dict[str, Any]:
        # public endpoint shape varies; transport/mocks supply fixtures
        return self._request("GET", f"/api/v3/brokerage/market/products/{symbol}/ticker")

    def get_market_price(self, symbol: str) -> float:
        data = self.get_ticker(symbol)
        price = data.get("price") or data.get("last") or data.get("trade_id")
        if price is None and isinstance(data.get("trades"), list) and data["trades"]:
            price = data["trades"][0].get("price")
        return float(price or 0.0)

    def get_orderbook(self, symbol: str, limit: int = 20) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/api/v3/brokerage/market/product_book",
            params={"product_id": symbol, "limit": limit},
        )

    def get_market_info(self, symbol: str) -> dict[str, Any]:
        return self._request("GET", f"/api/v3/brokerage/market/products/{symbol}")

    # --- authenticated (still blocked for orders in paper) ---
    def get_account(self) -> dict[str, Any]:
        if not self.api_key:
            return {"balances": [], "note": "no_credentials", "TRADING_MODE": "paper"}
        return self._request("GET", "/api/v3/brokerage/accounts")

    def get_balances(self) -> list[Balance]:
        return self.get_balance()

    def get_balance(self) -> list[Balance]:
        account = self.get_account()
        rows = account.get("accounts") or account.get("balances") or []
        out: list[Balance] = []
        for row in rows:
            currency = str(row.get("currency") or row.get("available_balance", {}).get("currency") or "USD")
            avail = row.get("available_balance", {})
            free = float(avail.get("value") or row.get("available") or row.get("free") or 0.0)
            out.append(Balance(currency=currency, free=free, locked=0.0))
        return out

    def get_positions(self) -> list[dict[str, Any]]:
        return []

    def get_open_orders(self, symbol: str | None = None) -> list[Order]:
        return []

    def get_order_history(self, symbol: str | None = None) -> list[dict[str, Any]]:
        return []

    def submit_order(self, order: Order, market_price: float | None = None) -> Order:
        return self.create_order(order, market_price=market_price)

    def create_order(self, order: Order, market_price: float | None = None) -> Order:
        self._assert_live_orders_allowed()
        raise LiveExecutionBlocked("Coinbase live create_order not enabled in Phase 9")

    def cancel_order(self, order_id: str) -> Order:
        self._assert_live_orders_allowed()
        raise LiveExecutionBlocked("Coinbase live cancel_order not enabled in Phase 9")

    def get_order(self, order_id: str) -> Order:
        raise LiveExecutionBlocked("Coinbase authenticated get_order requires live mode")

    def status(self) -> dict[str, Any]:
        return self.health.status()
