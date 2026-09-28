from __future__ import annotations

from typing import Any, Callable


class WebSocketMarketFeed:
    """Optional WebSocket feed hook.

    Phase 9 keeps this disabled by default on constrained hosts.
    Callers may inject a connect factory for tests.
    """

    def __init__(
        self,
        *,
        enabled: bool = False,
        connect: Callable[[], Any] | None = None,
    ) -> None:
        self.enabled = enabled
        self._connect = connect
        self.connected = False
        self.last_message_at: str | None = None

    def start(self) -> dict[str, Any]:
        if not self.enabled:
            return {"enabled": False, "connected": False, "reason": "websocket_disabled"}
        if self._connect is not None:
            self._connect()
        self.connected = True
        return {"enabled": True, "connected": True}

    def stop(self) -> dict[str, Any]:
        self.connected = False
        return {"enabled": self.enabled, "connected": False}

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "connected": self.connected,
            "last_message_at": self.last_message_at,
        }
