from __future__ import annotations

import http.client
from typing import Any
from urllib.parse import urlparse

from crypto_trading_mcp.dashboard.config import DashboardSettings


def check_dashboard_health(settings: DashboardSettings, *, timeout: float = 2.0) -> dict[str, Any]:
    parsed = urlparse(settings.url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or settings.port
    try:
        conn = http.client.HTTPConnection(host, port, timeout=timeout)
        conn.request("GET", "/api/health")
        resp = conn.getresponse()
        body = resp.read().decode("utf-8", errors="replace")
        ok = resp.status == 200
        return {"ok": ok, "status_code": resp.status, "body": body, "url": settings.url}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "url": settings.url}
