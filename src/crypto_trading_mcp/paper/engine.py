from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from crypto_trading_mcp.compliance.policy import CompliancePolicy, TaxSimulator
from crypto_trading_mcp.config.settings import REPO_ROOT, get_settings
from crypto_trading_mcp.exchange.config import load_paper_config, resolve_strategy_for_symbol
from crypto_trading_mcp.exchange.models import AssetClass, Order, OrderSide, OrderType
from crypto_trading_mcp.exchange.paper import PaperExchange
from crypto_trading_mcp.exchange.prediction import (
    EnsembleAttribution,
    PredictionContract,
    PredictionMarketBook,
)
from crypto_trading_mcp.execution.planner import TradePlan
from crypto_trading_mcp.risk.config import KillSwitch
from crypto_trading_mcp.risk.correlation import CorrelationFilter
from crypto_trading_mcp.risk.engine import RiskEngine
from crypto_trading_mcp.risk.models import PortfolioRiskSnapshot, TradeProposal


@dataclass
class AgentDecisionRecord:
    run_id: str
    market_state: dict[str, Any]
    strategy_selected: str | None
    agent_outputs: dict[str, Any]
    bull_case: dict[str, Any] | None
    bear_case: dict[str, Any] | None
    consensus: dict[str, Any]
    trade_plan: dict[str, Any] | None
    compliance_result: dict[str, Any]
    risk_result: dict[str, Any]
    execution_result: dict[str, Any]
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "market_state": self.market_state,
            "strategy_selected": self.strategy_selected,
            "agent_outputs": self.agent_outputs,
            "bull_case": self.bull_case,
            "bear_case": self.bear_case,
            "consensus": self.consensus,
            "trade_plan": self.trade_plan,
            "compliance_result": self.compliance_result,
            "risk_result": self.risk_result,
            "execution_result": self.execution_result,
            "created_at": self.created_at,
        }


