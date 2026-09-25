from __future__ import annotations

from typing import Any

from crypto_trading_mcp.learning.config import LearningConfig
from crypto_trading_mcp.learning.models import LearningProposal, ProposalStatus


def validate_proposal(
    proposal: LearningProposal,
    *,
    config: LearningConfig,
    sample_size: int,
    oos_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    flags: list[str] = []
    if sample_size < config.min_sample_size:
        flags.append("INSUFFICIENT_SAMPLE")
    oos = oos_metrics or {}
    if oos.get("brier") is not None and oos["brier"] > config.max_acceptable_brier_score:
        flags.append("CALIBRATION_DEGRADATION")
    if oos.get("degradation"):
        flags.append("OOS_DEGRADATION")
    if oos.get("turnover", 0) > 5:
        flags.append("HIGH_TURNOVER")
    if oos.get("in_sample_return") and oos.get("oos_return") is not None:
        if oos["in_sample_return"] > 0 and oos["oos_return"] < oos["in_sample_return"] * 0.3:
            flags.append("POSSIBLE_OVERFITTING")
    proposal.warning_flags = flags
    if flags:
        proposal.status = ProposalStatus.REJECTED
        return {"status": ProposalStatus.REJECTED.value, "flags": flags, "accepted": False}
    proposal.status = ProposalStatus.VALIDATION
    return {"status": ProposalStatus.VALIDATION.value, "flags": flags, "accepted": True}
