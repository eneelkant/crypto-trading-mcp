from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


class LearningAuditLog:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def record(
        self,
        event: str,
        *,
        trade_id: str | None = None,
        model: str | None = None,
        strategy: str | None = None,
        proposal: str | None = None,
        decision: str | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        entry = {
            "audit_id": f"AUD-{uuid4().hex[:10]}",
            "timestamp": datetime.now(UTC).isoformat(),
            "event": event,
            "trade": trade_id,
            "model": model,
            "strategy": strategy,
            "proposal": proposal,
            "decision": decision,
            "evidence": evidence or {},
        }
        self.events.append(entry)
        return entry

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.events[-limit:]
