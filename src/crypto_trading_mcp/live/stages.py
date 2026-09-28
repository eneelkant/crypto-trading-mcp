from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TradingStage(str, Enum):
    STAGE_0_BACKTEST = "STAGE_0_BACKTEST"
    STAGE_1_LOCAL_PAPER = "STAGE_1_LOCAL_PAPER"
    STAGE_2_CLOUD_PAPER = "STAGE_2_CLOUD_PAPER"
    STAGE_3_PRODUCTION_READ_ONLY = "STAGE_3_PRODUCTION_READ_ONLY"
    STAGE_4_LIVE_DRY_RUN = "STAGE_4_LIVE_DRY_RUN"
    STAGE_5_CONTROLLED_LIVE = "STAGE_5_CONTROLLED_LIVE"
    STAGE_6_AUTONOMOUS_LIVE = "STAGE_6_AUTONOMOUS_LIVE"


_ORDER = [
    TradingStage.STAGE_0_BACKTEST,
    TradingStage.STAGE_1_LOCAL_PAPER,
    TradingStage.STAGE_2_CLOUD_PAPER,
    TradingStage.STAGE_3_PRODUCTION_READ_ONLY,
    TradingStage.STAGE_4_LIVE_DRY_RUN,
    TradingStage.STAGE_5_CONTROLLED_LIVE,
    TradingStage.STAGE_6_AUTONOMOUS_LIVE,
]


class StagePromotionError(PermissionError):
    pass


class TradingStageManager(BaseModel):
    """Explicit, auditable stage control. No automatic promotion. No skipping."""

    current: TradingStage = TradingStage.STAGE_1_LOCAL_PAPER
    history: list[dict[str, Any]] = Field(default_factory=list)

    def index(self, stage: TradingStage) -> int:
        return _ORDER.index(stage)

    def allows_live_orders(self) -> bool:
        return self.current in {
            TradingStage.STAGE_5_CONTROLLED_LIVE,
            TradingStage.STAGE_6_AUTONOMOUS_LIVE,
        }

    def allows_production_reads(self) -> bool:
        return self.index(self.current) >= self.index(
            TradingStage.STAGE_3_PRODUCTION_READ_ONLY
        )

    def promote(
        self,
        target: TradingStage,
        *,
        operator: str,
        evidence: str,
        force_skip: bool = False,
    ) -> dict[str, Any]:
        if force_skip:
            raise StagePromotionError("Stage skipping is forbidden")
        cur_i = self.index(self.current)
        tgt_i = self.index(target)
        if tgt_i == cur_i:
            return {"promoted": False, "reason": "ALREADY_AT_STAGE", "current": self.current.value}
        if tgt_i < cur_i:
            # demotion allowed with audit
            self.history.append(
                {
                    "from": self.current.value,
                    "to": target.value,
                    "operator": operator,
                    "evidence": evidence,
                    "action": "demote",
                }
            )
            self.current = target
            return {"promoted": True, "action": "demote", "current": self.current.value}
        if tgt_i > cur_i + 1:
            raise StagePromotionError(
                f"Cannot skip from {self.current.value} to {target.value}"
            )
        if not evidence.strip():
            raise StagePromotionError("Promotion requires non-empty evidence")
        if not operator.strip():
            raise StagePromotionError("Promotion requires operator identity")
        self.history.append(
            {
                "from": self.current.value,
                "to": target.value,
                "operator": operator,
                "evidence": evidence,
                "action": "promote",
            }
        )
        self.current = target
        return {"promoted": True, "action": "promote", "current": self.current.value}

    def status(self) -> dict[str, Any]:
        return {
            "current": self.current.value,
            "allows_live_orders": self.allows_live_orders(),
            "allows_production_reads": self.allows_production_reads(),
            "history_len": len(self.history),
        }
