from __future__ import annotations

import asyncio
import threading
from collections import deque
from typing import Any, Callable

from crypto_trading_mcp.dashboard.events import DashboardEvent, EventType
from crypto_trading_mcp.paper.persistence import InMemoryPaperStore, PaperStore


Listener = Callable[[DashboardEvent], None]


class EventBus:
    """In-process pub/sub. Dashboard crash/disconnect must not break publishers."""

    def __init__(self, *, history_limit: int = 5000, store: PaperStore | None = None) -> None:
        self.history_limit = history_limit
        self._history: deque[DashboardEvent] = deque(maxlen=history_limit)
        self._listeners: list[Listener] = []
        self._async_queues: list[asyncio.Queue[DashboardEvent]] = []
        self._lock = threading.RLock()
        self.store = store or InMemoryPaperStore()
        self.publish_errors = 0

    def subscribe(self, listener: Listener) -> None:
        with self._lock:
            self._listeners.append(listener)

    def unsubscribe(self, listener: Listener) -> None:
        with self._lock:
            if listener in self._listeners:
                self._listeners.remove(listener)

    def subscribe_queue(self) -> asyncio.Queue[DashboardEvent]:
        queue: asyncio.Queue[DashboardEvent] = asyncio.Queue(maxsize=1000)
        with self._lock:
            self._async_queues.append(queue)
        return queue

    def unsubscribe_queue(self, queue: asyncio.Queue[DashboardEvent]) -> None:
        with self._lock:
            if queue in self._async_queues:
                self._async_queues.remove(queue)

    def publish(self, event: DashboardEvent | dict[str, Any]) -> DashboardEvent:
        if isinstance(event, dict):
            event = DashboardEvent.model_validate(event)
        with self._lock:
            self._history.append(event)
            listeners = list(self._listeners)
            queues = list(self._async_queues)
        try:
            self.store.save_event(
                {
                    "type": str(event.event_type),
                    "session_id": event.run_id or "dashboard",
                    **event.to_dict(),
                }
            )
        except Exception:  # noqa: BLE001
            self.publish_errors += 1
        for listener in listeners:
            try:
                listener(event)
            except Exception:  # noqa: BLE001
                self.publish_errors += 1
        for queue in queues:
            try:
                queue.put_nowait(event)
            except Exception:  # noqa: BLE001
                self.publish_errors += 1
        return event

    def emit(
        self,
        event_type: EventType | str,
        *,
        payload: dict[str, Any] | None = None,
        agent_id: str | None = None,
        symbol: str | None = None,
        run_id: str | None = None,
        severity: str = "info",
    ) -> DashboardEvent:
        return self.publish(
            DashboardEvent(
                event_type=event_type,
                payload=payload or {},
                agent_id=agent_id,
                symbol=symbol,
                run_id=run_id,
                severity=severity,  # type: ignore[arg-type]
            )
        )

    def history(self, *, limit: int = 200, event_type: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self._history)
        if event_type:
            items = [e for e in items if str(e.event_type) == event_type]
        return [e.to_dict() for e in items[-limit:]]

    def get(self, event_id: str) -> dict[str, Any] | None:
        with self._lock:
            for event in self._history:
                if event.event_id == event_id:
                    return event.to_dict()
        return None


_BUS: EventBus | None = None
_BUS_LOCK = threading.Lock()


def get_event_bus(history_limit: int = 5000) -> EventBus:
    global _BUS
    with _BUS_LOCK:
        if _BUS is None:
            _BUS = EventBus(history_limit=history_limit)
        return _BUS


def reset_event_bus() -> None:
    global _BUS
    with _BUS_LOCK:
        _BUS = None
