from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable
from uuid import uuid4

import httpx

from crypto_trading_mcp.credentials.models import ExchangeEnvironment
from crypto_trading_mcp.exchange.delta_india import DeltaExchangeIndiaAdapter
from crypto_trading_mcp.exchange.models import Order, OrderSide, OrderType
from crypto_trading_mcp.live.stages import TradingStage
from crypto_trading_mcp.sandbox.endpoints import (
    SandboxEndpointError,
    SandboxEndpointGuard,
    load_sandbox_config,
)
from crypto_trading_mcp.sandbox.harness import LocalDeltaSandboxHarness
from crypto_trading_mcp.sandbox.testnet_credentials import resolve_testnet_credentials


class DeltaIndiaSandboxAdapter:
    """Stage-2 / Stage-2.1 Delta India TESTNET adapter with production endpoint rejection."""

    name = "delta_india_sandbox"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        api_secret: str | None = None,
        transport: Callable[..., httpx.Response] | None = None,
        stage: TradingStage = TradingStage.STAGE_2_CLOUD_PAPER,
        use_local_harness: bool = False,
        allow_real_testnet_http: bool = False,
        resolve_env_credentials: bool = False,
    ) -> None:
        cfg = load_sandbox_config()
        venue = dict(cfg.get("delta_india") or {})
        default_url = str(venue.get("default_base_url") or "https://cdn-ind.testnet.deltaex.org")
        self.stage = stage
        self.guard = SandboxEndpointGuard(cfg)
        self.mode = "HARNESS"
        creds = None
        if resolve_env_credentials or allow_real_testnet_http:
            creds = resolve_testnet_credentials()
            if base_url is None:
                base_url = creds.base_url
            if api_key is None and creds.configured:
                api_key = creds.api_key
            if api_secret is None and creds.configured:
                api_secret = creds.api_secret
        self.base_url = (base_url or default_url).rstrip("/")
        self.guard.validate(self.base_url, stage=stage, environment="TESTNET")

        # Prefer harness when explicitly requested, or when real HTTP not allowed /
        # credentials missing.
        if use_local_harness and transport is None:
            transport = LocalDeltaSandboxHarness()
            self.mode = "HARNESS"
        elif allow_real_testnet_http and transport is None:
            if not (api_key and api_secret):
                # Fail safe: do not invent production; fall back to harness only
                # when caller did not require real HTTP exclusively.
                transport = LocalDeltaSandboxHarness()
                self.mode = "HARNESS_FALLBACK_NO_CREDS"
                allow_real_testnet_http = False
            else:
                self.mode = "REAL_TESTNET"
        elif transport is None and not allow_real_testnet_http:
            # Default CI-safe path
            transport = LocalDeltaSandboxHarness()
            self.mode = "HARNESS"

        self._inner = DeltaExchangeIndiaAdapter(
            base_url=self.base_url,
            api_key=api_key or "sandbox-key",
            api_secret=api_secret or "sandbox-secret",
            transport=transport,
            environment=ExchangeEnvironment.TESTNET,
            max_clock_skew_seconds=5,
            allow_real_testnet_http=allow_real_testnet_http and transport is None,
        )
        # If real HTTP mode with credentials, transport is None and allow_real=True
        if self.mode == "REAL_TESTNET":
            self._inner.allow_real_testnet_http = True
            self._inner._transport = None
        self.request_log: list[dict[str, Any]] = []
        self.credential_source = creds.source if creds else "explicit_or_harness"

    def _req_meta(self, op: str) -> dict[str, Any]:
        meta = {
            "request_id": f"REQ-{uuid4().hex[:12]}",
            "op": op,
            "timestamp": datetime.now(UTC).isoformat(),
            "venue": self.name,
            "base_url": self.base_url,
            "mode": self.mode,
        }
        self.request_log.append({"request_id": meta["request_id"], "op": op})
        return meta

    def authenticate(self) -> dict[str, Any]:
        meta = self._req_meta("authenticate")
        headers = self._inner.sign(method="GET", request_path="/v2/wallet/balances")
        bals = self._inner.get_balance()
        return {
            **meta,
            "authenticated": bool(headers.get("signature")),
            "balance_count": len(bals),
            "environment": "TESTNET",
            "LIVE_TRADING_ENABLED": False,
            # Never include api-key/signature values
            "has_signature": bool(headers.get("signature")),
        }

    def health_check(self) -> dict[str, Any]:
        meta = self._req_meta("health_check")
        try:
            price = self._inner.get_market_price("BTCUSD")
            st = self._inner.status()
            ok = price >= 0 and st.get("ok", True) is not False
            return {**meta, "ok": ok, "last_price": price, "exchange_status": st}
        except Exception as exc:  # noqa: BLE001
            return {**meta, "ok": False, "error": str(exc)}

    def get_account(self) -> dict[str, Any]:
        meta = self._req_meta("get_account")
        data = self._inner.get_account()
        return {**meta, "account": data}

    def get_balances(self) -> list[dict[str, Any]]:
        self._req_meta("get_balances")
        return [b.model_dump() for b in self._inner.get_balance()]

    def get_positions(self) -> list[dict[str, Any]]:
        self._req_meta("get_positions")
        return self._inner.get_positions()

    def get_open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        self._req_meta("get_open_orders")
        return [o.model_dump(mode="json") for o in self._inner.get_open_orders(symbol)]

    def get_order_status(self, order_id: str) -> dict[str, Any]:
        meta = self._req_meta("get_order_status")
        order = self._inner.get_order(order_id)
        return {**meta, "order": order.model_dump(mode="json")}

    def list_instruments(self) -> list[dict[str, Any]]:
        self._req_meta("list_instruments")
        return self._inner.list_products()

    def discover_test_instrument(self) -> dict[str, Any]:
        """Pick a live testnet instrument with a minimum size (no production assumption)."""
        products = self.list_instruments()
        for row in products:
            if not isinstance(row, dict):
                continue
            state = str(row.get("state") or row.get("trading_status") or "").lower()
            symbol = str(row.get("symbol") or row.get("product_symbol") or "")
            if not symbol:
                continue
            if state and state not in {"live", "operational", "active", ""}:
                continue
            min_size = float(row.get("min_size") or row.get("minimum_quantity") or 1)
            return {
                "symbol": symbol,
                "min_size": min_size,
                "raw_keys": sorted(row.keys()),
                "mode": self.mode,
            }
        return {"symbol": None, "min_size": None, "error": "NO_TESTNET_INSTRUMENT", "mode": self.mode}

    def submit_order(
        self,
        *,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str = "MARKET",
        price: float | None = None,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        meta = self._req_meta("submit_order")
        order = Order(
            client_order_id=client_order_id,
            symbol=symbol,
            side=OrderSide.BUY if side.upper().startswith("BUY") else OrderSide.SELL,
            order_type=OrderType.MARKET if order_type.upper() == "MARKET" else OrderType.LIMIT,
            quantity=quantity,
            limit_price=price,
        )
        try:
            submitted = self._inner.create_order(order)
            return {
                **meta,
                "accepted": True,
                "exchange_order_id": submitted.order_id,
                "order": submitted.model_dump(mode="json"),
                "ambiguous": False,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                **meta,
                "accepted": False,
                "ambiguous": True,
                "error": str(exc),
                "action": "RECONCILE_BEFORE_RETRY",
            }

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        meta = self._req_meta("cancel_order")
        cancelled = self._inner.cancel_order(order_id)
        return {**meta, "order": cancelled.model_dump(mode="json"), "success": True}

    def cancel_all_orders(self) -> dict[str, Any]:
        meta = self._req_meta("cancel_all_orders")
        result = self._inner.cancel_all_open_orders()
        return {**meta, **result}

    def reject_production_url(self, url: str) -> None:
        self.guard.validate(url, stage=self.stage, environment="TESTNET")

    def server_time(self) -> dict[str, Any]:
        return self._inner.get_server_time()


def assert_not_production_credential_env(environment: str) -> None:
    if environment.upper() in {"PRODUCTION", "PRODUCTION_TRADING", "PRODUCTION_READ_ONLY"}:
        raise SandboxEndpointError("Production credentials rejected in STAGE_2_CLOUD_PAPER")
