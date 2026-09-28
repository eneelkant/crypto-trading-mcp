"""Secure TradingView webhook → trade intent only (never direct execution)."""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Callable


ALLOWED_ACTIONS = {"buy", "sell", "long", "short", "close", "exit"}
PLACEHOLDER_SECRETS = {
    "YOUR_SECRET_KEY",
    "your_secret_key",
    "PLACEHOLDER_NOT_A_SECRET",
    "{{secret}}",
    "",
}


class WebhookSecurityError(PermissionError):
    pass


@dataclass
class TradingViewWebhookConfig:
    secret_env_var: str = "TRADINGVIEW_WEBHOOK_SECRET"
    require_https: bool = True
    allow_localhost_http: bool = True
    max_skew_seconds: int = 60
    rate_limit_per_minute: int = 30
    symbol_allowlist: set[str] = field(
        default_factory=lambda: {
            "BTC/USD",
            "BTC-USD",
            "BTCUSDT",
            "ETH/USD",
            "ETH-USD",
            "ETHUSDT",
            "SOL/USD",
            "SOLUSDT",
        }
    )
    min_qty: float = 0.0
    max_qty: float = 100.0
    min_price: float = 0.0
    max_price: float = 10_000_000.0
    idempotency_ttl_seconds: int = 3600


