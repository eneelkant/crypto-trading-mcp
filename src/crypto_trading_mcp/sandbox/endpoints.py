from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from crypto_trading_mcp.config.settings import REPO_ROOT
from crypto_trading_mcp.live.stages import TradingStage


class SandboxEndpointError(PermissionError):
    pass


def load_sandbox_config(path: Path | None = None) -> dict[str, Any]:
    path = path or (REPO_ROOT / "config" / "sandbox.yaml")
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data.get("sandbox") or {}


class SandboxEndpointGuard:
    """Reject production exchange hosts while Stage 2 cloud-paper is active."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config if config is not None else load_sandbox_config()
        venue = str(self.config.get("selected_venue") or "delta_india")
        self.venue = venue
        self.venue_cfg = dict(self.config.get(venue) or {})

    def allowed_urls(self) -> set[str]:
        return {u.rstrip("/") for u in self.venue_cfg.get("allowed_base_urls") or []}

    def rejected_urls(self) -> set[str]:
        return {u.rstrip("/") for u in self.venue_cfg.get("rejected_base_urls") or []}

    def normalize(self, base_url: str) -> str:
        return base_url.rstrip("/")

    def host(self, base_url: str) -> str:
        return urlparse(self.normalize(base_url)).netloc.lower()

    def validate(
        self,
        base_url: str,
        *,
        stage: TradingStage = TradingStage.STAGE_2_CLOUD_PAPER,
        environment: str = "TESTNET",
    ) -> dict[str, Any]:
        url = self.normalize(base_url)
        host = self.host(url)
        rejected_hosts = {self.host(u) for u in self.rejected_urls()}
        allowed_hosts = {self.host(u) for u in self.allowed_urls()}

        if stage == TradingStage.STAGE_2_CLOUD_PAPER:
            if host in rejected_hosts or url in self.rejected_urls():
                raise SandboxEndpointError(
                    f"Production endpoint rejected in STAGE_2_CLOUD_PAPER: {host}"
                )
            if allowed_hosts and host not in allowed_hosts:
                raise SandboxEndpointError(
                    f"Endpoint host not in Stage 2 allowlist: {host}"
                )
            if environment.upper() in {"PRODUCTION", "PRODUCTION_TRADING", "PRODUCTION_READ_ONLY"}:
                raise SandboxEndpointError(
                    "Production credential environment rejected in STAGE_2_CLOUD_PAPER"
                )
        return {
            "ok": True,
            "venue": self.venue,
            "base_url": url,
            "host": host,
            "stage": stage.value,
            "environment": environment,
        }
