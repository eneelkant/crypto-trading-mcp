from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from crypto_trading_mcp.config.settings import REPO_ROOT


class DashboardSettings(BaseModel):
    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = 8050
    auto_open: bool = True
    websocket_enabled: bool = True
    event_history_limit: int = 5000
    static_dir: str = "dashboard_ui/dist"
    title: str = "AI Trading Command Center"

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def static_path(self) -> Path:
        path = Path(self.static_dir)
        if not path.is_absolute():
            path = REPO_ROOT / path
        return path


class DashboardEnv(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    dashboard_enabled: bool | None = None
    dashboard_host: str | None = None
    dashboard_port: int | None = None
    dashboard_auto_open: bool | None = None
    dashboard_websocket_enabled: bool | None = None


def load_dashboard_config(path: Path | None = None) -> DashboardSettings:
    path = path or (REPO_ROOT / "config" / "dashboard.yaml")
    data: dict[str, Any] = {}
    if path.exists():
        with path.open(encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
        data = raw.get("dashboard") or {}
    settings = DashboardSettings.model_validate(data)
    env = DashboardEnv()
    updates: dict[str, Any] = {}
    if env.dashboard_enabled is not None:
        updates["enabled"] = env.dashboard_enabled
    if env.dashboard_host is not None:
        updates["host"] = env.dashboard_host
    if env.dashboard_port is not None:
        updates["port"] = env.dashboard_port
    if env.dashboard_auto_open is not None:
        updates["auto_open"] = env.dashboard_auto_open
    if env.dashboard_websocket_enabled is not None:
        updates["websocket_enabled"] = env.dashboard_websocket_enabled
    if updates:
        settings = settings.model_copy(update=updates)
    # Safety: never auto-bind public by default; keep localhost unless explicitly set.
    if settings.host in {"0.0.0.0", "::"}:
        # Still allow if user set it, but document risk; leave as configured.
        pass
    return settings
