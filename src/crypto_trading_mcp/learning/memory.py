from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from crypto_trading_mcp.config.settings import REPO_ROOT
from crypto_trading_mcp.learning.config import LearningConfig
from crypto_trading_mcp.learning.models import TradeLearningRecord, TradeOutcome
from crypto_trading_mcp.learning.retrieval import build_learning_context


class LearningMemory:
    """Persistent learning memory. JSON failure log is compatibility export only."""

    def __init__(self, config: LearningConfig, store: Any | None = None) -> None:
        self.config = config
        self.store = store
        self._lock = threading.RLock()
        self.records: list[TradeLearningRecord] = []
        self._load_compat()

    def _failure_log_path(self) -> Path:
        path = Path(self.config.failure_log)
        if not path.is_absolute():
            path = REPO_ROOT / path
        return path

    def _load_compat(self) -> None:
        path = self._failure_log_path()
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("trade_id"):
                        try:
                            self.records.append(TradeLearningRecord.model_validate(item))
                        except Exception:
                            continue
        except Exception:
            return

    def _export_compat(self) -> None:
        path = self._failure_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        failures = [
            r.to_dict()
            for r in self.records
            if r.outcome == TradeOutcome.LOSS or r.failure_categories
        ]
        # Never delete — rewrite full historical export
        path.write_text(json.dumps(failures, indent=2, default=str), encoding="utf-8")

    def add(self, record: TradeLearningRecord) -> TradeLearningRecord:
        with self._lock:
            self.records.append(record)
            if self.store is not None and hasattr(self.store, "save_event"):
                self.store.save_event(
                    {
                        "type": "learning_record",
                        "trade_id": record.trade_id,
                        "payload": record.to_dict(),
                    }
                )
            try:
                self._export_compat()
            except Exception:
                pass
            return record

    def failures(self) -> list[TradeLearningRecord]:
        return [r for r in self.records if r.outcome == TradeOutcome.LOSS]

    def successes(self) -> list[TradeLearningRecord]:
        return [r for r in self.records if r.outcome == TradeOutcome.WIN]

    def search(self, features: dict[str, Any], **kwargs: Any):
        return build_learning_context(features, self.records, config=self.config, **kwargs)

    def summary(self) -> dict[str, Any]:
        return {
            "total": len(self.records),
            "failures": len(self.failures()),
            "successes": len(self.successes()),
            "enabled": self.config.memory_enabled,
        }
