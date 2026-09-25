from __future__ import annotations

import hashlib
import json
from typing import Any

from crypto_trading_mcp.learning.models import ModelVersion


class ModelVersionRegistry:
    def __init__(self) -> None:
        self.versions: list[ModelVersion] = []
        self._counter = 0

    def next_version(self, prefix: str = "model_xgb") -> str:
        self._counter += 1
        return f"{prefix}_v{self._counter:03d}"

    def register(self, **kwargs: Any) -> ModelVersion:
        if "model_version" not in kwargs:
            kwargs["model_version"] = self.next_version()
        mv = ModelVersion(**kwargs)
        self.versions.append(mv)
        return mv

    def champion(self) -> ModelVersion | None:
        for v in reversed(self.versions):
            if v.champion:
                return v
        return None

    def challenger(self) -> ModelVersion | None:
        for v in reversed(self.versions):
            if not v.champion:
                return v
        return None

    def list(self) -> list[dict[str, Any]]:
        return [v.to_dict() for v in self.versions]


def stable_hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
