"""Resolve Delta India TESTNET credentials without exposing values."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping

from crypto_trading_mcp.sandbox.endpoints import SandboxEndpointError, load_sandbox_config


PRODUCTION_HOST_MARKERS = (
    "api.india.delta.exchange",
    "api.delta.exchange",
)


@dataclass(frozen=True)
class TestnetCredentialStatus:
    configured: bool
    source: str
    base_url: str
    environment: str
    has_key: bool
    has_secret: bool
    # Never store raw secrets on this object when serializing to reports.
    api_key: str | None = None
    api_secret: str | None = None

    def redacted_dict(self) -> dict[str, Any]:
        return {
            "configured": self.configured,
            "source": self.source,
            "base_url": self.base_url,
            "environment": self.environment,
            "has_key": self.has_key,
            "has_secret": self.has_secret,
            "api_key": "[REDACTED]" if self.has_key else None,
            "api_secret": "[REDACTED]" if self.has_secret else None,
            "LIVE_TRADING_ENABLED": False,
        }


def resolve_testnet_base_url(environ: Mapping[str, str] | None = None) -> str:
    env = environ if environ is not None else os.environ
    cfg = load_sandbox_config()
    venue = dict(cfg.get("delta_india") or {})
    default = str(venue.get("default_base_url") or "https://cdn-ind.testnet.deltaex.org")
    # Prefer explicit testnet URL envs; never invent production.
    url = (
        env.get("DELTA_TESTNET_API_BASE_URL")
        or env.get("DELTA_API_BASE_URL")
        or default
    ).rstrip("/")
    lower = url.lower()
    for marker in PRODUCTION_HOST_MARKERS:
        if marker in lower:
            raise SandboxEndpointError(
                f"Production endpoint forbidden for Stage 2.1 testnet credentials: {marker}"
            )
    delta_env = (env.get("DELTA_ENV") or "testnet").strip().lower()
    if delta_env in {"production", "prod", "live"}:
        raise SandboxEndpointError("DELTA_ENV=production is forbidden for Stage 2.1")
    return url


def resolve_testnet_credentials(
    environ: Mapping[str, str] | None = None,
) -> TestnetCredentialStatus:
    """Resolve testnet credentials from environment only.

    Preference order:
    1. DELTA_TESTNET_API_KEY / DELTA_TESTNET_API_SECRET
    2. DELTA_API_KEY / DELTA_API_SECRET when DELTA_ENV=testnet (or unset)
    """
    env = dict(environ) if environ is not None else dict(os.environ)
    base_url = resolve_testnet_base_url(env)
    delta_env = (env.get("DELTA_ENV") or "testnet").strip().lower()

    tn_key = (env.get("DELTA_TESTNET_API_KEY") or "").strip()
    tn_secret = (env.get("DELTA_TESTNET_API_SECRET") or "").strip()
    if tn_key and tn_secret:
        return TestnetCredentialStatus(
            configured=True,
            source="DELTA_TESTNET_API_*",
            base_url=base_url,
            environment="TESTNET",
            has_key=True,
            has_secret=True,
            api_key=tn_key,
            api_secret=tn_secret,
        )

    # Fallback to DELTA_API_* only when explicitly in testnet mode (default).
    if delta_env in {"testnet", "sandbox", ""}:
        key = (env.get("DELTA_API_KEY") or "").strip()
        secret = (env.get("DELTA_API_SECRET") or "").strip()
        if key and secret:
            return TestnetCredentialStatus(
                configured=True,
                source="DELTA_API_*+DELTA_ENV=testnet",
                base_url=base_url,
                environment="TESTNET",
                has_key=True,
                has_secret=True,
                api_key=key,
                api_secret=secret,
            )

    return TestnetCredentialStatus(
        configured=False,
        source="none",
        base_url=base_url,
        environment="TESTNET",
        has_key=False,
        has_secret=False,
    )
