from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx


class LocalDeltaSandboxHarness:
    """Deterministic HTTP transport stand-in for Delta TESTNET.

    This is a CI/local harness, not a claim of live Delta testnet connectivity.
    Labelled NOT a production exchange. Used when real sandbox credentials are absent.
    """

    def __init__(self) -> None:
        self.orders: dict[str, dict[str, Any]] = {}
        self.balances = [{"asset_symbol": "USDT", "available_balance": "10000", "order_margin": "0"}]
        self.positions: list[dict[str, Any]] = []
        self.authenticated = False
        self.calls: list[str] = []

    def __call__(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        self.calls.append(f"{method} {url}")
        path = url.split("://", 1)[-1]
        path = "/" + path.split("/", 1)[-1] if "/" in path else "/"
        # strip host
        if "://" in url:
            path = "/" + url.split("://", 1)[1].split("/", 1)[-1]
        headers = kwargs.get("headers") or {}
        content = kwargs.get("content")

        if path.startswith("/v2/tickers"):
            return httpx.Response(200, json={"result": {"close": "100.0", "mark_price": "100.0"}})
        if path.startswith("/v2/l2orderbook"):
            return httpx.Response(200, json={"result": {"buy": [], "sell": []}})
        if path.startswith("/v2/products"):
            return httpx.Response(200, json={"result": {"symbol": "BTCUSD"}})
        if path.startswith("/v2/wallet/balances"):
            if not headers.get("signature") and not headers.get("api-key"):
                return httpx.Response(401, json={"error": "unauthorized"})
            self.authenticated = True
            return httpx.Response(200, json={"result": self.balances})
        if path.startswith("/v2/positions"):
            return httpx.Response(200, json={"result": self.positions})
        if path == "/v2/orders" and method.upper() == "GET":
            opens = [o for o in self.orders.values() if o.get("status") in {"open", "partial"}]
            return httpx.Response(200, json={"result": opens})
        if path.startswith("/v2/orders/history"):
            return httpx.Response(200, json={"result": list(self.orders.values())})
        if path.startswith("/v2/orders/") and method.upper() == "GET":
            oid = path.rstrip("/").split("/")[-1]
            order = self.orders.get(oid) or {"id": oid, "status": "closed", "product_symbol": "BTCUSD", "side": "buy", "size": 0}
            return httpx.Response(200, json={"result": order})
        if path == "/v2/orders" and method.upper() == "POST":
            body = json.loads(content or "{}")
            oid = f"SBX-{uuid4().hex[:10]}"
            order = {
                "id": oid,
                "product_symbol": body.get("product_symbol") or "BTCUSD",
                "side": body.get("side") or "buy",
                "size": body.get("size") or 0,
                "order_type": body.get("order_type") or "market",
                "status": "open",
                "created_at": datetime.now(UTC).isoformat(),
            }
            self.orders[oid] = order
            # immediate fill simulation for market
            if str(body.get("order_type") or "market").lower() == "market":
                order["status"] = "closed"
                order["filled_size"] = order["size"]
                self.positions = [
                    {
                        "product_symbol": order["product_symbol"],
                        "size": order["size"],
                        "entry_price": 100.0,
                    }
                ]
            return httpx.Response(200, json={"result": order})
        if path.startswith("/v2/orders/") and method.upper() == "DELETE":
            oid = path.rstrip("/").split("/")[-1]
            if oid in self.orders:
                self.orders[oid]["status"] = "cancelled"
            return httpx.Response(200, json={"result": {"id": oid, "status": "cancelled", "product_symbol": "BTCUSD"}})
        return httpx.Response(404, json={"error": "not_found", "path": path})
