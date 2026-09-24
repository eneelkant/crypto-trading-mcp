from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from crypto_trading_mcp.execution.planner import TradePlan, TradePlanner
from crypto_trading_mcp.market.data import MockMarketData
from crypto_trading_mcp.market.models import Candle
from crypto_trading_mcp.portfolio.manager import PortfolioManager
from crypto_trading_mcp.providers.order_flow import UnavailableOrderFlowProvider
from crypto_trading_mcp.risk.config import KillSwitch, load_risk_config
from crypto_trading_mcp.risk.engine import RiskEngine
from crypto_trading_mcp.risk.models import PortfolioRiskSnapshot
from crypto_trading_mcp.strategy.features import StrategyFeatureEngine, timeframe_to_minutes
from crypto_trading_mcp.strategy.repository import StrategyKnowledgeService


def synthesize_timeframe(candles: list[Candle], timeframe: str) -> list[Candle]:
    """Aggregate lower-TF candles into higher-TF closed bars (no look-ahead)."""
    minutes = timeframe_to_minutes(timeframe)
    if not candles:
        return []
    bucket: dict[int, list[Candle]] = {}
    for candle in candles:
        ts = int(candle.timestamp.timestamp())
        key = ts - (ts % (minutes * 60))
        bucket.setdefault(key, []).append(candle)
    out: list[Candle] = []
    for key in sorted(bucket):
        group = bucket[key]
        out.append(
            Candle(
                timestamp=datetime.fromtimestamp(key, tz=UTC),
                open=group[0].open,
                high=max(c.high for c in group),
                low=min(c.low for c in group),
                close=group[-1].close,
                volume=sum(c.volume for c in group),
            )
        )
    return out


class CircuitBreakerService:
    def __init__(self, kill_switch: KillSwitch) -> None:
        self.kill_switch = kill_switch
        self.config = load_risk_config()
        self._halted = False
        self._reasons: list[str] = []

    @property
    def halted(self) -> bool:
        return self._halted or self.kill_switch.active

    def reasons(self) -> list[str]:
        reasons = list(self._reasons)
        if self.kill_switch.active:
            reasons.append("KILL_SWITCH_ACTIVE")
        return reasons

    def evaluate_portfolio(self, portfolio: PortfolioRiskSnapshot, limits: dict[str, Any]) -> None:
        self._reasons = []
        cb = self.config.circuit_breakers
        if cb.get("daily_loss_limit", True) and portfolio.equity > 0:
            if abs(min(portfolio.daily_pnl, 0.0)) / portfolio.equity >= limits["max_daily_loss_pct"]:
                self._halted = True
                self._reasons.append("DAILY_LOSS_LIMIT")
        if cb.get("drawdown_limit", True):
            if portfolio.drawdown_pct >= limits["max_drawdown_pct"]:
                self._halted = True
                self._reasons.append("DRAWDOWN_LIMIT")
        if cb.get("excessive_trade_frequency", True):
            if portfolio.trades_today >= limits["max_trades_per_day"]:
                self._halted = True
                self._reasons.append("TRADE_COUNT_LIMIT")

    def halt(self, reason: str) -> None:
        self._halted = True
        self._reasons.append(reason)


