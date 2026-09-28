from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class DurableStore(ABC):
    """Single persistence surface for portfolio, orders, intents, audit events."""

    @abstractmethod
    def put_json(self, collection: str, key: str, value: dict[str, Any]) -> None: ...

    @abstractmethod
    def get_json(self, collection: str, key: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def list_json(self, collection: str, *, limit: int = 100) -> list[dict[str, Any]]: ...

    @abstractmethod
    def delete(self, collection: str, key: str) -> None: ...

    def health(self) -> dict[str, Any]:
        return {"ok": True, "backend": type(self).__name__}
