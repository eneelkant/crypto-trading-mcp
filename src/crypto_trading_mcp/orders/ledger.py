from __future__ import annotations

from typing import Any

from crypto_trading_mcp.orders.intent import IntentStatus, OrderIntent
from crypto_trading_mcp.persistence.base import DurableStore
from crypto_trading_mcp.persistence.sqlite_store import SqliteDurableStore


class DuplicateOrderError(RuntimeError):
    pass


class OrderIntentLedger:
    """Persist intents before submission; durable idempotency across restarts."""

    COLLECTION = "order_intents"
    IDEM_COLLECTION = "order_idempotency"

    def __init__(self, store: DurableStore | None = None) -> None:
        self.store = store or SqliteDurableStore()

    def persist(self, intent: OrderIntent) -> OrderIntent:
        existing = self.store.get_json(self.IDEM_COLLECTION, intent.idempotency_key)
        if existing and existing.get("intent_id") != intent.intent_id:
            raise DuplicateOrderError(
                f"Idempotency key already used by {existing.get('intent_id')}"
            )
        intent.status = IntentStatus.PERSISTED
        payload = intent.to_public_dict()
        self.store.put_json(self.COLLECTION, intent.intent_id, payload)
        self.store.put_json(
            self.IDEM_COLLECTION,
            intent.idempotency_key,
            {"intent_id": intent.intent_id, "status": intent.status.value},
        )
        return intent

    def mark(
        self,
        intent_id: str,
        status: IntentStatus,
        *,
        reason_codes: list[str] | None = None,
        exchange_order_id: str | None = None,
    ) -> dict[str, Any]:
        row = self.store.get_json(self.COLLECTION, intent_id)
        if not row:
            raise KeyError(f"Unknown intent: {intent_id}")
        row["status"] = status.value
        if reason_codes is not None:
            row["reason_codes"] = reason_codes
        if exchange_order_id is not None:
            row["exchange_order_id"] = exchange_order_id
        self.store.put_json(self.COLLECTION, intent_id, row)
        idem = row.get("idempotency_key")
        if idem:
            self.store.put_json(
                self.IDEM_COLLECTION,
                str(idem),
                {"intent_id": intent_id, "status": status.value},
            )
        return row

    def get(self, intent_id: str) -> dict[str, Any] | None:
        return self.store.get_json(self.COLLECTION, intent_id)

    def find_by_idempotency(self, key: str) -> dict[str, Any] | None:
        ref = self.store.get_json(self.IDEM_COLLECTION, key)
        if not ref:
            return None
        return self.get(str(ref["intent_id"]))

    def list_intents(self, *, limit: int = 100) -> list[dict[str, Any]]:
        return self.store.list_json(self.COLLECTION, limit=limit)

    def would_duplicate(self, idempotency_key: str) -> bool:
        return self.store.get_json(self.IDEM_COLLECTION, idempotency_key) is not None
