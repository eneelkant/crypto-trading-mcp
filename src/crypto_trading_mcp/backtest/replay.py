from __future__ import annotations

from typing import Iterator, Sequence

from crypto_trading_mcp.backtest.models import NormalizedCandle


class LookaheadGuard:
    """Ensures strategy decisions only see candles at or before index T."""

    def __init__(self, candles: Sequence[NormalizedCandle], *, enabled: bool = True) -> None:
        self._all = list(candles)
        self.enabled = enabled
        self._cursor = -1
        self.violations: list[str] = []

    def __len__(self) -> int:
        return len(self._all)

    def advance(self) -> NormalizedCandle:
        self._cursor += 1
        if self._cursor >= len(self._all):
            raise IndexError("Past end of historical series")
        return self._all[self._cursor]

    @property
    def index(self) -> int:
        return self._cursor

    def available(self) -> list[NormalizedCandle]:
        if self._cursor < 0:
            return []
        return self._all[: self._cursor + 1]

    def future(self) -> list[NormalizedCandle]:
        return self._all[self._cursor + 1 :]

    def assert_no_future_access(self, used: Sequence[NormalizedCandle]) -> None:
        if not self.enabled:
            return
        limit = self._all[self._cursor].timestamp if self._cursor >= 0 else None
        for c in used:
            if limit is not None and c.timestamp > limit:
                msg = f"Lookahead violation: used {c.timestamp.isoformat()} after {limit.isoformat()}"
                self.violations.append(msg)
                raise RuntimeError(msg)

    def iter_closed(self) -> Iterator[tuple[int, NormalizedCandle, list[NormalizedCandle]]]:
        for i, candle in enumerate(self._all):
            self._cursor = i
            hist = self._all[: i + 1]
            yield i, candle, hist
