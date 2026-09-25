from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from crypto_trading_mcp.config.settings import REPO_ROOT
from crypto_trading_mcp.strategy.repository import StrategyKnowledgeService, StrategyRepository
from crypto_trading_mcp.strategy.schema import StrategyConfig, load_strategy_config


STRATEGY_PATH = REPO_ROOT / "strategies" / "multi_model_po3_vwap_strategy.json"


def test_strategy_json_valid_and_schema():
    raw = json.loads(STRATEGY_PATH.read_text(encoding="utf-8"))
    config = StrategyConfig.model_validate(raw)
    assert config.strategy_metadata.version == "1.0.0"
    assert [m.model_id for m in config.trading_models] == ["M1", "M2", "M3", "M4"]
    assert all(m.enabled for m in config.trading_models)


def test_strategy_config_hash_stable():
    config = load_strategy_config(STRATEGY_PATH)
    assert len(config.config_hash()) == 64
    assert config.config_hash() == load_strategy_config(STRATEGY_PATH).config_hash()


def test_strategy_repository_loads_reference():
    repo = StrategyRepository()
    record = repo.default()
    assert record.strategy_id == "multi_model_po3_vwap"
    assert record.version == "1.0.0"
    assert record.status.value == "reference"
    assert set(record.enabled_models) == {"M1", "M2", "M3", "M4"}


def test_strategy_knowledge_and_agent_map():
    knowledge = StrategyKnowledgeService()
    bundle = knowledge.knowledge_bundle()
    assert bundle["strategy_id"] == "multi_model_po3_vwap"
    assert "disclaimer" in bundle
    assert knowledge.primary_agents_for("M1")
    assert "strategy" in knowledge.primary_agents_for("M2")
    assert "M3" in knowledge.models_for_agent("technical_analysis")


def test_malformed_strategy_rejected(tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"strategy_metadata": {"name": "x"}}), encoding="utf-8")
    with pytest.raises(ValidationError):
        load_strategy_config(bad)


def test_duplicate_model_ids_rejected():
    raw = json.loads(STRATEGY_PATH.read_text(encoding="utf-8"))
    raw["trading_models"].append(dict(raw["trading_models"][0]))
    with pytest.raises(ValidationError):
        StrategyConfig.model_validate(raw)
