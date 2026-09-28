from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable
from uuid import uuid4

import httpx

from crypto_trading_mcp.credentials.models import ExchangeEnvironment
from crypto_trading_mcp.exchange.delta_india import DeltaExchangeIndiaAdapter
from crypto_trading_mcp.exchange.models import Order, OrderSide, OrderType
from crypto_trading_mcp.live.stages import TradingStage
from crypto_trading_mcp.sandbox.endpoints import SandboxEndpointError, SandboxEndpointGuard, load_sandbox_config
from crypto_trading_mcp.sandbox.harness import LocalDeltaSandboxHarness


class DeltaIndiaSandboxAdapter:
    """Stage-2 Delta India TESTNET adapter with production endpoint rejection."""

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
    ) -> None:
        cfg = load_sandbox_config()
        venue = dict(cfg.get("delta_india") or {})
        default_url = str(venue.get("default_base_url") or "https://cdn-ind.testnet.deltaex.org")
        self.stage = stage
        self.guard = SandboxEndpointGuard(cfg)
        self.base_url = (base_url or default_url).rstrip("/")
        self.guard.validate(self.base_url, stage=stage, environment="TESTNET")
        if use_local_harness and transport is None:
            transport = LocalDeltaSandboxHarness()
        self._inner = DeltaExchangeIndiaAdapter(
            base_url=self.base_url,
            api_key=api_key or "sandbox-key",
            api_secret=api_secret or "sandbox-secret",
            transport=transport,
            environment=ExchangeEnvironment.TESTNET,
        )
        self.request_log: list[dict[str, Any]] = []

    def _req_meta(self, op: str) -> dict[str, Any]:
        meta = {
            "request_id": f"REQ-{uuid4().hex[:12]}",
            "op": op,
            "timestamp": datetime.now(UTC).isoformat(),
            "venue": self.name,
            "base_url": self.base_url,
        }
        self.request_log.append({"request_id": meta["request_id"], "op": op})
        return meta

    def authenticate(self) -> dict[str, Any]:
        meta = self._req_meta("authenticate")
        # Signing material proves key presence; fetch balances as auth check.
        headers = self._inner.sign(method="GET", request_path="/v2/wallet/balances")
        bals = self._inner.get_balance()
        return {
            **meta,
            "authenticated": bool(headers.get("signature")),
            "balance_count": len(bals),
            "environment": "TESTNET",
            "LIVE_TRADING_ENABLED": False,
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
            # Ambiguous network-like failures require reconciliation first.
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


def assert_not_production_credential_env(environment: str) -> None:
    if environment.upper() in {"PRODUCTION", "PRODUCTION_TRADING", "PRODUCTION_READ_ONLY"}:
        raise SandboxEndpointError("Production credentials rejected in STAGE_2_CLOUD_PAPER")