class TradingViewWebhookHandler:
    """Validate TradingView alerts and emit trade intents only.

    Intents must still pass RiskEngine, KillSwitch, StageManager,
    LiveTradingGate, Reconciliation, and ExecutionPolicy.
    """

    def __init__(
        self,
        config: TradingViewWebhookConfig | None = None,
        *,
        secret: str | None = None,
        intent_sink: Callable[[dict[str, Any]], None] | None = None,
        audit_sink: Callable[[dict[str, Any]], None] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.config = config or TradingViewWebhookConfig()
        self._secret = secret
        self.intent_sink = intent_sink
        self.audit_sink = audit_sink
        self.clock = clock or time.time
        self._seen_nonces: OrderedDict[str, float] = OrderedDict()
        self._seen_idempotency: OrderedDict[str, float] = OrderedDict()
        self._rate_buckets: list[float] = []
        self.audit_log: list[dict[str, Any]] = []

    def resolve_secret(self) -> str:
        if self._secret is not None:
            secret = self._secret
        else:
            secret = os.environ.get(self.config.secret_env_var, "")
        if not secret or secret in PLACEHOLDER_SECRETS:
            raise WebhookSecurityError("WEBHOOK_SECRET_NOT_CONFIGURED")
        if secret in PLACEHOLDER_SECRETS or secret == "YOUR_SECRET_KEY":
            raise WebhookSecurityError("WEBHOOK_SECRET_PLACEHOLDER_REJECTED")
        return secret

    def _audit(self, event: dict[str, Any]) -> None:
        event = {
            **event,
            "timestamp": datetime.now(UTC).isoformat(),
            # Never log the raw secret
            "secret_present": "secret" in (event.get("fields") or {}),
        }
        event.pop("secret", None)
        if "fields" in event and isinstance(event["fields"], dict):
            fields = dict(event["fields"])
            if "secret" in fields:
                fields["secret"] = "***REDACTED***"
            event["fields"] = fields
        self.audit_log.append(event)
        if self.audit_sink:
            self.audit_sink(event)

    def _prune(self, now: float) -> None:
        ttl = self.config.idempotency_ttl_seconds
        while self._seen_nonces and next(iter(self._seen_nonces.values())) < now - ttl:
            self._seen_nonces.popitem(last=False)
        while self._seen_idempotency and next(iter(self._seen_idempotency.values())) < now - ttl:
            self._seen_idempotency.popitem(last=False)
        self._rate_buckets = [t for t in self._rate_buckets if t >= now - 60]

    def handle(
        self,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
        remote_scheme: str = "https",
        remote_host: str = "example.com",
    ) -> dict[str, Any]:
        headers = {k.lower(): v for k, v in (headers or {}).items()}
        now = self.clock()
        self._prune(now)

        try:
            secret = self.resolve_secret()
        except WebhookSecurityError as exc:
            self._audit({"event": "REJECTED", "reason": str(exc)})
            return {"accepted": False, "reason_code": str(exc), "intent_created": False}

        # HTTPS enforcement for non-local
        host = (remote_host or "").split(":")[0].lower()
        local = host in {"127.0.0.1", "localhost", "::1"}
        if self.config.require_https and remote_scheme.lower() != "https":
            if not (local and self.config.allow_localhost_http):
                self._audit({"event": "REJECTED", "reason": "HTTPS_REQUIRED"})
                return {
                    "accepted": False,
                    "reason_code": "HTTPS_REQUIRED",
                    "intent_created": False,
                }

        # Rate limit
        if len(self._rate_buckets) >= self.config.rate_limit_per_minute:
            self._audit({"event": "REJECTED", "reason": "RATE_LIMIT"})
            return {"accepted": False, "reason_code": "RATE_LIMIT", "intent_created": False}
        self._rate_buckets.append(now)

        # Schema
        required = {"action", "symbol", "price", "qty", "secret"}
        missing = required - set(payload)
        if missing:
            self._audit({"event": "REJECTED", "reason": "SCHEMA_INVALID", "missing": sorted(missing)})
            return {
                "accepted": False,
                "reason_code": "SCHEMA_INVALID",
                "missing": sorted(missing),
                "intent_created": False,
            }

        provided_secret = str(payload.get("secret") or "")
        if provided_secret in PLACEHOLDER_SECRETS or provided_secret == "YOUR_SECRET_KEY":
            self._audit({"event": "REJECTED", "reason": "SECRET_PLACEHOLDER"})
            return {
                "accepted": False,
                "reason_code": "SECRET_PLACEHOLDER",
                "intent_created": False,
            }
        if not hmac.compare_digest(provided_secret, secret):
            self._audit({"event": "REJECTED", "reason": "SECRET_MISMATCH"})
            return {
                "accepted": False,
                "reason_code": "AUTH_FAILED",
                "intent_created": False,
            }

        # Timestamp / replay
        ts_header = headers.get("x-webhook-timestamp") or str(payload.get("timestamp") or "")
        nonce = headers.get("x-webhook-nonce") or str(payload.get("nonce") or "")
        if not ts_header or not nonce:
            self._audit({"event": "REJECTED", "reason": "REPLAY_PROTECTION_FIELDS_MISSING"})
            return {
                "accepted": False,
                "reason_code": "REPLAY_PROTECTION_REQUIRED",
                "intent_created": False,
            }
        try:
            ts = float(ts_header)
        except ValueError:
            return {
                "accepted": False,
                "reason_code": "TIMESTAMP_INVALID",
                "intent_created": False,
            }
        if abs(now - ts) > self.config.max_skew_seconds:
            self._audit({"event": "REJECTED", "reason": "TIMESTAMP_SKEW"})
            return {
                "accepted": False,
                "reason_code": "TIMESTAMP_SKEW",
                "intent_created": False,
            }
        if nonce in self._seen_nonces:
            self._audit({"event": "REJECTED", "reason": "REPLAY_DETECTED"})
            return {
                "accepted": False,
                "reason_code": "REPLAY_DETECTED",
                "intent_created": False,
            }
        self._seen_nonces[nonce] = now

        action = str(payload["action"]).strip().lower()
        if action not in ALLOWED_ACTIONS:
            return {
                "accepted": False,
                "reason_code": "ACTION_NOT_ALLOWED",
                "intent_created": False,
            }

        symbol = str(payload["symbol"]).strip().upper()
        allow = {s.upper() for s in self.config.symbol_allowlist}
        sym_candidates = {
            symbol,
            symbol.replace("-", "/"),
            symbol.replace("/", "-"),
            symbol.replace("/", ""),
        }
        if not (sym_candidates & allow or any(a.replace("/", "") in sym_candidates for a in allow)):
            return {
                "accepted": False,
                "reason_code": "SYMBOL_NOT_ALLOWED",
                "intent_created": False,
            }

        try:
            price = float(payload["price"])
            qty = float(payload["qty"])
        except (TypeError, ValueError):
            return {
                "accepted": False,
                "reason_code": "PRICE_QTY_INVALID",
                "intent_created": False,
            }
        if not (self.config.min_price < price <= self.config.max_price):
            return {
                "accepted": False,
                "reason_code": "PRICE_OUT_OF_RANGE",
                "intent_created": False,
            }
        if not (self.config.min_qty < qty <= self.config.max_qty):
            return {
                "accepted": False,
                "reason_code": "QTY_OUT_OF_RANGE",
                "intent_created": False,
            }

        idem = (
            headers.get("idempotency-key")
            or str(payload.get("idempotency_key") or "")
            or hashlib.sha256(
                f"{nonce}:{symbol}:{action}:{price}:{qty}".encode()
            ).hexdigest()
        )
        if idem in self._seen_idempotency:
            self._audit({"event": "DUPLICATE", "idempotency_key": idem})
            return {
                "accepted": True,
                "reason_code": "IDEMPOTENT_REPLAY",
                "intent_created": False,
                "idempotency_key": idem,
            }
        self._seen_idempotency[idem] = now

        intent = {
            "source": "tradingview_webhook",
            "action": action,
            "symbol": symbol.replace("-", "/"),
            "price": price,
            "qty": qty,
            "idempotency_key": idem,
            "nonce": nonce,
            "timestamp": ts,
            "created_at": datetime.now(UTC).isoformat(),
            "status": "INTENT_ONLY",
            "execution_attempted": False,
            "requires": [
                "RiskEngine",
                "KillSwitch",
                "StageManager",
                "LiveTradingGate",
                "Reconciliation",
                "ExecutionPolicy",
            ],
            "LIVE_TRADING_ENABLED": False,
            "note": "Webhook creates trade intents only; never submits exchange orders directly.",
        }
        if self.intent_sink:
            self.intent_sink(intent)
        self._audit(
            {
                "event": "INTENT_CREATED",
                "idempotency_key": idem,
                "symbol": intent["symbol"],
                "action": action,
                "fields": {"action": action, "symbol": symbol, "price": price, "qty": qty},
            }
        )
        return {
            "accepted": True,
            "reason_code": "INTENT_CREATED",
            "intent_created": True,
            "intent": intent,
            "llm_can_bypass_gates": False,
        }
