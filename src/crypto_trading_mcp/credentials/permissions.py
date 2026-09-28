from __future__ import annotations

from typing import Any

from crypto_trading_mcp.credentials.models import (
    CredentialPermission,
    ExchangeCredentialSet,
    ExchangeEnvironment,
)


class CredentialPermissionError(PermissionError):
    pass


class CredentialPermissionValidator:
    """Enforces READ_ONLY / TRADING and explicitly rejects WITHDRAWAL."""

    ALLOWED = {CredentialPermission.READ_ONLY, CredentialPermission.TRADING}
    FORBIDDEN = {CredentialPermission.WITHDRAWAL}

    def validate(self, creds: ExchangeCredentialSet) -> dict[str, Any]:
        perms = set(creds.permissions)
        if perms & self.FORBIDDEN:
            raise CredentialPermissionError(
                "WITHDRAWAL permission is forbidden for the trading engine"
            )
        if not perms:
            raise CredentialPermissionError("Credential permissions must not be empty")
        if not perms.issubset(self.ALLOWED):
            raise CredentialPermissionError(f"Unsupported permissions: {perms - self.ALLOWED}")

        if creds.environment == ExchangeEnvironment.PRODUCTION_TRADING:
            if CredentialPermission.TRADING not in perms:
                raise CredentialPermissionError(
                    "PRODUCTION_TRADING environment requires TRADING permission"
                )
        if creds.environment == ExchangeEnvironment.PRODUCTION_READ_ONLY:
            if CredentialPermission.TRADING in perms:
                raise CredentialPermissionError(
                    "PRODUCTION_READ_ONLY must not include TRADING permission"
                )
        return {
            "ok": True,
            "permissions": [p.value for p in creds.permissions],
            "withdrawal": False,
            "environment": creds.environment.value,
        }

    def minimum_for(self, environment: ExchangeEnvironment) -> list[CredentialPermission]:
        if environment in {
            ExchangeEnvironment.PRODUCTION_TRADING,
            ExchangeEnvironment.SANDBOX,
            ExchangeEnvironment.TESTNET,
        }:
            return [CredentialPermission.READ_ONLY, CredentialPermission.TRADING]
        return [CredentialPermission.READ_ONLY]
