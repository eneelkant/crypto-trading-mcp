from __future__ import annotations

import hashlib
import json
from typing import Any


class LLMBacktestCache:
    """Deterministic cache so backtests never spam network LLM calls."""

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}
        self.hits = 0
        self.misses = 0

    @staticmethod
    def make_key(
        *,
        strategy_id: str,
        timestamp: str,
        market_state_hash: str,
        agent_name: str,
        model: str,
        prompt_version: str,
    ) -> str:
        raw = "|".join(
            [strategy_id, timestamp, market_state_hash, agent_name, model, prompt_version]
        )
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, key: str) -> dict[str, Any] | None:
        if key in self._store:
            self.hits += 1
            return self._store[key]
        self.misses += 1
        return None

    def put(self, key: str, value: dict[str, Any]) -> None:
        # Persist response hash for audit
        payload = dict(value)
        payload.setdefault(
            "response_hash",
            hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()[:16],
        )
        self._store[key] = payload
