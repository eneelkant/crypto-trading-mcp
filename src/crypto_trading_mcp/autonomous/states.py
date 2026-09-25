from __future__ import annotations

from enum import StrEnum


class CycleState(StrEnum):
    CYCLE_STARTED = "CYCLE_STARTED"
    MARKET_DATA_READY = "MARKET_DATA_READY"
    ANALYSIS_RUNNING = "ANALYSIS_RUNNING"
    CONSENSUS_READY = "CONSENSUS_READY"
    TRADE_PROPOSED = "TRADE_PROPOSED"
    RISK_VALIDATING = "RISK_VALIDATING"
    RISK_APPROVED = "RISK_APPROVED"
    RISK_REJECTED = "RISK_REJECTED"
    ORDER_SUBMITTED = "ORDER_SUBMITTED"
    ORDER_PARTIALLY_FILLED = "ORDER_PARTIALLY_FILLED"
    ORDER_FILLED = "ORDER_FILLED"
    ORDER_CANCELLED = "ORDER_CANCELLED"
    ORDER_EXPIRED = "ORDER_EXPIRED"
    POSITION_UPDATED = "POSITION_UPDATED"
    CYCLE_COMPLETED = "CYCLE_COMPLETED"
    CYCLE_FAILED = "CYCLE_FAILED"


CYCLE_TRANSITIONS: dict[CycleState, set[CycleState]] = {
    CycleState.CYCLE_STARTED: {
        CycleState.MARKET_DATA_READY,
        CycleState.CYCLE_FAILED,
    },
    CycleState.MARKET_DATA_READY: {
        CycleState.ANALYSIS_RUNNING,
        CycleState.CYCLE_FAILED,
        CycleState.CYCLE_COMPLETED,
    },
    CycleState.ANALYSIS_RUNNING: {
        CycleState.CONSENSUS_READY,
        CycleState.CYCLE_FAILED,
        CycleState.CYCLE_COMPLETED,
    },
    CycleState.CONSENSUS_READY: {
        CycleState.TRADE_PROPOSED,
        CycleState.CYCLE_COMPLETED,
        CycleState.CYCLE_FAILED,
    },
    CycleState.TRADE_PROPOSED: {
        CycleState.RISK_VALIDATING,
        CycleState.CYCLE_FAILED,
    },
    CycleState.RISK_VALIDATING: {
        CycleState.RISK_APPROVED,
        CycleState.RISK_REJECTED,
        CycleState.CYCLE_FAILED,
    },
    CycleState.RISK_APPROVED: {
        CycleState.ORDER_SUBMITTED,
        CycleState.CYCLE_FAILED,
    },
    CycleState.RISK_REJECTED: {CycleState.CYCLE_COMPLETED},
    CycleState.ORDER_SUBMITTED: {
        CycleState.ORDER_PARTIALLY_FILLED,
        CycleState.ORDER_FILLED,
        CycleState.ORDER_CANCELLED,
        CycleState.ORDER_EXPIRED,
        CycleState.CYCLE_FAILED,
    },
    CycleState.ORDER_PARTIALLY_FILLED: {
        CycleState.ORDER_FILLED,
        CycleState.ORDER_CANCELLED,
        CycleState.POSITION_UPDATED,
    },
    CycleState.ORDER_FILLED: {CycleState.POSITION_UPDATED, CycleState.CYCLE_COMPLETED},
    CycleState.ORDER_CANCELLED: {CycleState.CYCLE_COMPLETED},
    CycleState.ORDER_EXPIRED: {CycleState.CYCLE_COMPLETED},
    CycleState.POSITION_UPDATED: {CycleState.CYCLE_COMPLETED},
    CycleState.CYCLE_COMPLETED: set(),
    CycleState.CYCLE_FAILED: set(),
}


class CycleStateMachine:
    def __init__(self, initial: CycleState = CycleState.CYCLE_STARTED) -> None:
        self.state = initial

    def transition(self, new_state: CycleState) -> None:
        allowed = CYCLE_TRANSITIONS.get(self.state, set())
        if new_state not in allowed:
            raise ValueError(f"Invalid cycle transition {self.state} → {new_state}")
        self.state = new_state
