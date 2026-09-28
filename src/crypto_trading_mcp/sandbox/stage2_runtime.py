from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from crypto_trading_mcp.alerts import AlertManager, AlertSeverity
from crypto_trading_mcp.live.durable_kill_switch import DurableKillSwitch
from crypto_trading_mcp.live.stages import TradingStage, TradingStageManager
from crypto_trading_mcp.persistence.sqlite_store import SqliteDurableStore
from crypto_trading_mcp.sandbox.delta_sandbox import DeltaIndiaSandboxAdapter
from crypto_trading_mcp.sandbox.execution import SandboxExecutionService
from crypto_trading_mcp.sandbox.websocket import SandboxWebSocketClient


class Stage2CloudPaperRuntime:
    """Long-running Stage 2 cloud-paper runtime (paper + sandbox harness)."""

    def __init__(
        self,
        *,
        store: SqliteDurableStore | None = None,
        use_local_harness: bool = True,
    ) -> None:
        self.store = store or SqliteDurableStore()
        self.stage_manager = TradingStageManager(current=TradingStage.STAGE_2_CLOUD_PAPER)
        self.kill_switch = DurableKillSwitch(self.store, alert_sink=self._alert)
        self.alerts = AlertManager()
        self.adapter = DeltaIndiaSandboxAdapter(
            use_local_harness=use_local_harness,
            stage=TradingStage.STAGE_2_CLOUD_PAPER,
        )
        self.execution = SandboxExecutionService(
            adapter=self.adapter,
            store=self.store,
            kill_switch_active=False,
            stage=TradingStage.STAGE_2_CLOUD_PAPER,
        )
        self.ws = SandboxWebSocketClient(
            url="wss://cdn-ind.testnet.deltaex.org/ws",
            connect=lambda: None,
            enabled=True,
        )
        self.cycles: list[dict[str, Any]] = []
        self.started_at: str | None = None

    def _alert(self, alert_type: str, details: dict[str, Any]) -> None:
        self.alerts.emit(alert_type, severity=AlertSeverity.CRITICAL, details=details)

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "stage": self.stage_manager.current.value,
            "TRADING_MODE": "paper",
            "LIVE_TRADING_ENABLED": False,
            "Live Execution": "DISABLED",
            "kill_switch": self.kill_switch.status(),
            "db": self.store.health(),
        }

    def readiness(self) -> dict[str, Any]:
        auth = self.adapter.authenticate()
        exch = self.adapter.health_check()
        ks_ok = self.kill_switch.allows_new_trades() or True  # readable
        ready = bool(auth.get("authenticated")) and bool(exch.get("ok")) and self.store.health().get("ok")
        # kill switch active still "ready" as process, but trades blocked
        return {
            "ready": ready,
            "authenticated": auth.get("authenticated"),
            "exchange_ok": exch.get("ok"),
            "db_ok": self.store.health().get("ok"),
            "kill_switch_blocks_trades": self.kill_switch.active,
            "ks_readable": ks_ok is not None,
        }

    def liveness(self) -> dict[str, Any]:
        return {"alive": True, "started_at": self.started_at}

    def start(self) -> dict[str, Any]:
        self.started_at = datetime.now(UTC).isoformat()
        self.ws.connect()
        self.ws.on_message("hello", {"type": "hello"})
        self.store.put_json(
            "runtime",
            "stage2",
            {
                "started_at": self.started_at,
                "stage": TradingStage.STAGE_2_CLOUD_PAPER.value,
                "TRADING_MODE": "paper",
                "LIVE_TRADING_ENABLED": False,
            },
        )
        return {"started": True, "health": self.health()}

    def run_cycle(self) -> dict[str, Any]:
        cycle_id = f"S2-{uuid4().hex[:10]}"
        started = datetime.now(UTC).isoformat()
        # Critical dependency gates
        if not self.store.health().get("ok"):
            self.alerts.emit("database_failure", severity=AlertSeverity.CRITICAL, details={})
            return self._no_trade(cycle_id, "DATABASE_FAILURE", started)
        if not self.kill_switch.allows_new_trades():
            self.alerts.emit("kill_switch", severity=AlertSeverity.CRITICAL, details={})
            return self._no_trade(cycle_id, "KILL_SWITCH", started)
        if not self.ws.allows_new_trades() and self.ws.enabled:
            # REST fallback freshness via exchange health
            exch = self.adapter.health_check()
            if not exch.get("ok"):
                self.alerts.emit("market_data_stale", details={})
                return self._no_trade(cycle_id, "STALE_OR_EXCHANGE_UNAVAILABLE", started)

        self.execution.kill_switch_active = self.kill_switch.active
        result = self.execution.execute(cycle_id=cycle_id, symbol="BTCUSD", quantity=0.01)
        record = {
            "cycle_id": cycle_id,
            "started_at": started,
            "completed_at": datetime.now(UTC).isoformat(),
            "stage": TradingStage.STAGE_2_CLOUD_PAPER.value,
            "strategy_version": "1.0.0",
            "model_version": "mock-analyst",
            "risk_decision": {"approved": not result.get("blocked")},
            "order_intent": result.get("intent_id"),
            "execution_result": {
                "executed": result.get("executed"),
                "exchange_order_id": result.get("exchange_order_id"),
            },
            "reconciliation_result": result.get("reconciliation"),
            "failure_reason": result.get("reason"),
            "final_state": result.get("lifecycle", {}).get("state"),
            "TRADING_MODE": "paper",
            "LIVE_TRADING_ENABLED": False,
            # no chain-of-thought
        }
        self.cycles.append(record)
        self.store.put_json("cycles", cycle_id, record)
        return record

    def _no_trade(self, cycle_id: str, reason: str, started: str) -> dict[str, Any]:
        record = {
            "cycle_id": cycle_id,
            "started_at": started,
            "completed_at": datetime.now(UTC).isoformat(),
            "executed": False,
            "failure_reason": reason,
            "final_state": "BLOCKED",
            "TRADING_MODE": "paper",
            "LIVE_TRADING_ENABLED": False,
        }
        self.cycles.append(record)
        self.store.put_json("cycles", cycle_id, record)
        return record

    def recover(self) -> dict[str, Any]:
        """Crash recovery: load state → reconcile → resume safely."""
        self.kill_switch._load()
        if not self.kill_switch.allows_new_trades():
            return {"recovered": True, "allows_new_trades": False, "reason": "KILL_SWITCH"}
        recon = self.execution._reconcile()
        allows = recon.get("state") == "RECONCILED"
        if not allows:
            self.alerts.emit("reconciliation_failure", severity=AlertSeverity.CRITICAL, details=recon)
        return {
            "recovered": True,
            "allows_new_trades": allows,
            "reconciliation": recon,
            "stage": self.stage_manager.current.value,
        }

    def shutdown(self) -> dict[str, Any]:
        self.ws.connected = False
        return {"stopped": True, "cycles": len(self.cycles)}
