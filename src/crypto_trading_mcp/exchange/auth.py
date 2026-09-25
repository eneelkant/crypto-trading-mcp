from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any


def utc_timestamp_ms() -> str:
    return str(int(time.time() * 1000))


def delta_india_signature(
    *,
    secret: str,
    method: str,
    timestamp: str,
    request_path: str,
    query_params: str = "",
    body: str = "",
) -> str:
    """HMAC-SHA256 signing for Delta Exchange India.

    message = method + timestamp + requestPath + query_params + body
    """
    payload = f"{method.upper()}{timestamp}{request_path}{query_params}{body}"
    digest = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest


def redact_secrets(payload: Any) -> Any:
    if isinstance(payload, dict):
        out: dict[str, Any] = {}
        for k, v in payload.items():
            lk = str(k).lower()
            if any(s in lk for s in ("secret", "api_key", "apikey", "password", "token", "authorization")):
                out[k] = "[REDACTED]"
            else:
                out[k] = redact_secrets(v)
        return out
    if isinstance(payload, list):
        return [redact_secrets(v) for v in payload]
    return payload
