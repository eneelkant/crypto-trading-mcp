from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from crypto_trading_mcp.persistence.base import DurableStore


class SqliteDurableStore(DurableStore):
    """Local development durable store. Not for multi-writer cloud without care."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS kv (
              collection TEXT NOT NULL,
              key TEXT NOT NULL,
              value TEXT NOT NULL,
              updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
              PRIMARY KEY (collection, key)
            )
            """
        )
        self._conn.commit()

    def put_json(self, collection: str, key: str, value: dict[str, Any]) -> None:
        payload = json.dumps(value, sort_keys=True)
        self._conn.execute(
            """
            INSERT INTO kv(collection, key, value) VALUES (?, ?, ?)
            ON CONFLICT(collection, key) DO UPDATE SET
              value=excluded.value,
              updated_at=CURRENT_TIMESTAMP
            """,
            (collection, key, payload),
        )
        self._conn.commit()

    def get_json(self, collection: str, key: str) -> dict[str, Any] | None:
        cur = self._conn.execute(
            "SELECT value FROM kv WHERE collection=? AND key=?",
            (collection, key),
        )
        row = cur.fetchone()
        if not row:
            return None
        data = json.loads(row[0])
        return data if isinstance(data, dict) else None

    def list_json(self, collection: str, *, limit: int = 100) -> list[dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT value FROM kv WHERE collection=? ORDER BY updated_at DESC LIMIT ?",
            (collection, int(limit)),
        )
        out: list[dict[str, Any]] = []
        for (value,) in cur.fetchall():
            data = json.loads(value)
            if isinstance(data, dict):
                out.append(data)
        return out

    def delete(self, collection: str, key: str) -> None:
        self._conn.execute(
            "DELETE FROM kv WHERE collection=? AND key=?",
            (collection, key),
        )
        self._conn.commit()

    def health(self) -> dict[str, Any]:
        try:
            self._conn.execute("SELECT 1")
            return {"ok": True, "backend": "sqlite", "path": self.path}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "backend": "sqlite", "error": str(exc)}