class ProposalService:
    """Strategy → Consensus → Trade Plan → Risk (no execution)."""

    def __init__(
        self,
        *,
        portfolio: PortfolioManager | None = None,
        risk_engine: RiskEngine | None = None,
        knowledge: StrategyKnowledgeService | None = None,
        kill_switch: KillSwitch | None = None,
    ) -> None:
        self.portfolio = portfolio or PortfolioManager()
        self.kill_switch = kill_switch or KillSwitch()
        self.risk_engine = risk_engine or RiskEngine(kill_switch=self.kill_switch)
        self.knowledge = knowledge or StrategyKnowledgeService()
        self.feature_engine = StrategyFeatureEngine()
        self.planner = TradePlanner(self.risk_engine.config.risk)
        self.circuit_breakers = CircuitBreakerService(self.kill_switch)
        self.order_flow = UnavailableOrderFlowProvider()

    def build_feature_bundle(
        self,
        *,
        strategy_id: str = "multi_model_po3_vwap",
        candles_5m: list[Candle],
        stale: bool = False,
        as_of: datetime | None = None,
    ) -> dict[str, Any]:
        record = self.knowledge.get_strategy(strategy_id)
        c15 = synthesize_timeframe(candles_5m, "15m")
        c240 = synthesize_timeframe(candles_5m, "240m")
        cvd = self.order_flow.fetch("BTC/USD")
        return self.feature_engine.compute(
            strategy=record.config,
            candles_5m=candles_5m,
            candles_15m=c15,
            candles_240m=c240,
            as_of=as_of,
            stale=stale,
            cvd_status=cvd.status,
        )

    def evaluate_proposal(
        self,
        *,
        symbol: str,
        analysis_result: dict[str, Any],
        candles_5m: list[Candle],
        stale: bool = False,
        liquidity_usd: float | None = 1_000_000.0,
        bars_since_last_trade: int | None = 100,
        strategy_id: str = "multi_model_po3_vwap",
    ) -> dict[str, Any]:
        record = self.knowledge.get_strategy(strategy_id)
        knowledge = self.knowledge.knowledge_bundle(strategy_id)
        features = self.build_feature_bundle(
            strategy_id=strategy_id,
            candles_5m=candles_5m,
            stale=stale,
        )
        consensus = analysis_result.get("consensus") or {}
        snap = self.portfolio.snapshot()
        from crypto_trading_mcp.risk.config import merge_effective_limits

        limits = merge_effective_limits(self.risk_engine.config.risk, record.config)
        risk_snap = PortfolioRiskSnapshot(
            equity=snap.equity,
            available_cash=snap.available_cash,
            positions_exposure=snap.positions_exposure,
            daily_pnl=snap.daily_pnl,
            drawdown_pct=snap.drawdown_pct,
            trades_today=snap.trades_today,
            kill_switch_active=self.kill_switch.active,
            trading_halted=self.circuit_breakers.halted,
            halt_reasons=self.circuit_breakers.reasons(),
        )
        self.circuit_breakers.evaluate_portfolio(risk_snap, limits)
        risk_snap.trading_halted = self.circuit_breakers.halted
        risk_snap.halt_reasons = self.circuit_breakers.reasons()

        plan = self.planner.plan(
            strategy_record=record,
            consensus=consensus,
            feature_bundle=features,
            equity=snap.equity,
        )
        plan.symbol = symbol.upper().replace("-", "/")

        model_rows = {
            m["model_id"]: m["status"] for m in features.get("models", [])
        }

        if plan.status == "NO_TRADE" or self.circuit_breakers.halted or stale:
            decision = {
                "approved": False,
                "reason_codes": (
                    ["TRADING_HALTED"]
                    if self.circuit_breakers.halted
                    else ["STALE_MARKET_DATA"]
                    if stale
                    else [plan.reason or "NO_TRADE"]
                ),
                "warnings": [],
                "max_allowed_quantity": 0.0,
                "max_allowed_notional": 0.0,
            }
            return {
                "strategy": knowledge,
                "models": model_rows,
                "confluence": features.get("confluence", {}),
                "consensus": consensus,
                "trade_plan": plan.to_dict(),
                "risk": decision,
                "portfolio": snap.to_dict(),
                "execution_attempted": False,
                "live_trading_enabled": False,
                "features_status": features.get("status"),
            }

        proposal = plan.to_proposal(
            current_price=plan.entry_price,
            liquidity_usd=liquidity_usd,
            market_data_stale=stale,
            bars_since_last_trade=bars_since_last_trade,
        )
        risk = self.risk_engine.evaluate(proposal, risk_snap, record.config)
        return {
            "strategy": {
                "strategy_id": record.strategy_id,
                "name": record.name,
                "version": record.version,
                "config_hash": record.config_hash,
            },
            "models": model_rows,
            "confluence": features.get("confluence", {}),
            "consensus": consensus,
            "trade_plan": plan.to_dict(),
            "risk": risk.to_dict(),
            "portfolio": snap.to_dict(),
            "execution_attempted": False,
            "live_trading_enabled": False,
            "features_status": features.get("status"),
            "approved": risk.approved,
        }


def default_mock_candles(n: int = 400) -> list[Candle]:
    """Generate enough 5m bars for HTF aggregation in tests."""
    now = datetime.now(UTC)
    # Align to closed 5m boundary in the past.
    base = now.replace(second=0, microsecond=0) - timedelta(minutes=5)
    candles: list[Candle] = []
    price = 100.0
    for i in range(n):
        ts = base - timedelta(minutes=5 * (n - i))
        open_ = price
        close = price + 0.15
        candles.append(
            Candle(
                timestamp=ts,
                open=open_,
                high=close + 0.05,
                low=open_ - 0.05,
                close=close,
                volume=1000 + (i % 20) * 10,
            )
        )
        price = close
    return candles
