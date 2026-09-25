from __future__ import annotations

import os
import threading
import webbrowser
from typing import Any

from crypto_trading_mcp.dashboard.config import DashboardSettings

_OPENED = False
_LOCK = threading.Lock()


def _is_ci_or_headless() -> bool:
    if os.environ.get("CI", "").lower() in {"1", "true", "yes"}:
        return True
    if os.environ.get("DASHBOARD_HEADLESS", "").lower() in {"1", "true", "yes"}:
        return True
    if not os.environ.get("DISPLAY") and os.name != "nt" and os.uname().sysname != "Darwin":
        # Linux without DISPLAY; macOS has no DISPLAY but can open browser.
        return True
    return False


def open_dashboard_browser(settings: DashboardSettings, *, force: bool = False) -> dict[str, Any]:
    """Open local dashboard URL once per process. Never opens non-local URLs."""
    global _OPENED
    url = settings.url
    if not url.startswith("http://127.0.0.1") and not url.startswith("http://localhost"):
        return {"opened": False, "reason": "NON_LOCAL_URL_BLOCKED", "url": url}
    if not settings.auto_open and not force:
        return {"opened": False, "reason": "AUTO_OPEN_DISABLED", "url": url}
    if _is_ci_or_headless() and not force:
        return {"opened": False, "reason": "HEADLESS_OR_CI", "url": url}
    with _LOCK:
        if _OPENED and not force:
            return {"opened": False, "reason": "ALREADY_OPENED", "url": url}
        try:
            webbrowser.open(url, new=2)
            _OPENED = True
            return {"opened": True, "url": url}
        except Exception as exc:  # noqa: BLE001
            return {"opened": False, "reason": str(exc), "url": url}


def reset_browser_gate() -> None:
    global _OPENED
    with _LOCK:
        _OPENED = False
