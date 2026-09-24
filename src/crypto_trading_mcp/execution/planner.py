from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from crypto_trading_mcp.risk.config import merge_effective_limits
from crypto_trading_mcp.risk.models import GlobalRiskLimits, TradeProposal
from crypto_trading_mcp.strategy.schema import StrategyConfig, StrategyRecord


class TradePlan(BaseModel):
    strategy_id: str
    strategy_version: str
    model_ids: list[str] = Field(default_factory=list)
    symbol: str
    side: str
    entry_price: float
    quantity: float
    notional: float
    stop_loss: float | None = None
    take_profit: float | None = None
    risk_amount: float = 0.0
    expected_fee: float = 0.0
    expected_slippage: float = 0.0
    risk_reward_ratio: float | None = None
    time_horizon: str = "intraday"
    confidence: float = 0.0
    invalidation_conditions: list[str] = Field(default_factory=list)
    status: str = "PROPOSED"  # PROPOSED | NO_TRADE
    reason: str | None = None
    confluence: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def to_proposal(
        self,
        *,
        current_price: float,
        liquidity_usd: float | None,
        market_data_stale: bool,
        bars_since_last_trade: int | None,
    ) -> TradeProposal:
        return TradeProposal(
            symbol=self.symbol,
            side=self.side,
            quantity=self.quantity,
            notional=self.notional,
            entry_price=self.entry_price,
            stop_loss=self.stop_loss,
            take_profit=self.take_profit,
            current_price=current_price,
            estimated_fees=self.expected_fee,
            estimated_slippage_pct=self.expected_slippage,
            confidence=self.confidence,
            model_ids=self.model_ids,
            strategy_id=self.strategy_id,
            strategy_version=self.strategy_version,
            liquidity_usd=liquidity_usd,
            market_data_stale=market_data_stale,
            bars_since_last_trade=bars_since_last_trade,
        )


class TradePlanner:
    """Builds non-executable trade plans from consensus + strategy features."""

    def __init__(self, global_limits: GlobalRiskLimits | None = None) -> None:
        self.global_limits = global_limits or GlobalRiskLimits()

    def plan(
        self,
        *,
        strategy_record: StrategyRecord,
        consensus: dict[str, Any],
        feature_bundle: dict[str, Any],
        equity: float,
        fee_rate: float = 0.001,
        slippage_pct: float = 0.0005,
    ) -> TradePlan:
        decision = str(consensus.get("decision", "NO_TRADE")).upper()
        confidence = float(consensus.get("confidence", 0.0))
        confluence = feature_bundle.get("confluence", {})
        confirmed_ids = list(confluence.get("confirmed_ids", []))
        strategy = strategy_record.config

        base = TradePlan(
            strategy_id=strategy_record.strategy_id,
            strategy_version=strategy_record.version,
            model_ids=confirmed_ids,
            symbol="",
            side="FLAT",
            entry_price=0.0,
            quantity=0.0,
            notional=0.0,
            confidence=confidence,
            confluence=confluence,
            invalidation_conditions=list(
                consensus.get("invalidating_conditions", [])
            ),
        )

        if decision in {"NO_TRADE", "NEUTRAL", "HOLD"}:
            base.status = "NO_TRADE"
            base.reason = f"Consensus decision={decision}"
            return base
        if not confirmed_ids:
            base.status = "NO_TRADE"
            base.reason = "NO_VALID_MODEL"
            return base

        features = feature_bundle.get("features", {})
        entry = features.get("last_close")
        if not isinstance(entry, (int, float)):
            base.status = "NO_TRADE"
            base.reason = "STRATEGY_DATA_UNAVAILABLE"
            return base

        side = "LONG" if decision == "LONG" else "SHORT" if decision == "SHORT" else None
        if side is None:
            base.status = "NO_TRADE"
            base.reason = f"Unsupported decision {decision}"
            return base

        stop = feature_bundle.get("stop_long" if side == "LONG" else "stop_short")
        atr_feature = features.get("atr_14", {})
        atr_val = atr_feature.get("value") if isinstance(atr_feature, dict) else None
        if stop is None and isinstance(atr_val, (int, float)):
            mult = strategy.risk_management.atr_fallback_multiplier
            stop = entry - mult * atr_val if side == "LONG" else entry + mult * atr_val

        limits = merge_effective_limits(self.global_limits, strategy)
        risk_pct = limits["risk_per_trade_pct"]
        risk_budget = equity * risk_pct
        if stop is None or abs(entry - stop) <= 0:
            base.status = "NO_TRADE"
            base.reason = "INVALID_STOP"
            base.entry_price = float(entry)
            base.side = side
            return base

        stop_distance = abs(entry - stop)
        quantity = risk_budget / stop_distance
        # Cap by max trade / position notionals.
        max_notional = equity * min(limits["max_trade_pct"], limits["max_position_pct"])
        quantity = min(quantity, max_notional / entry)
        notional = quantity * entry
        target_rr = strategy.risk_management.target_risk_reward_ratio
        take_profit = (
            entry + target_rr * stop_distance
            if side == "LONG"
            else entry - target_rr * stop_distance
        )
        rr = abs(take_profit - entry) / stop_distance
        fee = notional * fee_rate

        return TradePlan(
            strategy_id=strategy_record.strategy_id,
            strategy_version=strategy_record.version,
            model_ids=confirmed_ids,
            symbol="",  # filled by caller
            side=side,
            entry_price=float(entry),
            quantity=float(quantity),
            notional=float(notional),
            stop_loss=float(stop),
            take_profit=float(take_profit),
            risk_amount=float(quantity * stop_distance),
            expected_fee=float(fee),
            expected_slippage=float(slippage_pct),
            risk_reward_ratio=float(rr),
            time_horizon=strategy.strategy_metadata.execution_timeframe,
            confidence=confidence,
            invalidation_conditions=list(consensus.get("invalidating_conditions", [])),
            status="PROPOSED",
            confluence=confluence,
        )
