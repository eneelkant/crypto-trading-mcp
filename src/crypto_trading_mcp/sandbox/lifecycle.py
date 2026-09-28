from __future__ import annotations

from enum import Enum
from typing import Any


class OrderLifecycleState(str, Enum):
    CREATE_INTENT = "CREATE_INTENT"
    RISK_CHECK = "RISK_CHECK"
    IDEMPOTENCY_CHECK = "IDEMPOTENCY_CHECK"
    SUBMIT = "SUBMIT"
    ACK = "ACK"
    OPEN_NEW = "OPEN_NEW"
    PARTIAL_FILL = "PARTIAL_FILL"
    FULL_FILL = "FULL_FILL"
    POSITION_UPDATE = "POSITION_UPDATE"
    CANCEL = "CANCEL"
    CLOSE = "CLOSE"
    RECONCILIATION = "RECONCILIATION"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


_TRANSITIONS: dict[OrderLifecycleState, set[OrderLifecycleState]] = {
    OrderLifecycleState.CREATE_INTENT: {
        OrderLifecycleState.RISK_CHECK,
        OrderLifecycleState.BLOCKED,
        OrderLifecycleState.FAILED,
    },
    OrderLifecycleState.RISK_CHECK: {
        OrderLifecycleState.IDEMPOTENCY_CHECK,
        OrderLifecycleState.BLOCKED,
        OrderLifecycleState.FAILED,
    },
    OrderLifecycleState.IDEMPOTENCY_CHECK: {
        OrderLifecycleState.SUBMIT,
        OrderLifecycleState.BLOCKED,
        OrderLifecycleState.FAILED,
    },
    OrderLifecycleState.SUBMIT: {
        OrderLifecycleState.ACK,
        OrderLifecycleState.RECONCILIATION,  # ambiguous → reconcile first
        OrderLifecycleState.FAILED,
    },
    OrderLifecycleState.ACK: {
        OrderLifecycleState.OPEN_NEW,
        OrderLifecycleState.PARTIAL_FILL,
        OrderLifecycleState.FULL_FILL,
        OrderLifecycleState.CANCEL,
        OrderLifecycleState.FAILED,
    },
    OrderLifecycleState.OPEN_NEW: {
        OrderLifecycleState.PARTIAL_FILL,
        OrderLifecycleState.FULL_FILL,
        OrderLifecycleState.CANCEL,
        OrderLifecycleState.FAILED,
    },
    OrderLifecycleState.PARTIAL_FILL: {
        OrderLifecycleState.FULL_FILL,
        OrderLifecycleState.CANCEL,
        OrderLifecycleState.POSITION_UPDATE,
        OrderLifecycleState.FAILED,
    },
    OrderLifecycleState.FULL_FILL: {
        OrderLifecycleState.POSITION_UPDATE,
        OrderLifecycleState.CLOSE,
        OrderLifecycleState.RECONCILIATION,
    },
    OrderLifecycleState.POSITION_UPDATE: {
        OrderLifecycleState.CLOSE,
        OrderLifecycleState.RECONCILIATION,
        OrderLifecycleState.CANCEL,
    },
    OrderLifecycleState.CANCEL: {
        OrderLifecycleState.CLOSE,
        OrderLifecycleState.RECONCILIATION,
    },
    OrderLifecycleState.CLOSE: {OrderLifecycleState.RECONCILIATION},
    OrderLifecycleState.RECONCILIATION: set(),
    OrderLifecycleState.FAILED: {OrderLifecycleState.RECONCILIATION},
    OrderLifecycleState.BLOCKED: set(),
}


class OrderLifecycleMachine:
    def __init__(self, state: OrderLifecycleState = OrderLifecycleState.CREATE_INTENT) -> None:
        self.state = state
        self.history: list[str] = [state.value]

    def transition(self, target: OrderLifecycleState) -> OrderLifecycleState:
        allowed = _TRANSITIONS.get(self.state, set())
        if target not in allowed:
            raise ValueError(f"Illegal lifecycle transition {self.state.value} → {target.value}")
        self.state = target
        self.history.append(target.value)
        return self.state

    def status(self) -> dict[str, Any]:
        return {"state": self.state.value, "history": list(self.history)}
