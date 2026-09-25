from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from crypto_trading_mcp.config.settings import REPO_ROOT
from crypto_trading_mcp.strategy.schema import (
    StrategyConfig,
    StrategyRecord,
    StrategyStatus,
    build_strategy_record,
    load_strategy_config,
)

STRATEGIES_DIR = REPO_ROOT / "strategies"
DEFAULT_STRATEGY_FILE = "multi_model_po3_vwap_strategy.json"


class StrategyRepository:
    """Version-aware strategy store. Does not overwrite historical records."""

    def __init__(self, strategies_dir: Path | None = None) -> None:
        self.strategies_dir = strategies_dir or STRATEGIES_DIR
        self._records: dict[tuple[str, str], StrategyRecord] = {}
        self._load_disk()

    def _load_disk(self) -> None:
        if not self.strategies_dir.exists():
            return
        for path in sorted(self.strategies_dir.glob("*.json")):
            config = load_strategy_config(path)
            record = build_strategy_record(
                config,
                source_path=str(path),
                status=StrategyStatus.REFERENCE,
            )
            key = (record.strategy_id, record.version)
            # Preserve first-seen history; do not overwrite.
            if key not in self._records:
                self._records[key] = record

    def register(self, record: StrategyRecord, *, overwrite: bool = False) -> None:
        key = (record.strategy_id, record.version)
        if key in self._records and not overwrite:
            existing = self._records[key]
            if existing.config_hash != record.config_hash:
                raise ValueError(
                    f"Strategy {record.strategy_id}@{record.version} already registered "
                    "with a different config hash; refusing overwrite."
                )
            return
        self._records[key] = record

    def get(
        self,
        strategy_id: str,
        version: str | None = None,
    ) -> StrategyRecord:
        if version is not None:
            key = (strategy_id, version)
            if key not in self._records:
                raise KeyError(f"Unknown strategy {strategy_id}@{version}")
            return self._records[key]
        versions = sorted(
            (v for (sid, v) in self._records if sid == strategy_id),
            reverse=True,
        )
        if not versions:
            raise KeyError(f"Unknown strategy {strategy_id}")
        return self._records[(strategy_id, versions[0])]

    def list(self) -> list[StrategyRecord]:
        return sorted(
            self._records.values(),
            key=lambda r: (r.strategy_id, r.version),
        )

    def default(self) -> StrategyRecord:
        return self.get("multi_model_po3_vwap", "1.0.0")


class StrategyKnowledgeService:
    """Structured domain knowledge for agents. No LLM fine-tuning."""

    def __init__(
        self,
        repository: StrategyRepository | None = None,
        agent_map_path: Path | None = None,
    ) -> None:
        self.repository = repository or StrategyRepository()
        self.agent_map_path = agent_map_path or (
            REPO_ROOT / "config" / "strategy_agent_map.yaml"
        )
        self._agent_map = self._load_agent_map()

    def _load_agent_map(self) -> dict[str, Any]:
        if not self.agent_map_path.exists():
            return {}
        with self.agent_map_path.open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        return data if isinstance(data, dict) else {}

    def get_strategy(
        self,
        strategy_id: str = "multi_model_po3_vwap",
        version: str | None = "1.0.0",
    ) -> StrategyRecord:
        return self.repository.get(strategy_id, version)

    def knowledge_bundle(
        self,
        strategy_id: str = "multi_model_po3_vwap",
        version: str | None = "1.0.0",
    ) -> dict[str, Any]:
        record = self.get_strategy(strategy_id, version)
        config = record.config
        return {
            "strategy_id": record.strategy_id,
            "name": record.name,
            "version": record.version,
            "config_hash": record.config_hash,
            "status": record.status.value,
            "metadata": config.strategy_metadata.model_dump(),
            "risk_management": config.risk_management.model_dump(),
            "signal_filters": config.signal_filters.model_dump(),
            "enabled_models": [
                {
                    "model_id": m.model_id,
                    "name": m.name,
                    "type": m.type,
                    "rules": m.rules,
                    "primary_agents": self.primary_agents_for(m.model_id),
                }
                for m in config.enabled_models()
            ],
            "disclaimer": (
                "Reference specification only. Not a profitability guarantee. "
                "Does not enable live trading."
            ),
        }

    def primary_agents_for(self, model_id: str) -> list[str]:
        models = self._agent_map.get("models", {})
        entry = models.get(model_id, {}) if isinstance(models, dict) else {}
        agents = entry.get("primary_agents", []) if isinstance(entry, dict) else []
        return [str(a) for a in agents]

    def models_for_agent(self, agent_id: str) -> list[str]:
        models = self._agent_map.get("models", {})
        out: list[str] = []
        if not isinstance(models, dict):
            return out
        for model_id, entry in models.items():
            agents = entry.get("primary_agents", []) if isinstance(entry, dict) else []
            if agent_id in agents:
                out.append(str(model_id))
        return out
