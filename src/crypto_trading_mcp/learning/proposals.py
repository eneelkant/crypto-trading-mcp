from __future__ import annotations

from typing import Any

from crypto_trading_mcp.learning.models import LearningProposal, ProposalStatus


class ProposalStore:
    def __init__(self) -> None:
        self.proposals: list[LearningProposal] = []

    def create(self, **kwargs: Any) -> LearningProposal:
        proposal = LearningProposal(**kwargs)
        self.proposals.append(proposal)
        return proposal

    def update_status(self, proposal_id: str, status: ProposalStatus) -> LearningProposal | None:
        for p in self.proposals:
            if p.proposal_id == proposal_id:
                p.status = status
                return p
        return None

    def list(self) -> list[dict[str, Any]]:
        return [p.to_dict() for p in self.proposals]

    def get(self, proposal_id: str) -> LearningProposal | None:
        for p in self.proposals:
            if p.proposal_id == proposal_id:
                return p
        return None
