from __future__ import annotations

import hashlib
from typing import Any


def make_idempotency_key(
    *,
    strategy_id: str,
    symbol: str,
    timeframe: str,
    cycle_id: str,
    signal_version: str = "1",
    side: str | None = None,
) -> str:
    """Deterministic order idempotency key."""
    raw = "|".join(
        [
            strategy_id.strip().lower(),
            symbol.strip().upper(),
            timeframe.strip(),
            cycle_id.strip(),
            signal_version.strip(),
            (side or "").strip().upper(),
        ]
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"IDEM-{digest}"


def already_seen(store: set[str] | dict[str, Any], key: str) -> bool:
    return key in store
