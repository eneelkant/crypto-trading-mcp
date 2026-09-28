from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any, Callable


class WebSocketMarketFeed:
    """Production-oriented WebSocket feed hook with reconnect/backoff.

    Disabled by default. Inject ``connect`` for tests or real sockets.
    """

    def __init__(
        self,
        *,
        enabled: bool = False,
        connect: Callable[[], Any] | None = None,
        max_retries: int = 5,
        base_backoff_seconds: float = 0.5,
    ) -> None:
        self.enabled = enabled
        self._connect = connect
        self.max_retries = max_retries
        self.base_backoff_seconds = base_backoff_seconds
        self.connected = False
        self.last_message_at: str | None = None
        self.reconnect_attempts = 0
        self.last_error: str | None = None
        self._seen_message_ids: set[str] = set()

    def start(self) -> dict[str, Any]:
        if not self.enabled:
            return {"enabled": False, "connected": False, "reason": "websocket_disabled"}
        return self._connect_with_retry()

    def _connect_with_retry(self) -> dict[str, Any]:
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            self.reconnect_attempts = attempt + 1
            try:
                if self._connect is not None:
                    self._connect()
                self.connected = True
                self.last_error = None
                return {
                    "enabled": True,
                    "connected": True,
                    "reconnect_attempts": self.reconnect_attempts,
                }
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                self.last_error = str(exc)
                self.connected = False
                time.sleep(self.base_backoff_seconds * (2**attempt))
        return {
            "enabled": True,
            "connected": False,
            "error": str(last_exc) if last_exc else "connect_failed",
            "reconnect_attempts": self.reconnect_attempts,
        }

    def reconnect(self) -> dict[str, Any]:
        self.connected = False
        return self._connect_with_retry()

    def on_message(self, message_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if message_id in self._seen_message_ids:
            return {"duplicate": True, "accepted": False}
        self._seen_message_ids.add(message_id)
        if len(self._seen_message_ids) > 10_000:
            self._seen_message_ids = set(list(self._seen_message_ids)[-1000:])
        self.last_message_at = datetime.now(UTC).isoformat()
        return {"duplicate": False, "accepted": True, "payload_keys": list(payload)}

    def stop(self) -> dict[str, Any]:
        self.connected = False
        return {"enabled": self.enabled, "connected": False}

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "connected": self.connected,
            "last_message_at": self.last_message_at,
            "reconnect_attempts": self.reconnect_attempts,
            "last_error": self.last_error,
        }
