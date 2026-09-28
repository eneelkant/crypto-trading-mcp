from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, SecretStr


class ExchangeEnvironment(str, Enum):
    MOCK = "MOCK"
    SANDBOX = "SANDBOX"
    TESTNET = "TESTNET"
    PRODUCTION_READ_ONLY = "PRODUCTION_READ_ONLY"
    PRODUCTION_TRADING = "PRODUCTION_TRADING"


class CredentialPermission(str, Enum):
    READ_ONLY = "READ_ONLY"
    TRADING = "TRADING"
    WITHDRAWAL = "WITHDRAWAL"


class ExchangeCredentialSet(BaseModel):
    """In-memory credential bundle. Secrets never serialized to logs/DB/events."""

    exchange: str
    environment: ExchangeEnvironment = ExchangeEnvironment.MOCK
    api_key: SecretStr | None = None
    api_secret: SecretStr | None = None
    passphrase: SecretStr | None = None
    permissions: list[CredentialPermission] = Field(
        default_factory=lambda: [CredentialPermission.READ_ONLY]
    )
    ip_allowlist_required: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    def has_secret_material(self) -> bool:
        return bool(
            (self.api_key and self.api_key.get_secret_value())
            or (self.api_secret and self.api_secret.get_secret_value())
        )

    def public_status(self) -> dict[str, Any]:
        """Safe for dashboards/MCP — never includes secret values."""
        return {
            "exchange": self.exchange,
            "environment": self.environment.value,
            "permissions": [p.value for p in self.permissions],
            "has_api_key": bool(self.api_key and self.api_key.get_secret_value()),
            "has_api_secret": bool(self.api_secret and self.api_secret.get_secret_value()),
            "ip_allowlist_required": self.ip_allowlist_required,
            "withdrawal_permission": CredentialPermission.WITHDRAWAL in self.permissions,
        }
