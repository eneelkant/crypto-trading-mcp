from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ProviderResult:
    status: str  # AVAILABLE | UNAVAILABLE
    data: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    sources: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "data": self.data,
            "reason": self.reason,
            "sources": self.sources,
        }


class SentimentProvider(Protocol):
    def fetch(self, symbol: str) -> ProviderResult: ...


class OnChainProvider(Protocol):
    def fetch(self, symbol: str) -> ProviderResult: ...


class MacroEventProvider(Protocol):
    def fetch(self, symbol: str) -> ProviderResult: ...


class UnavailableSentimentProvider:
    def fetch(self, symbol: str) -> ProviderResult:
        return ProviderResult(
            status="UNAVAILABLE",
            reason=(
                f"No sentiment data source configured for {symbol}. "
                "Refusing to fabricate news/social sentiment."
            ),
        )


class UnavailableOnChainProvider:
    def fetch(self, symbol: str) -> ProviderResult:
        return ProviderResult(
            status="UNAVAILABLE",
            reason=(
                f"No on-chain data source configured for {symbol}. "
                "Refusing to fabricate whale/flow metrics."
            ),
        )


class UnavailableMacroEventProvider:
    def fetch(self, symbol: str) -> ProviderResult:
        return ProviderResult(
            status="UNAVAILABLE",
            reason=(
                f"No macro/event calendar configured for {symbol}. "
                "Refusing to invent economic or regulatory events."
            ),
        )
