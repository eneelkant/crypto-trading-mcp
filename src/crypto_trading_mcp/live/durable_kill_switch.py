from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable

from crypto_trading_mcp.live.kill_switch import LiveKillSwitch
from crypto_trading_mcp.persistence.base import DurableStore
from crypto_trading_mcp.persistence.sqlite_store import SqliteDurableStore
from crypto_trading_mcp.risk.config import KillSwitch


class DurableKillSwitch:
    """Database-backed kill switch that survives process restart."""

    COLLECTION = "kill_switch"
    KEY = "state"

    def __init__(
        self,
        store: DurableStore | None = None,
        *,
        alert_sink: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self.store = store or SqliteDurableStore()
        self.inner = LiveKillSwitch(
            KillSwitch(),
            event_sink=self._persist_event,
            alert_sink=alert_sink,
        )
        self._load()

    def _load(self) -> None:
        row = self.store.get_json(self.COLLECTION, self.KEY)
        if row and row.get("active"):
            self.inner.base.activate(str(row.get("reason") or "restored"))

    def _persist_event(self, event: dict[str, Any]) -> None:
        self.store.put_json(
            self.COLLECTION,
            self.KEY,
            {
                "active": True,
                "reason": event.get("reason"),
                "timestamp": event.get("timestamp") or datetime.now(UTC).isoformat(),
                "cancel_result": event.get("cancel_result"),
            },
        )
        self.store.put_json(
            self.COLLECTION,
            f"event:{event.get('timestamp')}",
            event,
        )

    @property
    def active(self) -> bool:
        row = self.store.get_json(self.COLLECTION, self.KEY)
        if row is None:
            # fail closed if store unreadable — treat missing after init as inactive default
            return self.inner.active
        return bool(row.get("active"))

    def activate(self, reason: str = "operator", *, canceller: Any | None = None) -> dict[str, Any]:
        return self.inner.activate(reason, canceller=canceller, live_mode=bool(canceller))

    def deactivate(self, *, operator_authorized: bool = False) -> None:
        self.inner.deactivate(operator_authorized=operator_authorized)
        self.store.put_json(
            self.COLLECTION,
            self.KEY,
            {
                "active": False,
                "reason": None,
                "timestamp": datetime.now(UTC).isoformat(),
                "cleared_by_operator": True,
            },
        )

    def status(self) -> dict[str, Any]:
        row = self.store.get_json(self.COLLECTION, self.KEY) or {}
        return {
            **self.inner.status(),
            "durable": True,
            "persisted_active": bool(row.get("active")),
            "llm_can_deactivate": False,
        }

    def allows_new_trades(self) -> bool:
        try:
            row = self.store.get_json(self.COLLECTION, self.KEY)
        except Exception:
            return False  # fail closed
        if row is None:
            return not self.inner.active
        return not bool(row.get("active"))
