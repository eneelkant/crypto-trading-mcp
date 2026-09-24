from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class DataPartition(StrEnum):
    TRAIN = "TRAIN"
    VALIDATION = "VALIDATION"
    OUT_OF_SAMPLE = "OUT_OF_SAMPLE"
    FULL = "FULL"


class AgentMode(StrEnum):
    DETERMINISTIC = "deterministic"
    LLM = "llm"


class NormalizedCandle(BaseModel):
    timestamp: datetime
    symbol: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }


class BacktestIdentity(BaseModel):
    backtest_id: str
    strategy_id: str
    strategy_version: str
    strategy_config_hash: str
    instrument: str
    timeframe: str
    data_source: str
    data_version: str
    date_start: str
    date_end: str
    backtest_config_hash: str
    partition: DataPartition = DataPartition.FULL

    @staticmethod
    def compute_id(
        *,
        strategy_id: str,
        strategy_version: str,
        strategy_config_hash: str,
        data_version: str,
        date_start: str,
        date_end: str,
        backtest_config_hash: str,
        instrument: str,
        timeframe: str,
    ) -> str:
        raw = "|".join(
            [
                strategy_id,
                strategy_version,
                strategy_config_hash,
                data_version,
                date_start,
                date_end,
                backtest_config_hash,
                instrument,
                timeframe,
            ]
        )
        digest = hashlib.sha256(raw.encode()).hexdigest()[:20]
        return f"BT-{digest}"


class EquityPoint(BaseModel):
    timestamp: str
    equity: float
    cash: float
    drawdown: float
    daily_pnl: float = 0.0


class TradeMAE_MFE(BaseModel):
    trade_id: str
    mae: float | None = None
    mfe: float | None = None


class BacktestWarning(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class BacktestResult(BaseModel):
    identity: BacktestIdentity
    initial_capital: float
    final_equity: float
    metrics: dict[str, Any] = Field(default_factory=dict)
    risk_metrics: dict[str, Any] = Field(default_factory=dict)
    equity_curve: list[EquityPoint] = Field(default_factory=list)
    trades: list[dict[str, Any]] = Field(default_factory=list)
    orders: list[dict[str, Any]] = Field(default_factory=list)
    fills: list[dict[str, Any]] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[BacktestWarning] = Field(default_factory=list)
    risk_rejections: int = 0
    structural_hash: str = ""
    disclaimer: str = (
        "Historical backtest results do not guarantee future performance. "
        "Paper/simulation only. Live trading disabled."
    )
    TRADING_MODE: str = "PAPER"
    REAL_MONEY: str = "DISABLED"

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def stable_hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()
