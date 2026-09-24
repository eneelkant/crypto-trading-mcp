from __future__ import annotations

import csv
import json
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

from crypto_trading_mcp.backtest.models import NormalizedCandle, stable_hash
from crypto_trading_mcp.market.models import Candle


class HistoricalDataError(ValueError):
    """Raised when historical data fails validation."""


class HistoricalDataProvider(ABC):
    """Generic historical OHLCV interface. Phase 6: offline sources only."""

    name: str = "base"

    @abstractmethod
    def load(
        self,
        symbol: str,
        *,
        timeframe: str = "1h",
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[NormalizedCandle]: ...

    def data_version(self, candles: Sequence[NormalizedCandle]) -> str:
        payload = [c.to_dict() for c in candles]
        return stable_hash(payload)[:16]


class FutureProviderStub(HistoricalDataProvider):
    """Interface-only stubs for future remote providers (no credentials used)."""

    def __init__(self, name: str) -> None:
        self.name = name

    def load(
        self,
        symbol: str,
        *,
        timeframe: str = "1h",
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[NormalizedCandle]:
        raise HistoricalDataError(
            f"Provider '{self.name}' is not implemented in Phase 6 and requires no live credentials."
        )


class CCXTHistoricalStub(FutureProviderStub):
    def __init__(self) -> None:
        super().__init__("ccxt")


class CoinbaseHistoricalStub(FutureProviderStub):
    def __init__(self) -> None:
        super().__init__("coinbase")


class YahooFinanceStub(FutureProviderStub):
    def __init__(self) -> None:
        super().__init__("yahoo")


def _parse_ts(value: Any) -> datetime:
    if isinstance(value, datetime):
        ts = value
    else:
        text = str(value).replace("Z", "+00:00")
        ts = datetime.fromisoformat(text)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts.astimezone(UTC)


def validate_candles(candles: Sequence[NormalizedCandle]) -> list[NormalizedCandle]:
    if not candles:
        raise HistoricalDataError("No candles provided")
    # sort
    ordered = sorted(candles, key=lambda c: c.timestamp)
    seen: set[datetime] = set()
    prev: datetime | None = None
    out: list[NormalizedCandle] = []
    for c in ordered:
        if c.timestamp in seen:
            raise HistoricalDataError(f"Duplicate timestamp: {c.timestamp.isoformat()}")
        seen.add(c.timestamp)
        if prev is not None and c.timestamp < prev:
            raise HistoricalDataError("Unsorted timestamps after sort (internal error)")
        if c.volume < 0:
            raise HistoricalDataError(f"Negative volume at {c.timestamp.isoformat()}")
        if c.high < c.low:
            raise HistoricalDataError(f"Invalid OHLC high<low at {c.timestamp.isoformat()}")
        if c.high < max(c.open, c.close) or c.low > min(c.open, c.close):
            raise HistoricalDataError(f"Invalid OHLC relationship at {c.timestamp.isoformat()}")
        if any(x < 0 for x in (c.open, c.high, c.low, c.close)):
            raise HistoricalDataError(f"Negative price at {c.timestamp.isoformat()}")
        prev = c.timestamp
        out.append(c)
    return out


def to_market_candles(candles: Sequence[NormalizedCandle]) -> list[Candle]:
    return [
        Candle(
            timestamp=c.timestamp,
            open=c.open,
            high=c.high,
            low=c.low,
            close=c.close,
            volume=c.volume,
        )
        for c in candles
    ]


class MockHistoricalDataProvider(HistoricalDataProvider):
    """Deterministic synthetic OHLCV for offline tests."""

    name = "mock"

    def __init__(self, candles: list[NormalizedCandle] | None = None) -> None:
        self._candles = candles or []

    def load(
        self,
        symbol: str,
        *,
        timeframe: str = "1h",
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[NormalizedCandle]:
        rows = [
            c
            for c in self._candles
            if c.symbol.upper() == symbol.upper() and c.timeframe == timeframe
        ]
        if start:
            rows = [c for c in rows if c.timestamp >= start]
        if end:
            rows = [c for c in rows if c.timestamp <= end]
        return validate_candles(rows) if rows else []


class CSVHistoricalDataProvider(HistoricalDataProvider):
    name = "csv"

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def load(
        self,
        symbol: str,
        *,
        timeframe: str = "1h",
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[NormalizedCandle]:
        if not self.path.exists():
            raise HistoricalDataError(f"CSV not found: {self.path}")
        rows: list[NormalizedCandle] = []
        with self.path.open(encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                sym = str(row.get("symbol") or symbol).upper()
                if sym != symbol.upper():
                    continue
                tf = str(row.get("timeframe") or timeframe)
                if tf != timeframe:
                    continue
                candle = NormalizedCandle(
                    timestamp=_parse_ts(row["timestamp"]),
                    symbol=sym,
                    timeframe=tf,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume") or 0),
                )
                rows.append(candle)
        if start:
            rows = [c for c in rows if c.timestamp >= start]
        if end:
            rows = [c for c in rows if c.timestamp <= end]
        return validate_candles(rows)


class JSONHistoricalDataProvider(HistoricalDataProvider):
    name = "json"

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def load(
        self,
        symbol: str,
        *,
        timeframe: str = "1h",
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[NormalizedCandle]:
        if not self.path.exists():
            raise HistoricalDataError(f"JSON not found: {self.path}")
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise HistoricalDataError("JSON historical data must be a list of candles")
        rows: list[NormalizedCandle] = []
        for row in data:
            sym = str(row.get("symbol") or symbol).upper()
            if sym != symbol.upper():
                continue
            tf = str(row.get("timeframe") or timeframe)
            if tf != timeframe:
                continue
            rows.append(
                NormalizedCandle(
                    timestamp=_parse_ts(row["timestamp"]),
                    symbol=sym,
                    timeframe=tf,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume") or 0),
                )
            )
        if start:
            rows = [c for c in rows if c.timestamp >= start]
        if end:
            rows = [c for c in rows if c.timestamp <= end]
        return validate_candles(rows)


class ParquetHistoricalDataProvider(HistoricalDataProvider):
    """Optional parquet reader; fails safely if pyarrow/pandas unavailable."""

    name = "parquet"

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def load(
        self,
        symbol: str,
        *,
        timeframe: str = "1h",
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[NormalizedCandle]:
        try:
            import pandas as pd  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise HistoricalDataError(
                "Parquet support requires pandas; use CSV/JSON/Mock for Phase 6"
            ) from exc
        if not self.path.exists():
            raise HistoricalDataError(f"Parquet not found: {self.path}")
        frame = pd.read_parquet(self.path)
        rows: list[NormalizedCandle] = []
        for _, row in frame.iterrows():
            sym = str(row.get("symbol") or symbol).upper()
            if sym != symbol.upper():
                continue
            tf = str(row.get("timeframe") or timeframe)
            if tf != timeframe:
                continue
            rows.append(
                NormalizedCandle(
                    timestamp=_parse_ts(row["timestamp"]),
                    symbol=sym,
                    timeframe=tf,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume") or 0),
                )
            )
        if start:
            rows = [c for c in rows if c.timestamp >= start]
        if end:
            rows = [c for c in rows if c.timestamp <= end]
        return validate_candles(rows)


def generate_synthetic_candles(
    *,
    symbol: str = "BTC/USD",
    timeframe: str = "1h",
    n: int = 120,
    start: datetime | None = None,
    start_price: float = 100.0,
    seed: int = 42,
) -> list[NormalizedCandle]:
    """Deterministic synthetic series (no fabricated alternative datasets)."""
    import random
    from datetime import timedelta

    rng = random.Random(seed)
    ts0 = start or datetime(2025, 1, 1, tzinfo=UTC)
    step = {
        "5m": timedelta(minutes=5),
        "15m": timedelta(minutes=15),
        "1h": timedelta(hours=1),
        "4h": timedelta(hours=4),
        "1d": timedelta(days=1),
    }.get(timeframe, timedelta(hours=1))
    price = start_price
    out: list[NormalizedCandle] = []
    for i in range(n):
        # Mild deterministic walk with occasional breakouts.
        drift = 0.15 if (i % 25 == 24) else (rng.uniform(-0.8, 0.9))
        open_ = price
        close = max(1.0, open_ + drift)
        high = max(open_, close) + abs(rng.uniform(0.0, 0.4))
        low = min(open_, close) - abs(rng.uniform(0.0, 0.4))
        vol = 1000 + rng.uniform(0, 200) + (500 if i % 25 == 24 else 0)
        out.append(
            NormalizedCandle(
                timestamp=ts0 + i * step,
                symbol=symbol.upper(),
                timeframe=timeframe,
                open=round(open_, 6),
                high=round(high, 6),
                low=round(low, 6),
                close=round(close, 6),
                volume=round(vol, 4),
            )
        )
        price = close
    return validate_candles(out)
