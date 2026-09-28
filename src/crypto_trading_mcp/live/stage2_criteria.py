from __future__ import annotations

from typing import Any

from crypto_trading_mcp.live.stages import TradingStage


STAGE2_REQUIRED = [
    "cloud_deployment_readiness",
    "postgres_or_sqlite_durable_store",
    "sandbox_health",
    "credential_validation",
    "market_data_freshness",
    "order_lifecycle",
    "reconciliation",
    "kill_switch",
    "alerting",
    "restart_recovery",
    "deterministic_risk",
    "complete_tests",
    "security_validation",
]


def evaluate_stage2_entry(checklist: dict[str, bool]) -> dict[str, Any]:
    missing = [k for k in STAGE2_REQUIRED if not checklist.get(k)]
    return {
        "stage": TradingStage.STAGE_2_CLOUD_PAPER.value,
        "ready": not missing,
        "missing": missing,
        "auto_advance_to_stage3": False,
        "llm_can_promote": False,
        "agents_can_promote": False,
    }
