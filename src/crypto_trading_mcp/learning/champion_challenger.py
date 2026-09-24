from __future__ import annotations

from typing import Any

from crypto_trading_mcp.learning.config import LearningConfig
from crypto_trading_mcp.learning.models import ChallengerDecision, ModelVersion


OVERFIT_FLAGS = {
    "POSSIBLE_OVERFITTING",
    "INSUFFICIENT_SAMPLE",
    "OOS_DEGRADATION",
    "HIGH_TURNOVER",
    "CALIBRATION_DEGRADATION",
}


def evaluate_challenger(
    challenger: ModelVersion,
    champion: ModelVersion | None,
    *,
    config: LearningConfig,
    sample_size: int,
    oos_return: float | None = None,
    champion_oos_return: float | None = None,
    turnover: float | None = None,
    risk_violations: int = 0,
) -> dict[str, Any]:
    reasons: list[str] = []
    flags: list[str] = []
    if sample_size < config.min_sample_size:
        flags.append("INSUFFICIENT_SAMPLE")
        reasons.append("insufficient_sample_size")
    if challenger.brier_score is not None and challenger.brier_score > config.max_acceptable_brier_score:
        flags.append("CALIBRATION_DEGRADATION")
        reasons.append("brier_above_threshold")
    if (
        oos_return is not None
        and champion_oos_return is not None
        and oos_return < champion_oos_return * 0.5
    ):
        flags.append("OOS_DEGRADATION")
        reasons.append("oos_degradation")
    if turnover is not None and turnover > 5.0:
        flags.append("HIGH_TURNOVER")
        reasons.append("high_turnover")
    if risk_violations > 0:
        reasons.append("risk_violations")
    # Never accept solely on higher backtest profit — require calibration OK and no hard flags
    accept = (
        not flags
        and risk_violations == 0
        and (challenger.brier_score is None or challenger.brier_score <= config.max_acceptable_brier_score)
    )
    if accept and champion is not None and oos_return is not None and champion_oos_return is not None:
        # Challenger must not be worse on OOS
        if oos_return < champion_oos_return:
            accept = False
            reasons.append("oos_worse_than_champion")
            flags.append("OOS_DEGRADATION")
    decision = ChallengerDecision.ACCEPTED if accept else ChallengerDecision.REJECTED
    challenger.decision = decision
    challenger.decision_reasons = reasons + flags
    if accept:
        challenger.champion = True
        if champion is not None:
            champion.champion = False
    return {
        "decision": decision.value,
        "reasons": reasons,
        "flags": flags,
        "accepted": accept,
    }
