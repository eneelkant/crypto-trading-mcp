from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from crypto_trading_mcp.backtest.config import BacktestConfig, load_backtest_config
from crypto_trading_mcp.backtest.data import HistoricalDataProvider
from crypto_trading_mcp.backtest.metrics import compute_backtest_metrics, compute_risk_metrics
from crypto_trading_mcp.backtest.models import (
    BacktestIdentity,
    BacktestResult,
    DataPartition,
    EquityPoint,
    NormalizedCandle,
    stable_hash,
)
from crypto_trading_mcp.backtest.replay import LookaheadGuard
from crypto_trading_mcp.backtest.signals import StrategySignal, signal_for_strategy
from crypto_trading_mcp.backtest.validation import detect_overfitting_warnings
from crypto_trading_mcp.config.settings import get_settings
from crypto_trading_mcp.exchange.exceptions import LiveExecutionBlocked
from crypto_trading_mcp.exchange.factory import create_exchange
from crypto_trading_mcp.exchange.paper import PaperExchange
from crypto_trading_mcp.execution.planner import TradePlan
from crypto_trading_mcp.paper.engine import PaperTradingEngine
from crypto_trading_mcp.portfolio.manager import PortfolioManager
from crypto_trading_mcp.strategy.repository import StrategyKnowledgeService


