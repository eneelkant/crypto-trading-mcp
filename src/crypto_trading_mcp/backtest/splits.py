from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Sequence

from crypto_trading_mcp.backtest.models import DataPartition, NormalizedCandle


@dataclass(frozen=True)
class SplitWindow:
    partition: DataPartition
    start: datetime
    end: datetime
    candles: tuple[NormalizedCandle, ...]


def filter_range(
    candles: Sequence[NormalizedCandle],
    start: datetime,
    end: datetime,
) -> list[NormalizedCandle]:
    return [c for c in candles if start <= c.timestamp <= end]


def chronological_splits(
    candles: Sequence[NormalizedCandle],
    *,
    train_ratio: float = 0.6,
    val_ratio: float = 0.2,
) -> dict[DataPartition, list[NormalizedCandle]]:
    if not candles:
        return {
            DataPartition.TRAIN: [],
            DataPartition.VALIDATION: [],
            DataPartition.OUT_OF_SAMPLE: [],
        }
    n = len(candles)
    t_end = int(n * train_ratio)
    v_end = int(n * (train_ratio + val_ratio))
    return {
        DataPartition.TRAIN: list(candles[:t_end]),
        DataPartition.VALIDATION: list(candles[t_end:v_end]),
        DataPartition.OUT_OF_SAMPLE: list(candles[v_end:]),
    }


def walk_forward_windows(
    candles: Sequence[NormalizedCandle],
    *,
    training_days: int = 180,
    validation_days: int = 60,
    test_days: int = 60,
    step_days: int = 30,
    training_bars: int | None = None,
    validation_bars: int | None = None,
    test_bars: int | None = None,
    step_bars: int | None = None,
) -> list[dict[str, SplitWindow]]:
    """Generate train/val/OOS windows stepping forward (calendar days or bar counts)."""
    if not candles:
        return []

    # Prefer explicit bar-based windows (useful for short fixtures).
    if training_bars and validation_bars and test_bars:
        step = step_bars or max(1, training_bars // 4)
        windows: list[dict[str, SplitWindow]] = []
        i = 0
        n = len(candles)
        while i + training_bars + validation_bars + test_bars <= n:
            t0 = i
            t1 = i + training_bars
            v1 = t1 + validation_bars
            o1 = v1 + test_bars
            train = list(candles[t0:t1])
            val = list(candles[t1:v1])
            test = list(candles[v1:o1])
            windows.append(
                {
                    "train": SplitWindow(
                        DataPartition.TRAIN, train[0].timestamp, train[-1].timestamp, tuple(train)
                    ),
                    "validation": SplitWindow(
                        DataPartition.VALIDATION, val[0].timestamp, val[-1].timestamp, tuple(val)
                    ),
                    "out_of_sample": SplitWindow(
                        DataPartition.OUT_OF_SAMPLE, test[0].timestamp, test[-1].timestamp, tuple(test)
                    ),
                }
            )
            i += step
        return windows

    start = candles[0].timestamp
    end = candles[-1].timestamp
    windows = []
    cursor = start
    while True:
        train_start = cursor
        train_end = train_start + timedelta(days=training_days)
        val_end = train_end + timedelta(days=validation_days)
        test_end = val_end + timedelta(days=test_days)
        if test_end > end:
            break
        train = filter_range(candles, train_start, train_end)
        val = filter_range(candles, train_end + timedelta(microseconds=1), val_end)
        test = filter_range(candles, val_end + timedelta(microseconds=1), test_end)
        if train and val and test:
            windows.append(
                {
                    "train": SplitWindow(DataPartition.TRAIN, train_start, train_end, tuple(train)),
                    "validation": SplitWindow(
                        DataPartition.VALIDATION, train_end, val_end, tuple(val)
                    ),
                    "out_of_sample": SplitWindow(
                        DataPartition.OUT_OF_SAMPLE, val_end, test_end, tuple(test)
                    ),
                }
            )
        cursor = cursor + timedelta(days=step_days)
    # Fallback for short series: proportional bar windows
    if not windows and len(candles) >= 40:
        n = len(candles)
        tb = max(10, n // 3)
        vb = max(5, n // 6)
        ob = max(5, n // 6)
        return walk_forward_windows(
            candles,
            training_bars=tb,
            validation_bars=vb,
            test_bars=ob,
            step_bars=max(1, tb // 3),
        )
    return windows
