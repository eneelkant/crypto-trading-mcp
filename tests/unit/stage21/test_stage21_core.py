from __future__ import annotations

import pytest

from crypto_trading_mcp.config.settings import get_settings
from crypto_trading_mcp.credentials.secret_provider import EnvironmentSecretProvider
from crypto_trading_mcp.exchange.auth import delta_india_signature
from crypto_trading_mcp.exchange.delta_india import DeltaExchangeIndiaAdapter, time_ms
from crypto_trading_mcp.exchange.exceptions import LiveExecutionBlocked
from crypto_trading_mcp.credentials.models import ExchangeEnvironment
from crypto_trading_mcp.live.stages import TradingStage, TradingStageManager
from crypto_trading_mcp.sandbox.delta_sandbox import DeltaIndiaSandboxAdapter
from crypto_trading_mcp.sandbox.endpoints import SandboxEndpointError
from crypto_trading_mcp.sandbox.testnet_credentials import (
    resolve_testnet_base_url,
    resolve_testnet_credentials,
)
from crypto_trading_mcp.sandbox.testnet_validation import (
    Stage21DeltaTestnetValidator,
    run_stage21_validation,
)


def test_stage21_branch_safety_defaults():
    s = get_settings()
    assert s.trading_mode == "paper"
    assert s.live_trading_enabled is False
    assert TradingStageManager().current == TradingStage.STAGE_1_LOCAL_PAPER


def test_production_endpoint_cannot_be_selected():
    with pytest.raises(SandboxEndpointError):
        resolve_testnet_base_url(
            {"DELTA_API_BASE_URL": "https://api.india.delta.exchange", "DELTA_ENV": "testnet"}
        )
    with pytest.raises(SandboxEndpointError):
        DeltaIndiaSandboxAdapter(base_url="https://api.india.delta.exchange", use_local_harness=True)


def test_credentials_prefer_testnet_vars_and_redact():
    env = {
        "DELTA_TESTNET_API_KEY": "tn-key",
        "DELTA_TESTNET_API_SECRET": "tn-secret",
        "DELTA_ENV": "testnet",
    }
    status = resolve_testnet_credentials(env)
    assert status.configured is True
    red = status.redacted_dict()
    assert red["api_key"] == "[REDACTED]"
    assert "tn-secret" not in str(red)
    assert red["source"] == "DELTA_TESTNET_API_*"


def test_missing_credentials_status():
    status = resolve_testnet_credentials({})
    assert status.configured is False
    assert status.source == "none"


def test_hmac_valid_invalid_stale():
    ts = str(time_ms())
    good = delta_india_signature(
        secret="s", method="GET", timestamp=ts, request_path="/v2/wallet/balances"
    )
    bad = delta_india_signature(
        secret="other", method="GET", timestamp=ts, request_path="/v2/wallet/balances"
    )
    assert good and good != bad
    adapter = DeltaExchangeIndiaAdapter(
        base_url="https://cdn-ind.testnet.deltaex.org",
        api_key="k",
        api_secret="s",
        environment=ExchangeEnvironment.TESTNET,
        max_clock_skew_seconds=5,
        allow_real_testnet_http=False,
        transport=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no")),
    )
    with pytest.raises(LiveExecutionBlocked):
        adapter.sign(
            method="GET",
            request_path="/v2/wallet/balances",
            timestamp=str(time_ms() - 30_000),
        )


def test_real_http_blocked_without_allow_flag():
    adapter = DeltaExchangeIndiaAdapter(
        base_url="https://cdn-ind.testnet.deltaex.org",
        api_key="k",
        api_secret="s",
        environment=ExchangeEnvironment.TESTNET,
        allow_real_testnet_http=False,
        transport=None,
    )
    from crypto_trading_mcp.exchange.models import Order, OrderSide, OrderType

    with pytest.raises(LiveExecutionBlocked):
        adapter.create_order(
            Order(
                symbol="BTCUSD",
                side=OrderSide.BUY,
                quantity=1,
                order_type=OrderType.LIMIT,
                limit_price=1.0,
            )
        )


def test_production_host_blocked_even_with_allow_real():
    adapter = DeltaExchangeIndiaAdapter(
        base_url="https://api.india.delta.exchange",
        api_key="k",
        api_secret="s",
        environment=ExchangeEnvironment.TESTNET,
        allow_real_testnet_http=True,
        transport=None,
    )
    from crypto_trading_mcp.exchange.models import Order, OrderSide, OrderType

    with pytest.raises(LiveExecutionBlocked):
        adapter.create_order(
            Order(
                symbol="BTCUSD",
                side=OrderSide.BUY,
                quantity=1,
                order_type=OrderType.LIMIT,
                limit_price=1.0,
            )
        )


def test_harness_instrument_discovery_and_limit_cancel_idempotency():
    adapter = DeltaIndiaSandboxAdapter(use_local_harness=True)
    discovered = adapter.discover_test_instrument()
    assert discovered["symbol"] == "BTCUSD"
    submit = adapter.submit_order(
        symbol="BTCUSD",
        side="BUY",
        quantity=1,
        order_type="LIMIT",
        price=1.0,
        client_order_id="idem-21-1",
    )
    assert submit["accepted"] is True
    oid = submit["exchange_order_id"]
    dup = adapter.submit_order(
        symbol="BTCUSD",
        side="BUY",
        quantity=1,
        order_type="LIMIT",
        price=1.0,
        client_order_id="idem-21-1",
    )
    assert dup["exchange_order_id"] == oid
    cancel = adapter.cancel_order(oid)
    assert cancel["success"] is True
    status = adapter.get_order_status(oid)
    assert str(status["order"].get("status")).lower() in {"cancelled", "canceled"}


def test_secret_provider_testnet_map():
    provider = EnvironmentSecretProvider(
        {"DELTA_TESTNET_API_KEY": "k", "DELTA_TESTNET_API_SECRET": "s", "DELTA_ENV": "testnet"}
    )
    secret = provider.get_secret("exchange/delta_india_testnet")
    assert secret is not None
    assert secret["environment"] == "TESTNET"
    assert "WITHDRAWAL" not in secret["permissions"]
    # audit log never stores raw values
    assert all(e.get("value") == "[REDACTED]" for e in provider.access_log)


def test_stage21_validator_harness_suite():
    report = run_stage21_validation(force_harness=True)
    assert report["TRADING_MODE"] == "paper"
    assert report["LIVE_TRADING_ENABLED"] is False
    assert report["credentials_configured"] is False or report["mode"] in {
        "HARNESS",
        "HARNESS_FALLBACK_NO_CREDS",
    }
    summary = report["summary"]
    for key in (
        "safety_preflight",
        "endpoint_isolation",
        "hmac_clock",
        "auth_account_book",
        "instrument_discovery",
        "order_lifecycle",
        "execution_kill_switch",
        "rate_limit",
    ):
        assert summary[key] == "PASS", (key, report["sections"][key])
    assert summary["websocket"] in {"PASS", "NOT_TESTED"}


def test_missing_creds_do_not_fallback_to_production():
    v = Stage21DeltaTestnetValidator(force_harness=True)
    assert "api.india.delta.exchange" not in v.adapter.base_url
    iso = v.validate_endpoint_isolation()
    assert iso["status"] == "PASS"
