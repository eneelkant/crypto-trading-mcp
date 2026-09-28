from __future__ import annotations

from typing import Any

from crypto_trading_mcp.exchange.auth import redact_secrets

_SECRET_FRAGMENTS = (
    "secret",
    "api_key",
    "apikey",
    "password",
    "token",
    "authorization",
    "passphrase",
    "private_key",
    "seed",
    "mnemonic",
    "signature",
    "bearer",
)


def redact_payload(payload: Any) -> Any:
    """Recursively redact secret-bearing structures for logs/events/MCP."""
    return redact_secrets(payload)


def contains_secret_leak(text: str, known_secrets: list[str] | None = None) -> bool:
    lowered = text.lower()
    if any(frag in lowered for frag in ("sk-", "api-secret", "begin private key")):
        return True
    for secret in known_secrets or []:
        if secret and secret in text:
            return True
    return False


def safe_exception_message(exc: BaseException) -> str:
    msg = str(exc)
    redacted = msg
    for frag in _SECRET_FRAGMENTS:
        if frag in redacted.lower():
            # Collapse likely key=value pairs
            redacted = "[REDACTED_EXCEPTION]"
            break
    return redacted[:500]
