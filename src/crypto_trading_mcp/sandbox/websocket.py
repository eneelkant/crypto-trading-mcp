from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any, Callable

from crypto_trading_mcp.market.freshness import MarketDataFreshness


class SandboxWebSocketClient:
    """Sandbox WS client with reconnect/backoff/stale/duplicate protection."""

    def __init__(
        self,
        *,
        url: str,
        connect: Callable[[], Any] | None = None,
        enabled: bool = True,
        max_age_seconds: float = 30.0,
        max_retries: int = 5,
        base_backoff: float = 0.05,
    ) -> None:
        self.url = url
        self._connect = connect
        self.enabled = enabled
        self.connected = False
        self.last_message_at: str | None = None
        self.reconnect_attempts = 0
        self.last_error: str | None = None
        self._seen: set[str] = set()
        self.freshness = MarketDataFreshness(max_age_seconds=max_age_seconds)
        self.max_retries = max_retries
        self.base_backoff = base_backoff

    def connect(self) -> dict[str, Any]:
        if not self.enabled:
            return {"enabled": False, "connected": False}
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            self.reconnect_attempts = attempt + 1
            try:
                if self._connect is not None:
                    self._connect()
                self.connected = True
                self.last_error = None
                return {"enabled": True, "connected": True, "url": self.url}
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                self.connected = False
                self.last_error = str(exc)
                time.sleep(self.base_backoff * (2**attempt))
        return {"enabled": True, "connected": False, "error": str(last_exc)}

    def reconnect(self) -> dict[str, Any]:
        self.connected = False
        return self.connect()

    def on_message(self, message_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if message_id in self._seen:
            return {"accepted": False, "duplicate": True}
        self._seen.add(message_id)
        self.last_message_at = datetime.now(UTC).isoformat()
        return {"accepted": True, "duplicate": False, "keys": list(payload)}

    def allows_new_trades(self) -> bool:
        if not self.connected:
            return False
        return self.freshness.is_fresh(self.last_message_at)

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "connected": self.connected,
            "url": self.url,
            "last_message_at": self.last_message_at,
            "reconnect_attempts": self.reconnect_attempts,
            "last_error": self.last_error,
            "allows_new_trades": self.allows_new_trades() if self.last_message_at else False,
        }
