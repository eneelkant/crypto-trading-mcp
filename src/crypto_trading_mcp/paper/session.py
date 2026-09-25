from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class PaperSession:
    session_id: str
    started_at: str
    ended_at: str | None = None
    starting_capital: float = 10_000.0
    ending_equity: float | None = None
    mode: str = "PAPER"
    strategy_versions: dict[str, str] = field(default_factory=dict)
    config_hash: str = ""
    status: str = "ACTIVE"  # ACTIVE | STOPPED | COMPLETED | KILLED

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "starting_capital": self.starting_capital,
            "ending_equity": self.ending_equity,
            "mode": self.mode,
            "strategy_versions": self.strategy_versions,
            "config_hash": self.config_hash,
            "status": self.status,
            "REAL_MONEY": "DISABLED",
            "TRADING_MODE": "PAPER",
        }

    def complete(self, ending_equity: float, *, status: str = "COMPLETED") -> None:
        self.ended_at = datetime.now(UTC).isoformat()
        self.ending_equity = ending_equity
        self.status = status


def make_session_id(prefix: str = "PAPER_SESSION", year: int | None = None, seq: int = 1) -> str:
    y = year or datetime.now(UTC).year
    return f"{prefix}_{y}_{seq:03d}"


def config_hash(config: dict[str, Any]) -> str:
    payload = json.dumps(config, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]
