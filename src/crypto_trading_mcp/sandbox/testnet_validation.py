"""Stage 2.1 — real Delta India TESTNET validation runner (paper-safe).

Distinguishes REAL_TESTNET vs HARNESS/MOCK vs NOT_TESTED / NOT_CONFIGURED.
Never prints credentials or signatures.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from crypto_trading_mcp.config.settings import get_settings
from crypto_trading_mcp.exchange.auth import delta_india_signature, utc_timestamp_ms
from crypto_trading_mcp.exchange.delta_india import time_ms
from crypto_trading_mcp.live.stages import TradingStage, TradingStageManager
from crypto_trading_mcp.persistence.sqlite_store import SqliteDurableStore
from crypto_trading_mcp.sandbox.delta_sandbox import DeltaIndiaSandboxAdapter
from crypto_trading_mcp.sandbox.endpoints import SandboxEndpointError, SandboxEndpointGuard
from crypto_trading_mcp.sandbox.execution import SandboxExecutionService
from crypto_trading_mcp.sandbox.testnet_credentials import resolve_testnet_credentials
from crypto_trading_mcp.sandbox.websocket import SandboxWebSocketClient


def _result(status: str, **extra: Any) -> dict[str, Any]:
    return {"status": status, **extra}


class Stage21DeltaTestnetValidator:
    """Controlled Stage 2.1 validation. Production trading remains disabled."""

    PRODUCTION_URL = "https://api.india.delta.exchange"

    def __init__(
        self,
        *,
        force_harness: bool = False,
        store: SqliteDurableStore | None = None,
    ) -> None:
        self.settings = get_settings()
        self.creds = resolve_testnet_credentials()
        self.force_harness = force_harness
        self.store = store or SqliteDurableStore(":memory:")
        self.use_real = (
            (not force_harness)
            and self.creds.configured
            and not self.settings.live_trading_enabled
            and self.settings.trading_mode == "paper"
        )
        self.adapter = DeltaIndiaSandboxAdapter(
            stage=TradingStage.STAGE_2_CLOUD_PAPER,
            use_local_harness=not self.use_real,
            allow_real_testnet_http=self.use_real,
            resolve_env_credentials=self.use_real,
            base_url=self.creds.base_url,
            api_key=self.creds.api_key if self.use_real else None,
            api_secret=self.creds.api_secret if self.use_real else None,
        )
        self.events: list[dict[str, Any]] = []

    def _classify(self) -> str:
        if self.use_real and self.adapter.mode == "REAL_TESTNET":
            return "REAL_TESTNET"
        return "HARNESS/MOCK"

    def validate_safety_preflight(self) -> dict[str, Any]:
        ok = (
            self.settings.trading_mode == "paper"
            and self.settings.live_trading_enabled is False
        )
        stage_mgr = TradingStageManager()
        return _result(
            "PASS" if ok else "FAIL",
            trading_mode=self.settings.trading_mode,
            live_trading_enabled=self.settings.live_trading_enabled,
            default_stage=stage_mgr.current.value,
            classification="SAFETY",
        )

    def validate_endpoint_isolation(self) -> dict[str, Any]:
        guard = SandboxEndpointGuard()
        rejected = False
        try:
            guard.validate(
                self.PRODUCTION_URL,
                stage=TradingStage.STAGE_2_CLOUD_PAPER,
                environment="TESTNET",
            )
        except SandboxEndpointError:
            rejected = True
        # Adapter must not accept production host in testnet mode
        adapter_blocked = False
        try:
            DeltaIndiaSandboxAdapter(
                base_url=self.PRODUCTION_URL,
                use_local_harness=True,
            )
        except SandboxEndpointError:
            adapter_blocked = True
        ok = rejected and adapter_blocked
        return _result(
            "PASS" if ok else "FAIL",
            production_url_rejected=rejected,
            adapter_construction_blocked=adapter_blocked,
            testnet_endpoint=self.adapter.base_url,
            classification="HARNESS/MOCK",
        )

    def validate_hmac_and_clock(self) -> dict[str, Any]:
        secret = "unit-test-secret"
        ts = utc_timestamp_ms()
        valid = delta_india_signature(
            secret=secret,
            method="GET",
            timestamp=ts,
            request_path="/v2/wallet/balances",
        )
        invalid = delta_india_signature(
            secret="wrong",
            method="GET",
            timestamp=ts,
            request_path="/v2/wallet/balances",
        )
        stale_blocked = False
        try:
            stale_ts = str(time_ms() - 60_000)
            self.adapter._inner.sign(
                method="GET",
                request_path="/v2/wallet/balances",
                timestamp=stale_ts,
            )
        except Exception:
            stale_blocked = True
        # incorrect endpoint already covered; malformed request path still signs but API fails
        ok = bool(valid) and valid != invalid and stale_blocked
        return _result(
            "PASS" if ok else "FAIL",
            hmac="HMAC-SHA256",
            clock_skew_seconds=self.adapter._inner.max_clock_skew_seconds,
            stale_timestamp_blocked=stale_blocked,
            classification="HARNESS/MOCK",
            # never emit signature digests in reports
        )

    def validate_auth_account_book(self) -> dict[str, Any]:
        auth = self.adapter.authenticate()
        account = self.adapter.get_account()
        bals = self.adapter.get_balances()
        positions = self.adapter.get_positions()
        opens = self.adapter.get_open_orders()
        health = self.adapter.health_check()
        server = self.adapter.server_time()
        classification = self._classify()
        if not self.creds.configured and not self.force_harness and not self.use_real:
            # harness path still validates read surface
            pass
        ok = (
            auth.get("authenticated") is True
            and isinstance(account.get("account"), dict)
            and isinstance(bals, list)
            and isinstance(positions, list)
            and isinstance(opens, list)
            and health.get("ok") is True
        )
        return _result(
            "PASS" if ok else "FAIL",
            classification=classification,
            credentials_configured=self.creds.configured,
            credential_source=self.creds.source if self.creds.configured else "none",
            auth=auth.get("authenticated"),
            balance_rows=len(bals),
            position_rows=len(positions),
            open_order_rows=len(opens),
            health_ok=health.get("ok"),
            server_time_ok="error" not in server or server.get("result") is not None,
            endpoint=self.adapter.base_url,
        )

    def validate_instrument_discovery(self) -> dict[str, Any]:
        discovered = self.adapter.discover_test_instrument()
        ok = bool(discovered.get("symbol"))
        return _result(
            "PASS" if ok else "FAIL",
            classification=self._classify(),
            symbol=discovered.get("symbol"),
            min_size=discovered.get("min_size"),
            error=discovered.get("error"),
        )

    def validate_order_lifecycle(self) -> dict[str, Any]:
        if not self.creds.configured and self.use_real:
            return _result(
                "NOT_RUN",
                reason="REAL_DELTA_TESTNET_CREDENTIALS_NOT_CONFIGURED",
                classification="NOT_TESTED",
            )
        discovered = self.adapter.discover_test_instrument()
        symbol = discovered.get("symbol") or "BTCUSD"
        min_size = float(discovered.get("min_size") or 1)
        qty = min_size
        # Prefer limit far from market so cancel is deterministic in harness/real.
        price = 1.0
        client_id = f"S21-{uuid4().hex[:16]}"
        submit = self.adapter.submit_order(
            symbol=symbol,
            side="BUY",
            quantity=qty,
            order_type="LIMIT",
            price=price,
            client_order_id=client_id,
        )
        if not submit.get("accepted"):
            return _result(
                "FAIL",
                classification=self._classify(),
                submit_error=submit.get("error"),
                symbol=symbol,
            )
        oid = str(submit.get("exchange_order_id") or "")
        status = self.adapter.get_order_status(oid)
        opens = self.adapter.get_open_orders(symbol)
        # Duplicate idempotent submit
        dup = self.adapter.submit_order(
            symbol=symbol,
            side="BUY",
            quantity=qty,
            order_type="LIMIT",
            price=price,
            client_order_id=client_id,
        )
        dup_same = str(dup.get("exchange_order_id") or "") == oid
        cancel = self.adapter.cancel_order(oid)
        status_after = self.adapter.get_order_status(oid)
        after_status = str((status_after.get("order") or {}).get("status") or "").lower()
        cancelled = after_status in {
            "cancelled",
            "canceled",
        } or cancel.get("success") is True
        # Reconcile via execution service snapshot compare
        svc = SandboxExecutionService(
            adapter=self.adapter,
            store=self.store,
            kill_switch_active=False,
            risk_ok=True,
        )
        recon = svc._reconcile()
        ok = bool(oid) and cancelled and dup_same and recon.get("state") == "RECONCILED"
        return _result(
            "PASS" if ok else "FAIL",
            classification=self._classify(),
            symbol=symbol,
            quantity=qty,
            order_id_present=bool(oid),
            status_checked=bool(status.get("order")),
            open_orders_seen=isinstance(opens, list),
            idempotent_duplicate=dup_same,
            cancelled=cancelled,
            reconciliation_state=recon.get("state"),
            LIVE_TRADING_ENABLED=False,
        )

    def validate_execution_pipeline_and_kill_switch(self) -> dict[str, Any]:
        svc = SandboxExecutionService(
            adapter=self.adapter if not self.use_real else DeltaIndiaSandboxAdapter(
                use_local_harness=True
            ),
            store=SqliteDurableStore(":memory:"),
            kill_switch_active=True,
            risk_ok=True,
        )
        blocked = svc.execute(cycle_id="KS1", idempotency_key="stage21-ks-1")
        # risk fail closed
        svc2 = SandboxExecutionService(
            adapter=DeltaIndiaSandboxAdapter(use_local_harness=True),
            store=SqliteDurableStore(":memory:"),
            kill_switch_active=False,
            risk_ok=False,
        )
        risk_blocked = svc2.execute(cycle_id="R1", idempotency_key="stage21-risk-1")
        # happy path harness
        svc3 = SandboxExecutionService(
            adapter=DeltaIndiaSandboxAdapter(use_local_harness=True),
            store=SqliteDurableStore(":memory:"),
        )
        ok_exec = svc3.execute(cycle_id="OK1", idempotency_key="stage21-ok-1")
        # stage default still STAGE_1
        stage = TradingStageManager().current
        ok = (
            blocked.get("blocked") is True
            and blocked.get("reason") == "KILL_SWITCH"
            and risk_blocked.get("blocked") is True
            and ok_exec.get("executed") is True
            and stage == TradingStage.STAGE_1_LOCAL_PAPER
            and ok_exec.get("LIVE_TRADING_ENABLED") is False
        )
        return _result(
            "PASS" if ok else "FAIL",
            classification="HARNESS/MOCK",
            kill_switch_blocks=blocked.get("reason"),
            risk_blocks=risk_blocked.get("reason"),
            executed_when_clear=ok_exec.get("executed"),
            default_stage=stage.value,
        )

    def validate_websocket(self) -> dict[str, Any]:
        # Real Delta WS not exercised without live credentials/network allowance.
        if self.use_real:
            return _result(
                "NOT_TESTED",
                reason="REAL_DELTA_TESTNET_WEBSOCKET_NOT_EXERCISED",
                classification="NOT_TESTED",
            )
        ws = SandboxWebSocketClient(url="wss://cdn-ind.testnet.deltaex.org/ws", connect=lambda: None)
        first = ws.on_message("1", {"a": 1})
        dup = ws.on_message("1", {"a": 1})
        recon = ws.reconnect()
        ok = dup.get("duplicate") is True and recon.get("connected") is True
        return _result(
            "PASS" if ok else "FAIL",
            classification="HARNESS/MOCK",
            note="Mock/harness WebSocket client only; not real exchange WS",
            first_ok=bool(first),
            duplicate=dup.get("duplicate"),
            reconnect=recon.get("connected"),
        )

    def validate_rate_limit_handling(self) -> dict[str, Any]:
        # Simulate 429 via harness wrapper
        from crypto_trading_mcp.sandbox.harness import LocalDeltaSandboxHarness

        class RateLimited(LocalDeltaSandboxHarness):
            def __call__(self, method: str, url: str, **kwargs: Any):
                if "/v2/wallet/balances" in url:
                    import httpx

                    return httpx.Response(429, json={"error": "rate_limited"})
                return super().__call__(method, url, **kwargs)

        adapter = DeltaIndiaSandboxAdapter(transport=RateLimited(), use_local_harness=False)
        adapter._inner._transport = RateLimited()
        raised = False
        try:
            adapter._inner.get_account()
        except Exception as exc:  # noqa: BLE001
            raised = "RATE_LIMITED" in str(exc) or "429" in str(exc)
        ok = raised and len(adapter._inner.rate_limit_events) >= 1
        return _result(
            "PASS" if ok else "FAIL",
            classification="HARNESS/MOCK",
            events=len(adapter._inner.rate_limit_events),
            note="Does not intentionally exhaust exchange rate limits",
        )

    def run_all(self) -> dict[str, Any]:
        sections = {
            "safety_preflight": self.validate_safety_preflight(),
            "endpoint_isolation": self.validate_endpoint_isolation(),
            "hmac_clock": self.validate_hmac_and_clock(),
            "auth_account_book": self.validate_auth_account_book(),
            "instrument_discovery": self.validate_instrument_discovery(),
            "order_lifecycle": self.validate_order_lifecycle(),
            "execution_kill_switch": self.validate_execution_pipeline_and_kill_switch(),
            "websocket": self.validate_websocket(),
            "rate_limit": self.validate_rate_limit_handling(),
        }
        return {
            "stage": "STAGE_2_1_DELTA_TESTNET_VALIDATION",
            "timestamp": datetime.now(UTC).isoformat(),
            "credentials_configured": self.creds.configured,
            "credential_source": self.creds.redacted_dict()["source"],
            "endpoint": self.adapter.base_url,
            "mode": self.adapter.mode,
            "classification": self._classify(),
            "TRADING_MODE": self.settings.trading_mode,
            "LIVE_TRADING_ENABLED": self.settings.live_trading_enabled,
            "sections": sections,
            "summary": {
                name: val.get("status") for name, val in sections.items()
            },
        }


def run_stage21_validation(*, force_harness: bool = False) -> dict[str, Any]:
    return Stage21DeltaTestnetValidator(force_harness=force_harness).run_all()
