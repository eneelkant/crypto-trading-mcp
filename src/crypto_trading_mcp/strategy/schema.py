from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator


class StrategyStatus(StrEnum):
    REFERENCE = "reference"
    CANDIDATE = "candidate"
    PAPER = "paper"
    DISABLED = "disabled"


class PartialTakeProfit(BaseModel):
    enabled: bool = True
    exit_quantity_percent: float = Field(ge=0, le=100)


class StrategyCircuitBreakers(BaseModel):
    max_daily_loss_percent: float = Field(gt=0)
    max_trades_per_day: int = Field(gt=0)
    cooldown_bars_between_trades: int = Field(ge=0)
    eod_flat_close_enabled: bool = True


class StrategyRiskManagement(BaseModel):
    risk_per_trade_percent: float = Field(gt=0)
    min_risk_reward_ratio: float = Field(gt=0)
    target_risk_reward_ratio: float = Field(gt=0)
    stop_loss_method: str
    atr_fallback_multiplier: float = Field(gt=0)
    partial_take_profit_1r: PartialTakeProfit
    move_stop_loss_to_breakeven_at_1r: bool
    circuit_breakers: StrategyCircuitBreakers


class ADXFilter(BaseModel):
    length: int = Field(gt=0)
    min_strength: float = Field(gt=0)


class EMAAlignment(BaseModel):
    fast_ema: int = Field(gt=0)
    slow_ema: int = Field(gt=0)
    structural_ema: int = Field(gt=0)
    long_term_ema: int = Field(gt=0)


class VolumeFilter(BaseModel):
    length: int = Field(gt=0)
    multiplier: float = Field(gt=0)


class SignalFilters(BaseModel):
    adx: ADXFilter
    ema_alignment: EMAAlignment
    volume: VolumeFilter


class TradingModel(BaseModel):
    model_id: str
    name: str
    type: str
    enabled: bool = True
    rules: dict[str, Any] = Field(default_factory=dict)

    @field_validator("model_id")
    @classmethod
    def _model_id_nonempty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("model_id must be non-empty")
        return value


class StrategyMetadata(BaseModel):
    name: str
    version: str
    description: str
    author: str
    supported_markets: list[str]
    recommended_pairs: list[str]
    execution_timeframe: str
    bias_timeframe: str


class StrategyConfig(BaseModel):
    strategy_metadata: StrategyMetadata
    risk_management: StrategyRiskManagement
    signal_filters: SignalFilters
    trading_models: list[TradingModel]

    @field_validator("trading_models")
    @classmethod
    def _unique_model_ids(cls, models: list[TradingModel]) -> list[TradingModel]:
        ids = [m.model_id for m in models]
        if len(ids) != len(set(ids)):
            raise ValueError("trading_models must have unique model_id values")
        if not models:
            raise ValueError("trading_models must not be empty")
        return models

    def enabled_models(self) -> list[TradingModel]:
        return [m for m in self.trading_models if m.enabled]

    def model_by_id(self, model_id: str) -> TradingModel | None:
        for model in self.trading_models:
            if model.model_id == model_id:
                return model
        return None

    def canonical_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))

    def config_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


class StrategyRecord(BaseModel):
    strategy_id: str
    name: str
    version: str
    config_hash: str
    enabled_models: list[str]
    created_at: datetime
    status: StrategyStatus = StrategyStatus.REFERENCE
    source_path: str | None = None
    config: StrategyConfig


def slugify_strategy_id(name: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in name)
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_") or "strategy"


def load_strategy_config(path: Path | str) -> StrategyConfig:
    raw = Path(path).read_text(encoding="utf-8")
    data = json.loads(raw)
    return StrategyConfig.model_validate(data)


def build_strategy_record(
    config: StrategyConfig,
    *,
    strategy_id: str | None = None,
    status: StrategyStatus = StrategyStatus.REFERENCE,
    source_path: str | None = None,
    created_at: datetime | None = None,
) -> StrategyRecord:
    sid = strategy_id or slugify_strategy_id(config.strategy_metadata.name)
    # Prefer stable id for the reference suite.
    if "po3" in sid and "vwap" in sid:
        sid = "multi_model_po3_vwap"
    return StrategyRecord(
        strategy_id=sid,
        name=config.strategy_metadata.name,
        version=config.strategy_metadata.version,
        config_hash=config.config_hash(),
        enabled_models=[m.model_id for m in config.enabled_models()],
        created_at=created_at or datetime.now(UTC),
        status=status,
        source_path=source_path,
        config=config,
    )
