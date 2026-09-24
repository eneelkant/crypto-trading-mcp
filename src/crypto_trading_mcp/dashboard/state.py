from __future__ import annotations

import threading
import time
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from crypto_trading_mcp.agents.registry import build_default_registry
from crypto_trading_mcp.backtest.store import BacktestStore
from crypto_trading_mcp.config.settings import get_settings
from crypto_trading_mcp.dashboard.event_bus import EventBus, get_event_bus
from crypto_trading_mcp.paper.engine import PaperTradingEngine
from crypto_trading_mcp.performance.metrics import compute_performance
from crypto_trading_mcp.risk.config import load_risk_config
from crypto_trading_mcp.strategy.repository import StrategyKnowledgeService


class AgentRuntimeStatus(StrEnum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    WAITING = "WAITING"
    FAILED = "FAILED"
    DISABLED = "DISABLED"


# Canonical 16-agent command-center roster
AGENT_ROSTER: list[dict[str, str]] = [
    {"id": "market_intelligence", "name": "Market Intelligence", "role": "market"},
    {"id": "technical_analysis", "name": "Technical Analysis", "role": "market"},
    {"id": "trend", "name": "Trend", "role": "market"},
    {"id": "sentiment", "name": "Sentiment", "role": "market"},
    {"id": "on_chain", "name": "On-Chain Intelligence", "role": "market"},
    {"id": "macro_event", "name": "Macro/Event", "role": "market"},
    {"id": "strategy", "name": "Strategy", "role": "strategy"},
    {"id": "bull", "name": "Bull Analyst", "role": "debate"},
    {"id": "bear", "name": "Bear Analyst", "role": "debate"},
    {"id": "consensus", "name": "Debate/Consensus", "role": "debate"},
    {"id": "risk_manager", "name": "Risk Manager", "role": "risk"},
    {"id": "portfolio_manager", "name": "Portfolio Manager", "role": "portfolio"},
    {"id": "trade_planner", "name": "Trade Planner", "role": "execution"},
    {"id": "execution", "name": "Execution", "role": "execution"},
    {"id": "reflection", "name": "Reflection/Learning", "role": "learning"},
    {"id": "performance_judge", "name": "Performance/Judge", "role": "learning"},
]


class AgentView(BaseModel):
    agent_id: str
    name: str
    role: str
    status: AgentRuntimeStatus = AgentRuntimeStatus.IDLE
    provider: str = "mock"
    model: str = "mock-analyst"
    model_version: str = "1.0.0"
    current_task: str | None = None
    last_execution: str | None = None
    execution_duration_ms: float | None = None
    success_count: int = 0
    failure_count: int = 0
    last_decision: dict[str, Any] | None = None
    confidence: float | None = None
    last_error: str | None = None


class ComponentHealth(BaseModel):
    name: str
    status: str = "ONLINE"  # ONLINE | DEGRADED | OFFLINE
    last_heartbeat: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    last_error: str | None = None
    detail: str | None = None


class DashboardState:
    """Shared runtime snapshot for API/WebSocket. Not a second trading engine."""

    def __init__(
        self,
        *,
        paper: PaperTradingEngine | None = None,
        bus: EventBus | None = None,
        backtest_store: BacktestStore | None = None,
    ) -> None:
        self.settings = get_settings()
        self.bus = bus or get_event_bus()
        self.paper = paper or PaperTradingEngine()
        self.backtest_store = backtest_store or BacktestStore()
        self.knowledge = StrategyKnowledgeService()
        self.started_at = time.time()
        self._lock = threading.RLock()
        self.agents: dict[str, AgentView] = {}
        self._init_agents()
        self.mcp_activity: list[dict[str, Any]] = []
        self.llm_stats: dict[str, dict[str, Any]] = {
            "mock": {"provider": "mock", "model": "mock-analyst", "status": "ONLINE", "request_count": 0, "success_count": 0, "failure_count": 0, "latency_ms": 0},
            "ollama": {"provider": "ollama", "model": "local", "status": "OFFLINE", "request_count": 0, "success_count": 0, "failure_count": 0, "latency_ms": None},
            "openai": {"provider": "openai", "model": "gpt", "status": "OFFLINE", "request_count": 0, "success_count": 0, "failure_count": 0, "latency_ms": None},
            "anthropic": {"provider": "anthropic", "model": "claude", "status": "OFFLINE", "request_count": 0, "success_count": 0, "failure_count": 0, "latency_ms": None},
            "gemini": {"provider": "gemini", "model": "gemini", "status": "OFFLINE", "request_count": 0, "success_count": 0, "failure_count": 0, "latency_ms": None},
        }
        self.components = self._default_health()
        self.latest_backtests: list[dict[str, Any]] = []
        self.walk_forward: dict[str, Any] | None = None
        self.sensitivity: list[dict[str, Any]] = []
        self.monte_carlo: dict[str, Any] | None = None
        self.benchmarks: dict[str, Any] | None = None
        self.prediction_backtests: dict[str, Any] | None = None
        self.market_cache: dict[str, Any] = {}
        self.running = False

    def _init_agents(self) -> None:
        registry = build_default_registry()
        registered = {a.agent_id: a for a in registry.list()}
        settings = get_settings()
        for entry in AGENT_ROSTER:
            aid = entry["id"]
            provider = "mock"
            model = "mock-analyst"
            if aid in registered:
                cfg = settings.agent_model_config(getattr(registered[aid], "config_key", aid) or aid)
                provider = cfg.get("provider", provider)
                model = cfg.get("model", model)
            self.agents[aid] = AgentView(
                agent_id=aid,
                name=entry["name"],
                role=entry["role"],
                provider=provider,
                model=model,
            )

    def _default_health(self) -> dict[str, ComponentHealth]:
        names = [
            "Market Data",
            "LLM Provider",
            "Risk Engine",
            "Portfolio",
            "Paper Exchange",
            "Database",
            "Event Bus",
            "WebSocket",
            "MCP Server",
            "Backtest Engine",
        ]
        return {n: ComponentHealth(name=n, status="ONLINE") for n in names}

    def uptime_seconds(self) -> float:
        return max(0.0, time.time() - self.started_at)

    def set_agent_status(
        self,
        agent_id: str,
        status: AgentRuntimeStatus,
        *,
        task: str | None = None,
        decision: dict[str, Any] | None = None,
        confidence: float | None = None,
        error: str | None = None,
        duration_ms: float | None = None,
    ) -> None:
        with self._lock:
            agent = self.agents.get(agent_id)
            if agent is None:
                return
            agent.status = status
            if task is not None:
                agent.current_task = task
            if decision is not None:
                agent.last_decision = decision
            if confidence is not None:
                agent.confidence = confidence
            if error is not None:
                agent.last_error = error
            if duration_ms is not None:
                agent.execution_duration_ms = duration_ms
            agent.last_execution = datetime.now(UTC).isoformat()
            if status == AgentRuntimeStatus.COMPLETED:
                agent.success_count += 1
            if status == AgentRuntimeStatus.FAILED:
                agent.failure_count += 1

    def record_mcp(self, tool: str, *, status: str = "OK", duration_ms: float = 0.0, agent: str | None = None) -> None:
        row = {
            "timestamp": datetime.now(UTC).isoformat(),
            "tool": tool,
            "agent": agent,
            "duration_ms": duration_ms,
            "status": status,
            "result_type": "json",
        }
        with self._lock:
            self.mcp_activity.append(row)
            self.mcp_activity = self.mcp_activity[-500:]

    def system_status(self) -> dict[str, Any]:
        snap = self.paper.exchange.portfolio.snapshot(self.paper.exchange.prices)
        risk = load_risk_config()
        return {
            "system": "ONLINE" if self.running else "STANDBY",
            "trading_mode": self.settings.trading_mode,
            "live_trading_enabled": self.settings.live_trading_enabled,
            "TRADING_MODE": "PAPER" if self.settings.trading_mode == "paper" else self.settings.trading_mode.upper(),
            "REAL_MONEY": "DISABLED",
            "LIVE_TRADING_ENABLED": False,
            "exchange": "PAPER EXCHANGE",
            "market_data": self.components["Market Data"].status,
            "risk_engine": self.components["Risk Engine"].status,
            "llm": self.settings.llm_provider.upper(),
            "agents_ready": len(self.agents),
            "uptime_seconds": self.uptime_seconds(),
            "kill_switch": self.paper.kill_switch.status().model_dump(),
            "equity": snap.equity,
            "cash": snap.cash,
            "signal_mode": "DETERMINISTIC",
        }

    def portfolio_view(self) -> dict[str, Any]:
        snap = self.paper.exchange.portfolio.snapshot(self.paper.exchange.prices)
        trades = self.paper.exchange.trades
        perf = compute_performance(trades, starting_equity=float(self.paper.session.starting_capital))
        return {
            **snap.to_dict(),
            "fees": snap.fees,
            "slippage": sum(float(t.get("slippage") or 0) for t in trades),
            "turnover": perf.get("turnover"),
            "total_return": perf.get("return"),
            "TRADING_MODE": "PAPER",
            "REAL_MONEY": "DISABLED",
        }

    def risk_view(self) -> dict[str, Any]:
        cfg = load_risk_config()
        snap = self.paper.exchange.portfolio.snapshot(self.paper.exchange.prices)
        return {
            "current_drawdown": snap.drawdown_pct,
            "maximum_drawdown_limit": cfg.risk.max_drawdown_pct,
            "daily_pnl": snap.daily_pnl,
            "maximum_daily_loss": cfg.risk.max_daily_loss_pct,
            "portfolio_exposure": snap.positions_exposure,
            "risk_per_trade": cfg.risk.max_trade_pct,
            "kelly_fraction": getattr(cfg.risk, "kelly_fraction", 0.25),
            "open_positions": len(snap.positions),
            "circuit_breaker": self.paper.exchange.halted,
            "halt_reason": self.paper.exchange.halt_reason,
            "kill_switch": self.paper.kill_switch.status().model_dump(),
            "limits": cfg.risk.model_dump(),
            "writable_from_dashboard": False,
        }

    def agents_view(self) -> list[dict[str, Any]]:
        with self._lock:
            return [a.model_dump(mode="json") for a in self.agents.values()]

    def health_view(self) -> dict[str, Any]:
        with self._lock:
            comps = {k: v.model_dump(mode="json") for k, v in self.components.items()}
        return {
            "status": "ONLINE",
            "uptime_seconds": self.uptime_seconds(),
            "components": comps,
            "TRADING_MODE": "PAPER",
            "LIVE_TRADING_ENABLED": False,
        }


_STATE: DashboardState | None = None
_STATE_LOCK = threading.Lock()


def get_dashboard_state() -> DashboardState:
    global _STATE
    with _STATE_LOCK:
        if _STATE is None:
            _STATE = DashboardState()
        return _STATE


def set_dashboard_state(state: DashboardState) -> None:
    global _STATE
    with _STATE_LOCK:
        _STATE = state
