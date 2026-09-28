from __future__ import annotations

from typing import Any

from crypto_trading_mcp.credentials.models import ExchangeCredentialSet, ExchangeEnvironment
from crypto_trading_mcp.credentials.permissions import (
    CredentialPermissionError,
    CredentialPermissionValidator,
)


class CredentialHealthCheck:
    """Validates credential presence/permissions without exposing secrets."""

    def __init__(self, validator: CredentialPermissionValidator | None = None) -> None:
        self.validator = validator or CredentialPermissionValidator()

    def check(self, creds: ExchangeCredentialSet | None) -> dict[str, Any]:
        if creds is None:
            return {"healthy": False, "reason": "CREDENTIALS_MISSING", "public": {}}
        try:
            self.validator.validate(creds)
        except CredentialPermissionError as exc:
            return {
                "healthy": False,
                "reason": "CREDENTIAL_PERMISSION_FAILURE",
                "detail": str(exc),
                "public": creds.public_status(),
            }
        if creds.environment == ExchangeEnvironment.MOCK:
            return {"healthy": True, "reason": "MOCK_OK", "public": creds.public_status()}
        if not creds.has_secret_material():
            return {
                "healthy": False,
                "reason": "CREDENTIAL_MATERIAL_MISSING",
                "public": creds.public_status(),
            }
        return {"healthy": True, "reason": "OK", "public": creds.public_status()}
