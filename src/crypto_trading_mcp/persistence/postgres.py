from __future__ import annotations

from typing import Any

from crypto_trading_mcp.persistence.base import DurableStore


class PostgresDurableStore(DurableStore):
    """Production Postgres interface.

    Construction requires an injected connection factory. No driver is bundled by
    default so local paper installs stay light. Cloud paper/live deploys wire this.
    """

    def __init__(self, connect: Any) -> None:
        self._connect = connect
        self._ensure()

    def _conn(self) -> Any:
        return self._connect()

    def _ensure(self) -> None:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS kv (
                      collection TEXT NOT NULL,
                      key TEXT NOT NULL,
                      value JSONB NOT NULL,
                      updated_at TIMESTAMPTZ DEFAULT NOW(),
                      PRIMARY KEY (collection, key)
                    )
                    """
                )
            conn.commit()

    def put_json(self, collection: str, key: str, value: dict[str, Any]) -> None:
        import json

        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO kv(collection, key, value) VALUES (%s, %s, %s::jsonb)
                    ON CONFLICT (collection, key) DO UPDATE
                    SET value = EXCLUDED.value, updated_at = NOW()
                    """,
                    (collection, key, json.dumps(value)),
                )
            conn.commit()

    def get_json(self, collection: str, key: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT value FROM kv WHERE collection=%s AND key=%s",
                    (collection, key),
                )
                row = cur.fetchone()
        if not row:
            return None
        data = row[0]
        return data if isinstance(data, dict) else None

    def list_json(self, collection: str, *, limit: int = 100) -> list[dict[str, Any]]:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT value FROM kv
                    WHERE collection=%s
                    ORDER BY updated_at DESC
                    LIMIT %s
                    """,
                    (collection, int(limit)),
                )
                rows = cur.fetchall()
        return [r[0] for r in rows if isinstance(r[0], dict)]

    def delete(self, collection: str, key: str) -> None:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM kv WHERE collection=%s AND key=%s",
                    (collection, key),
                )
            conn.commit()

    def health(self) -> dict[str, Any]:
        try:
            with self._conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
            return {"ok": True, "backend": "postgres"}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "backend": "postgres", "error": str(exc)}
