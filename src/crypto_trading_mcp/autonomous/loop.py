from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from crypto_trading_mcp.autonomous.idempotency import already_seen, make_idempotency_key
from crypto_trading_mcp.autonomous.states import CycleState, CycleStateMachine
from crypto_trading_mcp.config.settings import REPO_ROOT, get_settings
from crypto_trading_mcp.dashboard.event_bus import get_event_bus
from crypto_trading_mcp.dashboard.events import EventType
from crypto_trading_mcp.execution.planner import TradePlan
from crypto_trading_mcp.learning.engine import get_learning_engine
from crypto_trading_mcp.learning.models import TradeLearningRecord, TradeOutcome
from crypto_trading_mcp.market.data import MockMarketData
from crypto_trading_mcp.market.gateway import MarketDataGateway
from crypto_trading_mcp.paper.engine import PaperTradingEngine


def load_autonomous_config(path: Path | None = None) -> dict[str, Any]:
    path = path or (REPO_ROOT / "config" / "autonomous_loop.yaml")
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data.get("autonomous_loop") or {}


class AutonomousPaperLoop:
    """Continuous PAPER-only trading loop. Never enables live execution."""

    def __init__(
        self,
        *,
        config: dict[str, Any] | None = None,
        paper: PaperTradingEngine | None = None,
        market: MarketDataGateway | None = None,
        event_bus: Any | None = None,
    ) -> None:
        self.config = config if config is not None else load_autonomous_config()
        self.settings = get_settings()
        self.paper = paper or PaperTradingEngine()
        self.market = market or MarketDataGateway(MockMarketData())
        self.bus = event_bus or get_event_bus()
        self.learning = get_learning_engine()
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.running = False
        self.cycles_completed = 0
        self.last_cycle: dict[str, Any] | None = None
        self.seen_idempotency: set[str] = set()
        self.state_path = REPO_ROOT / str(
            self.config.get("state_path", ".runtime/autonomous_cycle_state.json")
        )
        self._load_state()

    def _assert_paper_only(self) -> None:
        if self.settings.trading_mode != "paper" or self.settings.live_trading_enabled:
            raise RuntimeError(
                "AutonomousPaperLoop requires TRADING_MODE=paper and LIVE_TRADING_ENABLED=false"
            )
        if bool(self.config.get("live_trading_enabled", False)):
            raise RuntimeError("autonomous_loop.live_trading_enabled must remain false")

    def _emit(self, event_type: EventType | str, payload: dict[str, Any], **kwargs: Any) -> None:
        try:
            self.bus.emit(event_type, payload=payload, **kwargs)
        except Exception:
            return

    def _load_state(self) -> None:
        if not self.state_path.exists():
            return
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            self.cycles_completed = int(data.get("cycles_completed") or 0)
            self.seen_idempotency = set(data.get("seen_idempotency") or [])
            self.last_cycle = data.get("last_cycle")
        except Exception:
            return

    def _persist_state(self) -> None:
        if not self.config.get("persist_state", True):
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "cycles_completed": self.cycles_completed,
            "seen_idempotency": sorted(self.seen_idempotency)[-500:],
            "last_cycle": self.last_cycle,
            "updated_at": datetime.now(UTC).isoformat(),
            "TRADING_MODE": "paper",
            "LIVE_TRADING_ENABLED": False,
        }
        self.state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def status(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "cycles_completed": self.cycles_completed,
            "last_cycle": self.last_cycle,
            "interval_seconds": self.config.get("interval_seconds", 30),
            "symbols": self.config.get("symbols") or ["BTC/USD"],
            "TRADING_MODE": "paper",
            "LIVE_TRADING_ENABLED": False,
            "Live Execution": "DISABLED",
        }

    def start(self, *, background: bool = True, max_cycles: int | None = None) -> dict[str, Any]:
        self._assert_paper_only()
        with self._lock:
            if self.running:
                return {"started": False, "reason": "already_running", **self.status()}
            self._stop.clear()
            self.running = True
            self.paper.start()
            limit = self.config.get("max_cycles", 0) if max_cycles is None else max_cycles

            def _run() -> None:
                try:
                    completed = 0
                    while not self._stop.is_set():
                        self.run_once()
                        completed += 1
                        if limit and completed >= int(limit):
                            break
                        interval = float(self.config.get("interval_seconds", 30))
                        if self._stop.wait(interval):
                            break
                finally:
                    self.running = False
                    self._persist_state()

            if background:
                self._thread = threading.Thread(target=_run, name="autonomous-paper-loop", daemon=True)
                self._thread.start()
            else:
                _run()
            return {"started": True, **self.status()}

    def stop(self) -> dict[str, Any]:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self.running = False
        self._persist_state()
        return {"stopped": True, **self.status()}

    def run_once(self, *, symbol: str | None = None, price: float | None = None) -> dict[str, Any]:
        self._assert_paper_only()
        sm = CycleStateMachine()
        cycle_id = f"CYC-{uuid4().hex[:10]}"
        symbol = (symbol or (self.config.get("symbols") or ["BTC/USD"])[0]).upper()
        timeframe = str(self.config.get("timeframe", "1h"))
        strategy_id = str(self.config.get("strategy_id", "momentum_breakout_crypto"))
        started = datetime.now(UTC)
        result: dict[str, Any] = {
            "cycle_id": cycle_id,
            "symbol": symbol,
            "state": sm.state.value,
            "TRADING_MODE": "paper",
            "LIVE_TRADING_ENABLED": False,
        }
        self._emit(EventType.AGENT_STARTED, {"cycle_id": cycle_id}, symbol=symbol, run_id=cycle_id)
        try:
            sm.transition(CycleState.MARKET_DATA_READY)
            snapshot = self.market.get_snapshot(symbol, timeframe=timeframe)
            if not self.market.allows_new_trade(snapshot):
                sm.transition(CycleState.CYCLE_COMPLETED)
                result.update(
                    {
                        "state": sm.state.value,
                        "executed": False,
                        "reason": "STALE_OR_UNAVAILABLE_MARKET_DATA",
                        "snapshot": snapshot.to_dict(),
                    }
                )
                self.last_cycle = result
                self.cycles_completed += 1
                self._persist_state()
                return result

            sm.transition(CycleState.ANALYSIS_RUNNING)
            # Deterministic paper path: reuse paper engine risk+execution.
            last = snapshot.ticker.last if snapshot.ticker else (price or 100.0)
            if price is not None:
                last = price
            sm.transition(CycleState.CONSENSUS_READY)
            sm.transition(CycleState.TRADE_PROPOSED)
            signal_version = "1"
            idem = make_idempotency_key(
                strategy_id=strategy_id,
                symbol=symbol,
                timeframe=timeframe,
                cycle_id=cycle_id if not self.config.get("duplicate_cycle_protection", True) else f"{strategy_id}:{symbol}:{timeframe}:{started.strftime('%Y%m%d%H%M')}",
                signal_version=signal_version,
                side="LONG",
            )
            # For duplicate protection within same minute bucket, use stable cycle key.
            if self.config.get("duplicate_cycle_protection", True):
                # Recompute with minute-bucket cycle identity for repeats
                bucket = started.strftime("%Y%m%d%H%M")
                idem = make_idempotency_key(
                    strategy_id=strategy_id,
                    symbol=symbol,
                    timeframe=timeframe,
                    cycle_id=bucket,
                    signal_version=signal_version,
                    side="LONG",
                )
            if already_seen(self.seen_idempotency, idem):
                sm.transition(CycleState.CYCLE_COMPLETED)
                result.update(
                    {
                        "state": sm.state.value,
                        "executed": False,
                        "reason": "DUPLICATE_CYCLE_IDEMPOTENCY",
                        "idempotency_key": idem,
                    }
                )
                self.last_cycle = result
                self.cycles_completed += 1
                self._persist_state()
                return result

            plan = TradePlan(
                strategy_id=strategy_id,
                strategy_version="1.0.0",
                model_ids=["PHASE9"],
                symbol=symbol,
                side="LONG",
                entry_price=float(last),
                quantity=1.0 if float(last) < 1000 else 0.01,
                notional=(1.0 if float(last) < 1000 else 0.01) * float(last),
                stop_loss=float(last) * 0.97,
                take_profit=float(last) * 1.06,
                risk_amount=abs(float(last) * 0.03) * (1.0 if float(last) < 1000 else 0.01),
                risk_reward_ratio=2.0,
                confidence=0.66,
                status="PROPOSED",
                confluence={"idempotency_key": idem, "cycle_id": cycle_id},
            )
            sm.transition(CycleState.RISK_VALIDATING)
            self.paper.start()
            exec_out = self.paper.execute_approved_plan(
                plan,
                market_price=float(last),
                asset_class="CRYPTO",
                analysis={"consensus": {"decision": "LONG", "confidence": 0.66}},
            )
            if exec_out.get("executed"):
                sm.transition(CycleState.RISK_APPROVED)
                sm.transition(CycleState.ORDER_SUBMITTED)
                sm.transition(CycleState.ORDER_FILLED)
                sm.transition(CycleState.POSITION_UPDATED)
                self.seen_idempotency.add(idem)
                # Close + learn (paper demo-style)
                exit_price = float(last) * 1.01
                record = TradeLearningRecord(
                    trade_id=f"{cycle_id}-T1",
                    strategy_id=strategy_id,
                    symbol=symbol,
                    timeframe=timeframe,
                    entry_price=float(last),
                    exit_price=exit_price,
                    quantity=plan.quantity,
                    net_pnl=(exit_price - float(last)) * plan.quantity,
                    predicted_probability=0.66,
                    outcome=TradeOutcome.WIN,
                    execution_quality="GOOD",
                )
                learn = self.learning.on_trade_close(record)
                sm.transition(CycleState.CYCLE_COMPLETED)
                result.update(
                    {
                        "state": sm.state.value,
                        "executed": True,
                        "idempotency_key": idem,
                        "execution": exec_out,
                        "learning": {
                            "trades_processed": self.learning.trades_processed,
                            "post_mortem": (learn or {}).get("post_mortem"),
                        },
                    }
                )
            else:
                sm.transition(CycleState.RISK_REJECTED)
                sm.transition(CycleState.CYCLE_COMPLETED)
                result.update(
                    {
                        "state": sm.state.value,
                        "executed": False,
                        "reason": "RISK_REJECTED",
                        "execution": exec_out,
                        "idempotency_key": idem,
                    }
                )
            self.last_cycle = result
            self.cycles_completed += 1
            self._persist_state()
            self._emit(
                EventType.AGENT_COMPLETED,
                {"cycle": result},
                symbol=symbol,
                run_id=cycle_id,
            )
            return result
        except Exception as exc:  # noqa: BLE001
            try:
                if sm.state not in {CycleState.CYCLE_FAILED, CycleState.CYCLE_COMPLETED}:
                    # best-effort fail transition
                    sm.state = CycleState.CYCLE_FAILED
            except Exception:
                pass
            result.update({"state": CycleState.CYCLE_FAILED.value, "executed": False, "error": str(exc)})
            self.last_cycle = result
            self.cycles_completed += 1
            self._persist_state()
            return result


_LOOP: AutonomousPaperLoop | None = None


def get_autonomous_loop(reset: bool = False) -> AutonomousPaperLoop:
    global _LOOP
    if reset or _LOOP is None:
        _LOOP = AutonomousPaperLoop()
    return _LOOP
