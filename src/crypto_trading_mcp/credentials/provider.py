from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any

from pydantic import SecretStr

from crypto_trading_mcp.credentials.models import (
    CredentialPermission,
    ExchangeCredentialSet,
    ExchangeEnvironment,
)
from crypto_trading_mcp.credentials.permissions import CredentialPermissionValidator


class CredentialProvider(ABC):
    """Resolve exchange credentials without exposing secrets in public APIs."""

    @abstractmethod
    def get(self, exchange: str) -> ExchangeCredentialSet | None: ...

    def status(self, exchange: str) -> dict[str, Any]:
        creds = self.get(exchange)
        if creds is None:
            return {"exchange": exchange, "present": False}
        return {"present": True, **creds.public_status()}


class EnvironmentCredentialProvider(CredentialProvider):
    """Local/dev provider reading process environment. Never logs values."""

    _MAP = {
        "coinbase": ("COINBASE_API_KEY", "COINBASE_API_SECRET", None),
        "delta_india": ("DELTA_API_KEY", "DELTA_API_SECRET", None),
    }

    def __init__(
        self,
        *,
        environment: ExchangeEnvironment = ExchangeEnvironment.MOCK,
        permissions: list[CredentialPermission] | None = None,
        environ: dict[str, str] | None = None,
    ) -> None:
        self.environment = environment
        self.permissions = permissions or [CredentialPermission.READ_ONLY]
        self._environ = environ if environ is not None else dict(os.environ)
        self._validator = CredentialPermissionValidator()

    def get(self, exchange: str) -> ExchangeCredentialSet | None:
        key = exchange.lower().strip()
        if key not in self._MAP:
            return None
        key_env, secret_env, pass_env = self._MAP[key]
        api_key = self._environ.get(key_env) or ""
        api_secret = self._environ.get(secret_env) or ""
        passphrase = self._environ.get(pass_env) if pass_env else None
        if not api_key and not api_secret:
            return ExchangeCredentialSet(
                exchange=key,
                environment=ExchangeEnvironment.MOCK,
                permissions=[CredentialPermission.READ_ONLY],
            )
        creds = ExchangeCredentialSet(
            exchange=key,
            environment=self.environment,
            api_key=SecretStr(api_key) if api_key else None,
            api_secret=SecretStr(api_secret) if api_secret else None,
            passphrase=SecretStr(passphrase) if passphrase else None,
            permissions=list(self.permissions),
        )
        self._validator.validate(creds)
        return creds


class SecretManagerCredentialProvider(CredentialProvider):
    """Cloud secret-manager adapter. Resolves via injected backend callable.

    Production wiring (GCP/AWS/Vault) is out of band; tests inject a mock backend.
    """

    def __init__(
        self,
        backend: Any,
        *,
        environment: ExchangeEnvironment = ExchangeEnvironment.PRODUCTION_READ_ONLY,
        permissions: list[CredentialPermission] | None = None,
    ) -> None:
        self.backend = backend
        self.environment = environment
        self.permissions = permissions or [CredentialPermission.READ_ONLY]
        self._validator = CredentialPermissionValidator()

    def get(self, exchange: str) -> ExchangeCredentialSet | None:
        key = exchange.lower().strip()
        payload = self.backend.get_secret(f"exchange/{key}")
        if not payload:
            return None
        if not isinstance(payload, dict):
            raise ValueError("Secret manager payload must be a mapping")
        # Reject withdrawal flags from secret metadata
        perms_raw = payload.get("permissions") or [p.value for p in self.permissions]
        perms = [CredentialPermission(p) for p in perms_raw]
        creds = ExchangeCredentialSet(
            exchange=key,
            environment=ExchangeEnvironment(
                payload.get("environment") or self.environment.value
            ),
            api_key=SecretStr(str(payload["api_key"])) if payload.get("api_key") else None,
            api_secret=SecretStr(str(payload["api_secret"]))
            if payload.get("api_secret")
            else None,
            passphrase=SecretStr(str(payload["passphrase"]))
            if payload.get("passphrase")
            else None,
            permissions=perms,
        )
        self._validator.validate(creds)
        return creds
