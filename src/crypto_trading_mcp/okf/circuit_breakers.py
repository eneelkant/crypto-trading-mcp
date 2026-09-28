"""OKF hard circuit breakers — subordinate to system KillSwitch / flatten policy."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Callable

from crypto_trading_mcp.risk.config import KillSwitch


@dataclass
class CircuitBreakerEvent:
    trigger: str
    reason_code: str
    timestamp: str
    details: dict[str, Any] = field(default_factory=dict)
    actions: list[str] = field(default_factory=list)


class OKFCircuitBreakers:
    """Enforce OKF max drawdown / daily loss / STOP file semantics.

    Hierarchy: system KillSwitch remains authoritative; this module activates it.
    LLMs cannot disable or bypass.
    """

    def __init__(
        self,
        *,
        kill_switch: KillSwitch | None = None,
        max_drawdown_pct: float = 0.10,
        max_daily_loss_pct: float = 0.05,
        kill_switch_file: str = "STOP",
        alert_sink: Callable[[str, dict[str, Any]], None] | None = None,
        event_sink: Callable[[dict[str, Any]], None] | None = None,
        flatten_fn: Callable[[], dict[str, Any]] | None = None,
        cancel_fn: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self.kill_switch = kill_switch or KillSwitch()
        self.max_drawdown_pct = max_drawdown_pct
        self.max_daily_loss_pct = max_daily_loss_pct
        self.kill_switch_file = kill_switch_file
        self.alert_sink = alert_sink
        self.event_sink = event_sink
        self.flatten_fn = flatten_fn
        self.cancel_fn = cancel_fn
        self.halted = False
        self.last_event: CircuitBreakerEvent | None = None
        self.events: list[CircuitBreakerEvent] = []

    def evaluate(
        self,
        *,
        equity: float,
        daily_pnl: float,
        drawdown_pct: float,
        stop_file_present: bool = False,
    ) -> dict[str, Any]:
        if stop_file_present:
            return self._breach(
                trigger="STOP_FILE",
                reason_code="KILL_SWITCH_STOP_FILE",
                details={"file": self.kill_switch_file},
            )
        if equity > 0 and daily_pnl < 0:
            daily_loss_pct = abs(daily_pnl) / equity
            if daily_loss_pct >= self.max_daily_loss_pct:
                return self._breach(
                    trigger="DAILY_LOSS",
                    reason_code="OKF_DAILY_LOSS_BREACH",
                    details={
                        "daily_loss_pct": daily_loss_pct,
                        "limit": self.max_daily_loss_pct,
                    },
                )
        if drawdown_pct >= self.max_drawdown_pct:
            return self._breach(
                trigger="DRAWDOWN",
                reason_code="OKF_DRAWDOWN_BREACH",
                details={
                    "drawdown_pct": drawdown_pct,
                    "limit": self.max_drawdown_pct,
                },
            )
        return {
            "breached": False,
            "halted": self.halted or self.kill_switch.active,
            "new_intents_allowed": not (self.halted or self.kill_switch.active),
            "llm_can_bypass": False,
        }

    def _breach(self, *, trigger: str, reason_code: str, details: dict[str, Any]) -> dict[str, Any]:
        actions = [
            "stop_new_trade_intents",
            "activate_kill_switch",
            "cancel_eligible_open_orders",
            "flatten_positions_per_safe_policy",
            "halt_autonomous_loop",
            "persist_reason",
            "alert_operators",
            "require_explicit_operator_recovery",
        ]
        self.kill_switch.activate(f"{reason_code}:{trigger}")
        self.halted = True
        cancel_result: dict[str, Any] = {"attempted": False}
        flatten_result: dict[str, Any] = {"attempted": False}
        if self.cancel_fn is not None:
            cancel_result = {"attempted": True, **(self.cancel_fn() or {})}
        if self.flatten_fn is not None:
            flatten_result = {"attempted": True, **(self.flatten_fn() or {})}

        event = CircuitBreakerEvent(
            trigger=trigger,
            reason_code=reason_code,
            timestamp=datetime.now(UTC).isoformat(),
            details=details,
            actions=actions,
        )
        self.last_event = event
        self.events.append(event)
        payload = {
            "type": "OKF_CIRCUIT_BREAKER",
            "trigger": trigger,
            "reason_code": reason_code,
            "timestamp": event.timestamp,
            "details": details,
            "actions": actions,
            "cancel_result": cancel_result,
            "flatten_result": flatten_result,
            "llm_can_bypass": False,
            "llm_can_deactivate": False,
        }
        if self.event_sink:
            self.event_sink(payload)
        if self.alert_sink:
            self.alert_sink("okf_circuit_breaker", payload)
        return {
            "breached": True,
            "halted": True,
            "new_intents_allowed": False,
            "reason_code": reason_code,
            "trigger": trigger,
            "details": details,
            "actions": actions,
            "cancel_result": cancel_result,
            "flatten_result": flatten_result,
            "requires_operator_recovery": True,
            "llm_can_bypass": False,
        }