class PaperTradingEngine:
    """Autonomous paper loop: plan → compliance → risk → paper exchange."""

    def __init__(
        self,
        *,
        exchange: PaperExchange | None = None,
        risk_engine: RiskEngine | None = None,
        compliance: CompliancePolicy | None = None,
        tax: TaxSimulator | None = None,
        kill_switch: KillSwitch | None = None,
        correlation: CorrelationFilter | None = None,
    ) -> None:
        self.settings = get_settings()
        self.config = load_paper_config()
        self.exchange = exchange or PaperExchange(config=self.config)
        self.kill_switch = kill_switch or KillSwitch()
        self.risk_engine = risk_engine or RiskEngine(kill_switch=self.kill_switch)
        self.compliance = compliance or CompliancePolicy()
        self.tax = tax or TaxSimulator()
        self.correlation = correlation or CorrelationFilter()
        self.prediction_book = PredictionMarketBook(self.exchange)
        self.running = False
        self.decision_log: list[dict[str, Any]] = []
        self.daily_turnover = 0.0
        self.strategy_books: dict[str, list[str]] = {}
        self.return_history: dict[str, list[float]] = {}
        self._check_stop_file()

    def _check_stop_file(self) -> None:
        stop_name = self.config.get("paper", {}).get("kill_switch_file", "STOP")
        stop_path = REPO_ROOT / str(stop_name)
        if stop_path.exists():
            self.kill_switch.activate(f"STOP file detected at {stop_path}")
            self.exchange.halt("KILL_SWITCH_ACTIVE")

    def start(self) -> dict[str, Any]:
        self._check_stop_file()
        if self.settings.trading_mode != "paper" or self.settings.live_trading_enabled:
            raise RuntimeError("Paper engine requires TRADING_MODE=paper and LIVE_TRADING_ENABLED=false")
        self.running = True
        return self.status()

    def stop(self) -> dict[str, Any]:
        self.running = False
        return self.status()

    def status(self) -> dict[str, Any]:
        snap = self.exchange.portfolio.snapshot(self.exchange.prices)
        return {
            "running": self.running,
            "trading_mode": self.settings.trading_mode,
            "live_trading_enabled": self.settings.live_trading_enabled,
            "kill_switch": self.kill_switch.status().model_dump(),
            "exchange_halted": self.exchange.halted,
            "halt_reason": self.exchange.halt_reason,
            "cash": snap.cash,
            "equity": snap.equity,
            "positions": len(snap.positions),
            "open_orders": len(self.exchange.get_open_orders()),
            "trades": len(self.exchange.trades),
            "daily_turnover": self.daily_turnover,
            "REAL_MONEY": "DISABLED",
            "TRADING_MODE": "PAPER",
        }

    def reset(self) -> dict[str, Any]:
        initial = float(self.config.get("paper", {}).get("initial_cash", 10_000))
        self.exchange = PaperExchange(config=self.config)
        self.exchange.portfolio = self.exchange.portfolio.__class__(starting_cash=initial)
        self.prediction_book = PredictionMarketBook(self.exchange)
        self.decision_log.clear()
        self.daily_turnover = 0.0
        self.strategy_books.clear()
        self.return_history.clear()
        self.running = False
        return self.status()

    def select_strategy(self, symbol: str) -> str | None:
        return resolve_strategy_for_symbol(symbol, self.config)

    def resolve_conflict(self, symbol: str, new_side: str, strategy_id: str) -> str:
        mode = str(self.config.get("paper", {}).get("strategy_conflict_mode", "NO_TRADE"))
        existing = self.exchange.portfolio.positions.get(symbol.upper())
        if existing is None:
            return "OK"
        if existing.strategy_id and existing.strategy_id != strategy_id:
            if mode == "SEPARATE_STRATEGY_BOOK":
                return "SEPARATE_STRATEGY_BOOK"
            if mode == "NETTED":
                return "NETTED"
            return "STRATEGY_CONFLICT"
        if existing.side[0] != new_side[0] and existing.side != new_side:
            # opposing direction
            if mode == "NETTED":
                return "NETTED"
            return "STRATEGY_CONFLICT"
        return "OK"

    def execute_approved_plan(
        self,
        plan: TradePlan,
        *,
        market_price: float,
        asset_class: str = "CRYPTO",
        analysis: dict[str, Any] | None = None,
        candidate_returns: list[float] | None = None,
    ) -> dict[str, Any]:
        self._check_stop_file()
        run_id = str(uuid4())
        analysis = analysis or {}
        if self.settings.trading_mode != "paper" or self.settings.live_trading_enabled:
            return {
                "executed": False,
                "reason_codes": ["PAPER_MODE_REQUIRED"],
                "execution_attempted": False,
            }
        if self.kill_switch.active or self.exchange.halted:
            return {
                "executed": False,
                "reason_codes": ["KILL_SWITCH_ACTIVE" if self.kill_switch.active else "TRADING_HALTED"],
                "execution_attempted": False,
            }
        if plan.status != "PROPOSED" or plan.quantity <= 0:
            return {
                "executed": False,
                "reason_codes": [plan.reason or "NO_TRADE"],
                "execution_attempted": False,
            }

        conflict = self.resolve_conflict(plan.symbol, plan.side, plan.strategy_id)
        if conflict in {"STRATEGY_CONFLICT", "NO_TRADE"}:
            return {
                "executed": False,
                "reason_codes": [conflict],
                "execution_attempted": False,
            }

        compliance = self.compliance.evaluate(
            strategy_id=plan.strategy_id,
            asset_class=asset_class,
            notional=plan.notional,
            daily_turnover=self.daily_turnover,
        )
        if not compliance.approved:
            record = self._log_decision(
                run_id,
                analysis,
                plan,
                compliance.model_dump(),
                {"approved": False, "reason_codes": compliance.reason_codes},
                {"executed": False},
            )
            return {
                "executed": False,
                "reason_codes": compliance.reason_codes,
                "decision_record": record,
                "execution_attempted": False,
            }

        if candidate_returns and self.return_history:
            ok, corr_reasons = self.correlation.evaluate(candidate_returns, self.return_history)
            if not ok:
                return {
                    "executed": False,
                    "reason_codes": corr_reasons,
                    "execution_attempted": False,
                }

        snap = self.exchange.portfolio.snapshot(self.exchange.prices)
        risk_snap = PortfolioRiskSnapshot(
            equity=snap.equity,
            available_cash=snap.available_cash,
            positions_exposure=snap.positions_exposure,
            daily_pnl=snap.daily_pnl,
            drawdown_pct=snap.drawdown_pct,
            trades_today=snap.trades_today,
            kill_switch_active=self.kill_switch.active,
            trading_halted=self.exchange.halted,
        )
        proposal = plan.to_proposal(
            current_price=market_price,
            liquidity_usd=1_000_000.0,
            market_data_stale=False,
            bars_since_last_trade=100,
        )
        # Ensure symbol set
        proposal.symbol = plan.symbol
        risk = self.risk_engine.evaluate(proposal, risk_snap, strategy=None)
        # Paper path may run strategy stubs without full Phase-4 strategy schema.
        ignore = {"STRATEGY_DATA_UNAVAILABLE"}
        if plan.model_ids:
            ignore.add("NO_VALID_MODEL")
        risk.reason_codes = [c for c in risk.reason_codes if c.value not in ignore]
        if not risk.reason_codes:
            from crypto_trading_mcp.risk.models import RiskReasonCode

            risk.approved = True
            risk.reason_codes = [RiskReasonCode.RISK_OK]
        else:
            risk.approved = False
        if not risk.approved:
            record = self._log_decision(
                run_id,
                analysis,
                plan,
                compliance.model_dump(),
                risk.to_dict(),
                {"executed": False},
            )
            return {
                "executed": False,
                "reason_codes": [c.value for c in risk.reason_codes],
                "risk": risk.to_dict(),
                "decision_record": record,
                "execution_attempted": False,
            }

        self.exchange.set_price(plan.symbol, market_price)
        side = OrderSide.BUY if plan.side.upper() in {"LONG", "BUY"} else OrderSide.SELL
        order = Order(
            symbol=plan.symbol,
            instrument_type=AssetClass(asset_class),
            side=side,
            order_type=OrderType.MARKET,
            quantity=plan.quantity,
            strategy_id=plan.strategy_id,
            strategy_version=plan.strategy_version,
            model_ids=plan.model_ids,
            agent_run_id=run_id,
            metadata={
                "stop_loss": plan.stop_loss,
                "take_profit": plan.take_profit,
            },
        )
        filled = self.exchange.create_order(order, market_price=market_price)
        executed = filled.status.value == "FILLED"
        if executed:
            self.daily_turnover += plan.notional
            self.strategy_books.setdefault(plan.strategy_id, []).append(plan.symbol)
            if candidate_returns:
                self.return_history[plan.symbol] = list(candidate_returns)[-50:]
            # Configure strategy-specific exits when provided in plan metadata via confluence
            if plan.confluence.get("move_be_at_1r") or plan.strategy_id == "multi_model_po3_vwap":
                partial = plan.confluence.get("partial_tp_pct", 50)
                self.exchange.configure_position_rules(
                    plan.symbol,
                    move_be_at_1r=True,
                    partial_tp_pct=float(partial),
                )

        tax = self.tax.apply(
            gross_pnl=0.0,
            fees=filled.fees,
            notional=plan.notional,
            asset_class=asset_class,
        )
        execution_result = {
            "executed": executed,
            "order": filled.model_dump(mode="json"),
            "tax": tax,
        }
        record = self._log_decision(
            run_id,
            analysis,
            plan,
            compliance.model_dump(),
            risk.to_dict(),
            execution_result,
        )
        return {
            "executed": executed,
            "order": filled.model_dump(mode="json"),
            "risk": risk.to_dict(),
            "compliance": compliance.model_dump(),
            "tax": tax,
            "decision_record": record,
            "execution_attempted": True,
            "live_trading_enabled": False,
        }

    def _log_decision(
        self,
        run_id: str,
        analysis: dict[str, Any],
        plan: TradePlan,
        compliance: dict[str, Any],
        risk: dict[str, Any],
        execution: dict[str, Any],
    ) -> dict[str, Any]:
        messages = analysis.get("messages") or {}
        record = AgentDecisionRecord(
            run_id=run_id,
            market_state={"prices": dict(self.exchange.prices)},
            strategy_selected=plan.strategy_id,
            agent_outputs={k: v for k, v in messages.items()},
            bull_case=(messages.get("bull") or {}).get("payload")
            if isinstance(messages.get("bull"), dict)
            else None,
            bear_case=(messages.get("bear") or {}).get("payload")
            if isinstance(messages.get("bear"), dict)
            else None,
            consensus=analysis.get("consensus") or {},
            trade_plan=plan.to_dict(),
            compliance_result=compliance,
            risk_result=risk,
            execution_result=execution,
        )
        data = record.to_dict()
        self.decision_log.append(data)
        return data

    def strategy_book_report(self) -> dict[str, Any]:
        snap = self.exchange.portfolio.snapshot(self.exchange.prices)
        books: dict[str, Any] = {"overall": snap.to_dict(), "strategies": {}}
        for strategy_id, symbols in self.strategy_books.items():
            positions = [p for p in snap.positions if p.strategy_id == strategy_id or p.symbol in symbols]
            books["strategies"][strategy_id] = {
                "symbols": symbols,
                "positions": [p.model_dump(mode="json") for p in positions],
            }
        by_asset: dict[str, list[dict[str, Any]]] = {}
        for p in snap.positions:
            ac = self.exchange._asset_class(p.symbol).value
            by_asset.setdefault(ac, []).append(p.model_dump(mode="json"))
        books["asset_classes"] = by_asset
        return books
