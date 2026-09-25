from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

TrailingMode = Literal["atr", "percentage", "fixed_distance"]


@dataclass
class TrailingStopState:
    mode: TrailingMode
    atr: float = 0.0
    multiplier: float = 2.0
    percentage: float = 0.02
    distance: float = 0.0
    allow_widen: bool = False


class TrailingStopEngine:
    """Deterministic trailing stops that never widen risk unless explicitly allowed."""

    def __init__(self) -> None:
        self._states: dict[str, TrailingStopState] = {}

    def configure(self, symbol: str, state: TrailingStopState) -> None:
        self._states[symbol.upper()] = state

    def get(self, symbol: str) -> TrailingStopState | None:
        return self._states.get(symbol.upper())

    def update(
        self,
        *,
        symbol: str,
        side: str,
        price: float,
        current_stop: float | None,
    ) -> float | None:
        state = self._states.get(symbol.upper())
        if state is None:
            return current_stop
        side_u = side.upper()
        if state.mode == "atr":
            if state.atr <= 0:
                return current_stop
            candidate = (
                price - state.atr * state.multiplier
                if side_u in {"LONG", "BUY"}
                else price + state.atr * state.multiplier
            )
        elif state.mode == "percentage":
            candidate = (
                price * (1.0 - state.percentage)
                if side_u in {"LONG", "BUY"}
                else price * (1.0 + state.percentage)
            )
        else:
            if state.distance <= 0:
                return current_stop
            candidate = (
                price - state.distance
                if side_u in {"LONG", "BUY"}
                else price + state.distance
            )
        return self._ratchet(side_u, current_stop, candidate, allow_widen=state.allow_widen)

    @staticmethod
    def _ratchet(
        side: str,
        current_stop: float | None,
        candidate: float,
        *,
        allow_widen: bool,
    ) -> float:
        if current_stop is None:
            return candidate
        if allow_widen:
            return candidate
        if side in {"LONG", "BUY"}:
            # Never move stop down (increase risk).
            return max(current_stop, candidate)
        # Short: never move stop up.
        return min(current_stop, candidate)

    def to_dict(self) -> dict[str, Any]:
        return {
            k: {
                "mode": v.mode,
                "atr": v.atr,
                "multiplier": v.multiplier,
                "percentage": v.percentage,
                "distance": v.distance,
                "allow_widen": v.allow_widen,
            }
            for k, v in self._states.items()
        }
