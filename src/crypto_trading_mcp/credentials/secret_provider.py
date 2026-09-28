from __future__ import annotations

import os
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from crypto_trading_mcp.credentials.redaction import redact_payload


class SecretProvider(ABC):
    """Retrieve secrets without exposing values through public APIs."""

    @abstractmethod
    def get_secret(self, name: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def exists(self, name: str) -> bool: ...

    def audit_access(self, name: str, *, ok: bool) -> dict[str, Any]:
        return {
            "secret_name": name,
            "ok": ok,
            "timestamp": datetime.now(UTC).isoformat(),
            "value": "[REDACTED]",
        }


class EnvironmentSecretProvider(SecretProvider):
    """Map logical secret names to environment variables (local Stage 2)."""

    DEFAULT_MAP = {
        "exchange/delta_india": ("DELTA_API_KEY", "DELTA_API_SECRET"),
        "exchange/delta_india_testnet": (
            "DELTA_TESTNET_API_KEY",
            "DELTA_TESTNET_API_SECRET",
        ),
        "exchange/coinbase": ("COINBASE_API_KEY", "COINBASE_API_SECRET"),
    }

    # Prefer dedicated testnet vars when resolving delta_india in testnet mode.
    TESTNET_FALLBACK = ("DELTA_API_KEY", "DELTA_API_SECRET")

    def __init__(self, environ: dict[str, str] | None = None) -> None:
        self._environ = environ if environ is not None else dict(os.environ)
        self.access_log: list[dict[str, Any]] = []

    def exists(self, name: str) -> bool:
        keys = self.DEFAULT_MAP.get(name)
        if not keys:
            return False
        if any(bool(self._environ.get(k)) for k in keys):
            return True
        if name == "exchange/delta_india_testnet":
            return any(bool(self._environ.get(k)) for k in self.TESTNET_FALLBACK)
        return False

    def get_secret(self, name: str) -> dict[str, Any] | None:
        keys = self.DEFAULT_MAP.get(name)
        if not keys:
            self.access_log.append(self.audit_access(name, ok=False))
            return None
        api_key = self._environ.get(keys[0]) or ""
        api_secret = self._environ.get(keys[1]) or ""
        if (
            not api_key
            and not api_secret
            and name == "exchange/delta_india_testnet"
        ):
            api_key = self._environ.get(self.TESTNET_FALLBACK[0]) or ""
            api_secret = self._environ.get(self.TESTNET_FALLBACK[1]) or ""
        if not api_key and not api_secret:
            self.access_log.append(self.audit_access(name, ok=False))
            return None
        delta_env = (self._environ.get("DELTA_ENV") or "testnet").lower()
        if delta_env in {"production", "prod", "live"}:
            self.access_log.append(self.audit_access(name, ok=False))
            raise PermissionError("Production DELTA_ENV forbidden for testnet secret map")
        self.access_log.append(self.audit_access(name, ok=True))
        return {
            "api_key": api_key,
            "api_secret": api_secret,
            "environment": "TESTNET",
            "permissions": ["READ_ONLY", "TRADING"],
        }


class GoogleSecretManagerProvider(SecretProvider):
    """GCP Secret Manager provider.

    Uses an injected client with ``access_secret_version``. No values are logged.
    """

    def __init__(self, client: Any, *, project_id: str) -> None:
        self.client = client
        self.project_id = project_id
        self.access_log: list[dict[str, Any]] = []

    def _resource(self, name: str) -> str:
        # logical name exchange/delta_india → secret id exchange_delta_india
        secret_id = name.replace("/", "_")
        return f"projects/{self.project_id}/secrets/{secret_id}/versions/latest"

    def exists(self, name: str) -> bool:
        try:
            return self.get_secret(name) is not None
        except Exception:
            return False

    def get_secret(self, name: str) -> dict[str, Any] | None:
        try:
            response = self.client.access_secret_version(request={"name": self._resource(name)})
            payload = response.payload.data.decode("utf-8")
            # Expect JSON mapping
            import json

            data = json.loads(payload)
            if not isinstance(data, dict):
                self.access_log.append(self.audit_access(name, ok=False))
                return None
            # Never allow withdrawal permission markers
            perms = data.get("permissions") or ["READ_ONLY"]
            if "WITHDRAWAL" in perms:
                raise PermissionError("WITHDRAWAL permission forbidden in secret payload")
            self.access_log.append(self.audit_access(name, ok=True))
            return data
        except Exception:
            self.access_log.append(self.audit_access(name, ok=False))
            return None
