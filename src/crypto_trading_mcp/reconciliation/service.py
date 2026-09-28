from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Callable

from crypto_trading_mcp.persistence.base import DurableStore
from crypto_trading_mcp.persistence.sqlite_store import SqliteDurableStore


class ReconciliationState(str, Enum):
    RECONCILED = "RECONCILED"
    DRIFT_DETECTED = "DRIFT_DETECTED"
    RECONCILIATION_FAILED = "RECONCILIATION_FAILED"
    EXCHANGE_UNAVAILABLE = "EXCHANGE_UNAVAILABLE"


class ExchangeReconciliationService:
    """Compare local ledger state against exchange-truth snapshots."""

    COLLECTION = "reconciliation"

    def __init__(
        self,
        store: DurableStore | None = None,
        *,
        event_sink: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.store = store or SqliteDurableStore()
        self.event_sink = event_sink
        self.last: dict[str, Any] | None = None

    def compare(
        self,
        *,
        local: dict[str, Any],
        exchange: dict[str, Any] | None,
        exchange_error: str | None = None,
    ) -> dict[str, Any]:
        ts = datetime.now(UTC).isoformat()
        if exchange_error:
            result = {
                "state": ReconciliationState.EXCHANGE_UNAVAILABLE.value,
                "healthy": False,
                "allows_new_live_orders": False,
                "timestamp": ts,
                "error": exchange_error,
                "drifts": [],
            }
            return self._persist(result)

        if exchange is None:
            result = {
                "state": ReconciliationState.RECONCILIATION_FAILED.value,
                "healthy": False,
                "allows_new_live_orders": False,
                "timestamp": ts,
                "error": "missing_exchange_snapshot",
                "drifts": [],
            }
            return self._persist(result)

        drifts: list[str] = []
        for field in (
            "balances",
            "available_balances",
            "positions",
            "open_orders",
            "fills",
            "realized_pnl",
            "unrealized_pnl",
        ):
            if field in local or field in exchange:
                if local.get(field) != exchange.get(field):
                    drifts.append(field)

        # Quantity / avg entry nested checks when present
        local_pos = local.get("position_details") or {}
        exch_pos = exchange.get("position_details") or {}
        for symbol in set(local_pos) | set(exch_pos):
            lp = local_pos.get(symbol) or {}
            ep = exch_pos.get(symbol) or {}
            if lp.get("quantity") != ep.get("quantity"):
                drifts.append(f"position_qty:{symbol}")
            if lp.get("avg_entry") != ep.get("avg_entry"):
                drifts.append(f"avg_entry:{symbol}")

        if drifts:
            state = ReconciliationState.DRIFT_DETECTED
            healthy = False
        else:
            state = ReconciliationState.RECONCILED
            healthy = True

        result = {
            "state": state.value,
            "healthy": healthy,
            "allows_new_live_orders": healthy,
            "timestamp": ts,
            "drifts": drifts,
        }
        return self._persist(result)

    def _persist(self, result: dict[str, Any]) -> dict[str, Any]:
        self.last = result
        key = result["timestamp"]
        self.store.put_json(self.COLLECTION, key, result)
        self.store.put_json(self.COLLECTION, "latest", result)
        if self.event_sink:
            self.event_sink({"type": "RECONCILIATION", **result})
        return result

    def status(self) -> dict[str, Any]:
        latest = self.store.get_json(self.COLLECTION, "latest") or self.last or {
            "state": ReconciliationState.RECONCILIATION_FAILED.value,
            "healthy": False,
            "allows_new_live_orders": False,
        }
        return latest
