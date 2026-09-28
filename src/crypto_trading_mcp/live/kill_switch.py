from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable, Protocol

from crypto_trading_mcp.risk.config import KillSwitch


class OrderCanceller(Protocol):
    def cancel_all_open_orders(self) -> dict[str, Any]: ...


class LiveKillSwitch:
    """Extends KillSwitch with live cancel-all + durable event recording."""

    def __init__(
        self,
        base: KillSwitch | None = None,
        *,
        event_sink: Callable[[dict[str, Any]], None] | None = None,
        alert_sink: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self.base = base or KillSwitch()
        self.event_sink = event_sink
        self.alert_sink = alert_sink
        self.last_cancel_result: dict[str, Any] | None = None

    @property
    def active(self) -> bool:
        return self.base.active

    def activate(
        self,
        reason: str = "operator",
        *,
        canceller: OrderCanceller | None = None,
        live_mode: bool = False,
    ) -> dict[str, Any]:
        self.base.activate(reason)
        cancel_result: dict[str, Any] = {
            "attempted": False,
            "cancelled": [],
            "failures": [],
        }
        if live_mode and canceller is not None:
            cancel_result["attempted"] = True
            try:
                raw = canceller.cancel_all_open_orders()
                cancel_result.update(raw if isinstance(raw, dict) else {"raw": raw})
                if cancel_result.get("failures"):
                    cancel_result["reason_codes"] = ["OPEN_ORDER_CANCELLATION_FAILURE"]
            except Exception as exc:  # noqa: BLE001
                cancel_result["failures"].append(str(exc))
                cancel_result["reason_codes"] = ["OPEN_ORDER_CANCELLATION_FAILURE"]
        self.last_cancel_result = cancel_result
        event = {
            "type": "KILL_SWITCH_ACTIVATED",
            "reason": reason,
            "timestamp": datetime.now(UTC).isoformat(),
            "cancel_result": {
                "attempted": cancel_result.get("attempted"),
                "failure_count": len(cancel_result.get("failures") or []),
                "reason_codes": cancel_result.get("reason_codes") or [],
            },
            "LIVE_TRADING_ENABLED": False,
        }
        if self.event_sink:
            self.event_sink(event)
        if self.alert_sink:
            self.alert_sink("kill_switch", event)
        return {
            "active": True,
            "reason": reason,
            "cancel_result": cancel_result,
            "blocks_new_orders": True,
        }

    def deactivate(self, *, operator_authorized: bool = False) -> None:
        self.base.deactivate(operator_authorized=operator_authorized)

    def status(self) -> dict[str, Any]:
        st = self.base.status()
        return {
            "active": st.active,
            "reason": st.reason,
            "last_cancel_result": self.last_cancel_result,
            "llm_can_deactivate": False,
        }
