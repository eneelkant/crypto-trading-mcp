from __future__ import annotations

from enum import StrEnum


class TradingState(StrEnum):
    IDLE = "IDLE"
    SCANNING = "SCANNING"
    ANALYZING = "ANALYZING"
    DEBATING = "DEBATING"
    RISK_REVIEW = "RISK_REVIEW"
    TRADE_PLANNED = "TRADE_PLANNED"
    EXECUTING = "EXECUTING"
    EXECUTED = "EXECUTED"
    MONITORING = "MONITORING"
    CLOSED = "CLOSED"
    REFLECTING = "REFLECTING"
    FAILED = "FAILED"
    HALTED = "HALTED"


# Analysis-phase allowed transitions (no human-approval state; no live execution yet).
ANALYSIS_TRANSITIONS: dict[TradingState, set[TradingState]] = {
    TradingState.IDLE: {TradingState.SCANNING, TradingState.HALTED},
    TradingState.SCANNING: {TradingState.ANALYZING, TradingState.FAILED, TradingState.HALTED},
    TradingState.ANALYZING: {TradingState.DEBATING, TradingState.FAILED, TradingState.HALTED},
    TradingState.DEBATING: {
        TradingState.IDLE,
        TradingState.FAILED,
        TradingState.HALTED,
        TradingState.RISK_REVIEW,
    },
    TradingState.RISK_REVIEW: {
        TradingState.IDLE,
        TradingState.FAILED,
        TradingState.HALTED,
        # TRADE_PLANNED reserved for later execution phases — not used to place orders.
        TradingState.TRADE_PLANNED,
    },
    TradingState.TRADE_PLANNED: {
        TradingState.IDLE,
        TradingState.FAILED,
        TradingState.HALTED,
    },
    TradingState.FAILED: {TradingState.IDLE, TradingState.HALTED},
    TradingState.HALTED: {TradingState.IDLE},
}


class StateMachine:
    def __init__(self, initial: TradingState = TradingState.IDLE) -> None:
        self.state = initial

    def transition(self, new_state: TradingState) -> None:
        allowed = ANALYSIS_TRANSITIONS.get(self.state, set())
        if new_state not in allowed:
            raise ValueError(f"Invalid transition {self.state} → {new_state}")
        self.state = new_state
