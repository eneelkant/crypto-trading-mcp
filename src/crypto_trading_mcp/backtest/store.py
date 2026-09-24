from __future__ import annotations

import json
from typing import Any

from crypto_trading_mcp.backtest.models import BacktestResult
from crypto_trading_mcp.paper.persistence import InMemoryPaperStore, PaperStore, SqlitePaperStore


class BacktestStore:
    """Persist backtest artifacts via the Phase 5 store abstraction."""

    def __init__(self, store: PaperStore | None = None) -> None:
        self.store = store or InMemoryPaperStore()
        self.runs: list[dict[str, Any]] = []

    def save_result(self, result: BacktestResult) -> None:
        payload = result.to_dict()
        self.runs.append(
            {
                "backtest_id": result.identity.backtest_id,
                "strategy_id": result.identity.strategy_id,
                "partition": result.identity.partition.value,
                "structural_hash": result.structural_hash,
            }
        )
        self.store.save_event(
            {
                "type": "BACKTEST_RUN",
                "session_id": result.identity.backtest_id,
                "payload": {
                    "identity": result.identity.model_dump(mode="json"),
                    "metrics": result.metrics,
                    "risk_metrics": result.risk_metrics,
                    "warnings": [w.model_dump() for w in result.warnings],
                    "structural_hash": result.structural_hash,
                },
            }
        )
        for order in result.orders:
            self.store.save_order({**order, "session_id": result.identity.backtest_id})
        for fill in result.fills:
            self.store.save_fill({**fill, "session_id": result.identity.backtest_id})
        for trade in result.trades:
            self.store.save_trade({**trade, "session_id": result.identity.backtest_id})
        self.store.save_snapshot(
            {
                "session_id": result.identity.backtest_id,
                "equity_curve": [e.model_dump() for e in result.equity_curve],
                "final_equity": result.final_equity,
            }
        )

    def list_runs(self) -> list[dict[str, Any]]:
        return list(self.runs)

    def get_run(self, backtest_id: str) -> dict[str, Any] | None:
        events = self.store.load_events(backtest_id)
        for event in reversed(events):
            if event.get("type") == "BACKTEST_RUN":
                return event.get("payload")
        return None


__all__ = ["BacktestStore", "InMemoryPaperStore", "SqlitePaperStore"]
