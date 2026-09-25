from __future__ import annotations

from typing import Any

from crypto_trading_mcp.learning.engine import LearningEngine, get_learning_engine
from crypto_trading_mcp.learning.models import TradeLearningRecord


class LearningToolSurface:
    """MCP surface for self-learning. Never places exchange orders."""

    def __init__(self, engine: LearningEngine | None = None) -> None:
        self.engine = engine or get_learning_engine()

    def get_learning_status(self) -> dict[str, Any]:
        return self.engine.status()

    def get_learning_memory(self) -> dict[str, Any]:
        return {
            "summary": self.engine.memory.summary(),
            "records": [r.to_dict() for r in self.engine.memory.records[-50:]],
        }

    def search_learning_memory(self, features: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.engine.learning_context_for(features=features or {})

    def get_trade_postmortem(self, trade_id: str | None = None) -> dict[str, Any]:
        if trade_id:
            for pm in reversed(self.engine.post_mortems):
                if pm.get("trade_id") == trade_id:
                    return pm
            return {"error": "NOT_FOUND", "trade_id": trade_id}
        return self.engine.post_mortems[-1] if self.engine.post_mortems else {}

    def get_failure_patterns(self) -> dict[str, Any]:
        cats: dict[str, int] = {}
        for r in self.engine.memory.failures():
            for c in r.failure_categories:
                cats[c.value] = cats.get(c.value, 0) + 1
        return {"patterns": cats, "count": len(self.engine.memory.failures())}

    def get_success_patterns(self) -> dict[str, Any]:
        cats: dict[str, int] = {}
        for r in self.engine.memory.successes():
            for c in r.success_categories:
                cats[c.value] = cats.get(c.value, 0) + 1
        return {"patterns": cats, "count": len(self.engine.memory.successes())}

    def get_calibration(self) -> dict[str, Any]:
        return self.engine.calibration.status()

    def get_brier_score(self) -> dict[str, Any]:
        return self.engine.calibration.status()

    def get_model_status(self) -> dict[str, Any]:
        return {
            "champion": None
            if self.engine.registry.champion() is None
            else self.engine.registry.champion().to_dict(),
            "challenger": None
            if self.engine.registry.challenger() is None
            else self.engine.registry.challenger().to_dict(),
        }

    def get_model_versions(self) -> dict[str, Any]:
        return {"versions": self.engine.registry.list()}

    def get_learning_proposals(self) -> dict[str, Any]:
        return {"proposals": self.engine.proposals.list()}

    def get_champion_strategy(self) -> dict[str, Any]:
        c = self.engine.registry.champion()
        return {"champion": None if c is None else c.to_dict()}

    def get_challenger_strategy(self) -> dict[str, Any]:
        c = self.engine.registry.challenger()
        return {"challenger": None if c is None else c.to_dict()}

    def run_postmortem(self, record: dict[str, Any]) -> dict[str, Any]:
        rec = TradeLearningRecord.model_validate(record)
        return self.engine.on_trade_close(rec)

    def run_reflection(self) -> dict[str, Any]:
        if not self.engine.memory.records:
            return {"ok": False, "reason": "no_records"}
        from crypto_trading_mcp.learning.post_mortem import run_post_mortem

        rec = self.engine.memory.records[-1]
        pm = run_post_mortem(rec)
        reflection = self.engine.reflection.reflect(rec, pm)
        self.engine.reflections.append(reflection.to_dict())
        return reflection.to_dict()

    def run_retraining(self) -> dict[str, Any]:
        return self.engine.run_retraining(seed=42)

    def run_learning_validation(self, proposal_id: str | None = None) -> dict[str, Any]:
        return self.engine.validate_learning(proposal_id)

    def get_learning_audit(self, limit: int = 100) -> dict[str, Any]:
        return {"events": self.engine.audit.list(limit=limit)}

    def rollback_learning_candidate(self, reason: str = "manual") -> dict[str, Any]:
        return self.engine.rollback_candidate(reason)