class BacktestEngine:
    """Historical backtest reusing Phase 5 PaperExchange + RiskEngine."""

    def __init__(
        self,
        *,
        config: BacktestConfig | None = None,
        knowledge: StrategyKnowledgeService | None = None,
    ) -> None:
        self.config = config or load_backtest_config()
        self.knowledge = knowledge or StrategyKnowledgeService()
        self.settings = get_settings()

    def _assert_safe(self) -> None:
        if self.settings.trading_mode != "paper" or self.settings.live_trading_enabled:
            raise LiveExecutionBlocked(
                "Backtests require TRADING_MODE=paper and LIVE_TRADING_ENABLED=false"
            )
        if self.config.execution_model != "paper_exchange":
            raise LiveExecutionBlocked(
                f"Unsupported execution_model={self.config.execution_model}; only paper_exchange allowed"
            )
        # Factory must never resolve live adapters.
        create_exchange("paper")

    def run(
        self,
        *,
        candles: list[NormalizedCandle],
        strategy_id: str,
        symbol: str | None = None,
        timeframe: str | None = None,
        partition: DataPartition = DataPartition.FULL,
        data_source: str = "mock",
        data_version: str | None = None,
        signal_params: dict[str, Any] | None = None,
        strategy_version: str | None = None,
    ) -> BacktestResult:
        self._assert_safe()
        if not candles:
            raise ValueError("No candles for backtest")

        symbol = (symbol or candles[0].symbol).upper()
        timeframe = timeframe or candles[0].timeframe
        try:
            record = self.knowledge.get_strategy(strategy_id, strategy_version)
        except KeyError:
            # Allow alias ids used in docs (e.g. MOMENTUM_BREAKOUT_CRYPTO)
            aliases = {
                "MOMENTUM_BREAKOUT_CRYPTO": "momentum_breakout_crypto",
                "MEAN_REVERSION_INDICES": "mean_reversion_equity",
                "TREND_FOLLOWING_COMMODITIES": "trend_following_commodities",
                "SMC_ORDER_BLOCK_CONFLUENCE": "multi_model_po3_vwap",
                "PO3_VWAP": "multi_model_po3_vwap",
                "PO3/VWAP": "multi_model_po3_vwap",
            }
            sid = aliases.get(strategy_id.upper(), strategy_id)
            record = self.knowledge.get_strategy(sid, strategy_version)

        data_version = data_version or stable_hash([c.to_dict() for c in candles])[:16]
        identity = BacktestIdentity(
            backtest_id=BacktestIdentity.compute_id(
                strategy_id=record.strategy_id,
                strategy_version=record.version,
                strategy_config_hash=record.config_hash,
                data_version=data_version,
                date_start=candles[0].timestamp.isoformat(),
                date_end=candles[-1].timestamp.isoformat(),
                backtest_config_hash=self.config.config_hash(),
                instrument=symbol,
                timeframe=timeframe,
            ),
            strategy_id=record.strategy_id,
            strategy_version=record.version,
            strategy_config_hash=record.config_hash,
            instrument=symbol,
            timeframe=timeframe,
            data_source=data_source,
            data_version=data_version,
            date_start=candles[0].timestamp.isoformat(),
            date_end=candles[-1].timestamp.isoformat(),
            backtest_config_hash=self.config.config_hash(),
            partition=partition,
        )

        paper_cfg = {
            "paper": {
                "initial_cash": self.config.initial_capital,
                "quote_currency": self.config.base_currency,
                "fees": {
                    "default_rate": 0.001 if self.config.include_fees and self.config.commission_enabled else 0.0
                },
                "slippage": {
                    "enabled": self.config.include_slippage and self.config.slippage_enabled,
                    "model": "fixed_bps",
                    "default_bps": 5 if self.config.include_slippage else 0,
                    "max_bps": 50,
                },
                "max_consecutive_api_failures": 3,
                "kill_switch_file": "STOP",
                "flatten_at_eod": False,
            }
        }
        portfolio = PortfolioManager(starting_cash=self.config.initial_capital)
        exchange = PaperExchange(
            portfolio=portfolio,
            config=paper_cfg,
            session_id=identity.backtest_id,
        )
        engine = PaperTradingEngine(exchange=exchange)
        engine.session.session_id = identity.backtest_id
        engine.session.config_hash = record.config_hash
        engine.session.starting_capital = self.config.initial_capital

        guard = LookaheadGuard(candles, enabled=self.config.prevent_lookahead)
        equity_curve: list[EquityPoint] = []
        exposures: list[float] = []
        risk_rejections = 0
        events: list[dict[str, Any]] = []
        trade_sides: list[str] = []

        warmup = 30
        for index, candle, hist in guard.iter_closed():
            # Closed-candle rule: decisions use hist including current closed bar.
            guard.assert_no_future_access(hist)
            events.append(
                {
                    "type": "MARKET_DATA_RECEIVED",
                    "timestamp": candle.timestamp.isoformat(),
                    "index": index,
                    "close": candle.close,
                }
            )
            # Manage open positions on OHLC path (high then low then close).
            exchange.on_price_update(symbol, candle.open)
            exchange.on_price_update(symbol, candle.high)
            exchange.on_price_update(symbol, candle.low)
            exchange.on_price_update(symbol, candle.close)

            if index < warmup:
                snap = exchange.portfolio.snapshot(exchange.prices)
                equity_curve.append(
                    EquityPoint(
                        timestamp=candle.timestamp.isoformat(),
                        equity=snap.equity,
                        cash=snap.cash,
                        drawdown=snap.drawdown_pct,
                        daily_pnl=snap.daily_pnl,
                    )
                )
                exposures.append(snap.positions_exposure)
                continue

            signal = signal_for_strategy(
                record.strategy_id, candles, index, params=signal_params
            )
            # Ensure signal only used hist <= T
            guard.assert_no_future_access(hist)

            if signal.side in {"LONG", "SHORT"} and symbol not in exchange.portfolio.positions:
                plan = self._plan_from_signal(
                    record.strategy_id,
                    record.version,
                    symbol,
                    signal,
                    model_ids=signal.model_ids or ["BACKTEST"],
                )
                result = engine.execute_approved_plan(
                    plan,
                    market_price=candle.close,
                    asset_class=self._asset_class(symbol),
                    analysis={
                        "consensus": {
                            "decision": signal.side,
                            "confidence": signal.confidence,
                        },
                        "messages": {},
                        "agent_mode": self.config.agent_mode,
                    },
                )
                if not result.get("executed"):
                    risk_rejections += 1
                    events.append(
                        {
                            "type": "RISK_VALIDATED",
                            "approved": False,
                            "reason_codes": result.get("reason_codes"),
                            "timestamp": candle.timestamp.isoformat(),
                        }
                    )
                else:
                    trade_sides.append(signal.side)
                    if signal.model_ids and "DONCHIAN" in "".join(signal.model_ids).upper():
                        exchange.configure_position_rules(
                            symbol,
                            trailing_atr=(candle.high - candle.low) or candle.close * 0.01,
                            trailing_mult=2.0,
                        )
                    events.append(
                        {
                            "type": "ORDER_FILLED",
                            "timestamp": candle.timestamp.isoformat(),
                            "side": signal.side,
                        }
                    )

            snap = exchange.portfolio.snapshot(exchange.prices)
            equity_curve.append(
                EquityPoint(
                    timestamp=candle.timestamp.isoformat(),
                    equity=snap.equity,
                    cash=snap.cash,
                    drawdown=snap.drawdown_pct,
                    daily_pnl=snap.daily_pnl,
                )
            )
            exposures.append(snap.positions_exposure)

        # Attach sides onto trade records for metrics when missing
        trades = list(exchange.trades)
        for i, t in enumerate(trades):
            if "side" not in t and i < len(trade_sides):
                t["side"] = trade_sides[i]

        fees_total = float(exchange.portfolio.fees_paid)
        slip_total = sum(float(f.slippage) for f in exchange.fills)
        metrics = compute_backtest_metrics(
            trades=trades,
            equity_curve=equity_curve,
            initial_capital=self.config.initial_capital,
            fees_total=fees_total,
            slippage_total=slip_total,
        )
        risk_metrics = compute_risk_metrics(
            equity_curve=equity_curve,
            trades=trades,
            risk_rejections=risk_rejections,
            exposures=exposures,
        )
        warnings = detect_overfitting_warnings(metrics, risk_metrics, trades)
        structural = {
            "backtest_id": identity.backtest_id,
            "final_equity": round(equity_curve[-1].equity if equity_curve else self.config.initial_capital, 8),
            "trade_count": len(trades),
            "fill_count": len(exchange.fills),
            "fees": round(fees_total, 8),
            "risk_rejections": risk_rejections,
            "net_pnl": round(float(metrics.get("net_pnl") or 0.0), 8),
        }
        return BacktestResult(
            identity=identity,
            initial_capital=self.config.initial_capital,
            final_equity=equity_curve[-1].equity if equity_curve else self.config.initial_capital,
            metrics=metrics,
            risk_metrics=risk_metrics,
            equity_curve=equity_curve,
            trades=trades,
            orders=[o.model_dump(mode="json") for o in exchange.orders.values()],
            fills=[f.model_dump(mode="json") for f in exchange.fills],
            events=events,
            warnings=warnings,
            risk_rejections=risk_rejections,
            structural_hash=stable_hash(structural),
        )

    def run_from_provider(
        self,
        provider: HistoricalDataProvider,
        *,
        symbol: str,
        strategy_id: str,
        timeframe: str = "1h",
        start: datetime | None = None,
        end: datetime | None = None,
        **kwargs: Any,
    ) -> BacktestResult:
        candles = provider.load(symbol, timeframe=timeframe, start=start, end=end)
        return self.run(
            candles=candles,
            strategy_id=strategy_id,
            symbol=symbol,
            timeframe=timeframe,
            data_source=provider.name,
            data_version=provider.data_version(candles),
            **kwargs,
        )

    def _plan_from_signal(
        self,
        strategy_id: str,
        strategy_version: str,
        symbol: str,
        signal: StrategySignal,
        *,
        model_ids: list[str],
    ) -> TradePlan:
        entry = signal.entry
        stop = signal.stop_loss or (entry * 0.98 if signal.side == "LONG" else entry * 1.02)
        tp = signal.take_profit or (entry * 1.06 if signal.side == "LONG" else entry * 0.94)
        risk_per_unit = abs(entry - stop)
        # Size from ~0.5% equity risk for stability across fixtures
        risk_budget = self.config.initial_capital * 0.005
        qty = (risk_budget / risk_per_unit) if risk_per_unit > 0 else 0.0
        qty = max(qty, 0.0)
        # Cap notional at 2% capital
        max_notional = self.config.initial_capital * 0.02
        if qty * entry > max_notional and entry > 0:
            qty = max_notional / entry
        rr = abs(tp - entry) / risk_per_unit if risk_per_unit > 0 else None
        return TradePlan(
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            model_ids=model_ids,
            symbol=symbol,
            side=signal.side,
            entry_price=entry,
            quantity=qty,
            notional=qty * entry,
            stop_loss=stop,
            take_profit=tp,
            risk_amount=risk_per_unit * qty,
            expected_fee=qty * entry * 0.001,
            expected_slippage=0.0005,
            risk_reward_ratio=rr,
            confidence=signal.confidence,
            status="PROPOSED" if qty > 0 else "NO_TRADE",
            reason=None if qty > 0 else "ZERO_SIZE",
            confluence={"backtest": True, "signal_reason": signal.reason},
        )

    @staticmethod
    def _asset_class(symbol: str) -> str:
        s = symbol.upper()
        if s in {"SPY", "QQQ"}:
            return "ETF"
        if s in {"GLD", "USO"}:
            return "COMMODITY"
        if s.startswith("PREDICT/"):
            return "PREDICTION_CONTRACT"
        return "CRYPTO"
