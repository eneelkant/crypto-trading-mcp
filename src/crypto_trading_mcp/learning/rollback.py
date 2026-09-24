from __future__ import annotations

from typing import Any

from crypto_trading_mcp.learning.models import ModelVersion, ProposalStatus
from crypto_trading_mcp.learning.proposals import ProposalStore
from crypto_trading_mcp.learning.versioning import ModelVersionRegistry


class RollbackManager:
    def __init__(self, registry: ModelVersionRegistry, proposals: ProposalStore) -> None:
        self.registry = registry
        self.proposals = proposals
        self.events: list[dict[str, Any]] = []

    def rollback_to_champion(self, reason: str) -> dict[str, Any]:
        champ = self.registry.champion()
        # Demote non-champions; keep audit history
        for v in self.registry.versions:
            if champ is None or v.model_version != champ.model_version:
                v.champion = False
        if champ is not None:
            champ.champion = True
        for p in self.proposals.proposals:
            if p.status in {
                ProposalStatus.PAPER_TESTING,
                ProposalStatus.VALIDATION,
                ProposalStatus.OOS_TESTING,
                ProposalStatus.BACKTESTING,
                ProposalStatus.PROPOSED,
            }:
                p.status = ProposalStatus.ROLLED_BACK
        event = {
            "action": "ROLLBACK",
            "reason": reason,
            "champion": None if champ is None else champ.model_version,
        }
        self.events.append(event)
        return event
