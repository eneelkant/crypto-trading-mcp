from __future__ import annotations

import threading
import time
from typing import Any

import uvicorn

from crypto_trading_mcp.dashboard.app import create_app
from crypto_trading_mcp.dashboard.browser import open_dashboard_browser
from crypto_trading_mcp.dashboard.config import DashboardSettings, load_dashboard_config
from crypto_trading_mcp.dashboard.health import check_dashboard_health
from crypto_trading_mcp.dashboard.state import get_dashboard_state, set_dashboard_state, DashboardState


class DashboardServer:
    """Runs uvicorn in a daemon thread so trading continues if dashboard dies."""

    def __init__(self, settings: DashboardSettings | None = None, state: DashboardState | None = None) -> None:
        self.settings = settings or load_dashboard_config()
        if state is not None:
            set_dashboard_state(state)
        self.state = get_dashboard_state()
        self._thread: threading.Thread | None = None
        self._server: uvicorn.Server | None = None
        self._started = False

    @property
    def url(self) -> str:
        return self.settings.url

    def start(self, *, open_browser: bool | None = None, wait_healthy: bool = True) -> dict[str, Any]:
        if not self.settings.enabled:
            return {"started": False, "reason": "DASHBOARD_DISABLED", "url": self.url}
        if self._started and self._thread and self._thread.is_alive():
            result = {"started": False, "reason": "ALREADY_RUNNING", "url": self.url}
            if open_browser or (open_browser is None and self.settings.auto_open):
                result["browser"] = open_dashboard_browser(self.settings)
            return result

        app = create_app(self.settings)
        config = uvicorn.Config(
            app,
            host=self.settings.host,
            port=self.settings.port,
            log_level="warning",
            access_log=False,
        )
        self._server = uvicorn.Server(config)

        def _run() -> None:
            try:
                self._server.run()
            except Exception:  # noqa: BLE001
                # Dashboard failure must not stop trading.
                self.state.components["WebSocket"].status = "OFFLINE"
                self.state.components["WebSocket"].last_error = "dashboard_server_exited"

        self._thread = threading.Thread(target=_run, name="dashboard-uvicorn", daemon=True)
        self._thread.start()
        self._started = True
        self.state.running = True

        healthy = {"ok": False}
        if wait_healthy:
            for _ in range(40):
                healthy = check_dashboard_health(self.settings)
                if healthy.get("ok"):
                    break
                time.sleep(0.1)

        browser = None
        if open_browser or (open_browser is None and self.settings.auto_open):
            browser = open_dashboard_browser(self.settings)

        return {
            "started": True,
            "url": self.url,
            "healthy": healthy,
            "browser": browser,
            "TRADING_MODE": "PAPER",
            "LIVE_TRADING_ENABLED": False,
        }

    def stop(self) -> dict[str, Any]:
        if self._server is not None:
            self._server.should_exit = True
        self.state.running = False
        return {"stopped": True, "url": self.url}

    def status(self) -> dict[str, Any]:
        healthy = check_dashboard_health(self.settings)
        alive = bool(self._thread and self._thread.is_alive())
        return {
            "running": alive,
            "url": self.url,
            "healthy": healthy,
            "TRADING_MODE": "PAPER",
            "LIVE_TRADING_ENABLED": False,
        }


_SERVER: DashboardServer | None = None


def get_dashboard_server() -> DashboardServer:
    global _SERVER
    if _SERVER is None:
        _SERVER = DashboardServer()
    return _SERVER
