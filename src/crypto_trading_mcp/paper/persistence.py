from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Protocol


class PaperStore(Protocol):
    def save_event(self, event: dict[str, Any]) -> None: ...

    def save_order(self, order: dict[str, Any]) -> None: ...

    def save_fill(self, fill: dict[str, Any]) -> None: ...

    def save_trade(self, trade: dict[str, Any]) -> None: ...

    def save_snapshot(self, snapshot: dict[str, Any]) -> None: ...

    def save_session(self, session: dict[str, Any]) -> None: ...

    def load_orders(self, session_id: str | None = None) -> list[dict[str, Any]]: ...

    def load_trades(self, session_id: str | None = None) -> list[dict[str, Any]]: ...

    def load_events(self, session_id: str | None = None) -> list[dict[str, Any]]: ...


class InMemoryPaperStore:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.orders: list[dict[str, Any]] = []
        self.fills: list[dict[str, Any]] = []
        self.trades: list[dict[str, Any]] = []
        self.snapshots: list[dict[str, Any]] = []
        self.sessions: list[dict[str, Any]] = []

    def save_event(self, event: dict[str, Any]) -> None:
        self.events.append(event)

    def save_order(self, order: dict[str, Any]) -> None:
        self.orders.append(order)

    def save_fill(self, fill: dict[str, Any]) -> None:
        self.fills.append(fill)

    def save_trade(self, trade: dict[str, Any]) -> None:
        self.trades.append(trade)

    def save_snapshot(self, snapshot: dict[str, Any]) -> None:
        self.snapshots.append(snapshot)

    def save_session(self, session: dict[str, Any]) -> None:
        self.sessions.append(session)

    def load_orders(self, session_id: str | None = None) -> list[dict[str, Any]]:
        if session_id is None:
            return list(self.orders)
        return [o for o in self.orders if o.get("session_id") == session_id]

    def load_trades(self, session_id: str | None = None) -> list[dict[str, Any]]:
        if session_id is None:
            return list(self.trades)
        return [t for t in self.trades if t.get("session_id") == session_id]

    def load_events(self, session_id: str | None = None) -> list[dict[str, Any]]:
        if session_id is None:
            return list(self.events)
        return [e for e in self.events if e.get("session_id") == session_id]


class SqlitePaperStore:
    """SQLite persistence; schema kept simple for later PostgreSQL migration."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        cur = self._conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              session_id TEXT,
              payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS orders (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              session_id TEXT,
              order_id TEXT,
              payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS fills (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              session_id TEXT,
              payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS trades (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              session_id TEXT,
              payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS snapshots (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              session_id TEXT,
              payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              session_id TEXT,
              payload TEXT NOT NULL
            );
            """
        )
        self._conn.commit()

    def _insert(self, table: str, session_id: str | None, payload: dict[str, Any], extra: dict[str, Any] | None = None) -> None:
        cols = ["session_id", "payload"]
        vals: list[Any] = [session_id, json.dumps(payload, default=str)]
        if extra:
            for k, v in extra.items():
                cols.append(k)
                vals.append(v)
        placeholders = ", ".join("?" for _ in cols)
        self._conn.execute(
            f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})",
            vals,
        )
        self._conn.commit()

    def save_event(self, event: dict[str, Any]) -> None:
        self._insert("events", event.get("session_id"), event)

    def save_order(self, order: dict[str, Any]) -> None:
        self._insert(
            "orders",
            order.get("session_id"),
            order,
            {"order_id": order.get("order_id")},
        )

    def save_fill(self, fill: dict[str, Any]) -> None:
        self._insert("fills", fill.get("session_id"), fill)

    def save_trade(self, trade: dict[str, Any]) -> None:
        self._insert("trades", trade.get("session_id"), trade)

    def save_snapshot(self, snapshot: dict[str, Any]) -> None:
        self._insert("snapshots", snapshot.get("session_id"), snapshot)

    def save_session(self, session: dict[str, Any]) -> None:
        self._insert("sessions", session.get("session_id"), session)

    def _load(self, table: str, session_id: str | None = None) -> list[dict[str, Any]]:
        if session_id is None:
            rows = self._conn.execute(f"SELECT payload FROM {table}").fetchall()
        else:
            rows = self._conn.execute(
                f"SELECT payload FROM {table} WHERE session_id = ?", (session_id,)
            ).fetchall()
        return [json.loads(r["payload"]) for r in rows]

    def load_orders(self, session_id: str | None = None) -> list[dict[str, Any]]:
        return self._load("orders", session_id)

    def load_trades(self, session_id: str | None = None) -> list[dict[str, Any]]:
        return self._load("trades", session_id)

    def load_events(self, session_id: str | None = None) -> list[dict[str, Any]]:
        return self._load("events", session_id)

    def close(self) -> None:
        self._conn.close()
