from __future__ import annotations

from typing import Any

from crypto_trading_mcp.config.settings import get_settings


class ExchangeHealth:
    def __init__(self, name: str) -> None:
        self.name = name
        self.last_error: str | None = None
        self.ok: bool = True

    def mark_ok(self) -> None:
        self.ok = True
        self.last_error = None

    def mark_error(self, message: str) -> None:
        self.ok = False
        self.last_error = message

    def status(self) -> dict[str, Any]:
        settings = get_settings()
        return {
            "exchange": self.name,
            "ok": self.ok,
            "last_error": self.last_error,
            "TRADING_MODE": settings.trading_mode,
            "LIVE_TRADING_ENABLED": settings.live_trading_enabled,
            "live_orders_allowed": bool(
                settings.trading_mode == "live" and settings.live_trading_enabled
            ),
        }
