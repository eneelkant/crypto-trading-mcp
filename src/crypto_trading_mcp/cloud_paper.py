"""Cloud-paper entrypoint. Incapable of submitting live orders by construction."""

from __future__ import annotations

import os
import time

from crypto_trading_mcp.autonomous.loop import AutonomousPaperLoop
from crypto_trading_mcp.config.settings import get_settings
from crypto_trading_mcp.live.gate import LiveTradingGate
from crypto_trading_mcp.live.policy import LiveExecutionPolicy
from crypto_trading_mcp.live.stages import TradingStage


def assert_cloud_paper_isolation() -> None:
    settings = get_settings()
    if settings.trading_mode != "paper" or settings.live_trading_enabled:
        raise RuntimeError("Cloud-paper requires TRADING_MODE=paper and LIVE_TRADING_ENABLED=false")
    if os.getenv("LIVE_TRADING_ENABLED", "false").lower() in {"1", "true", "yes"}:
        raise RuntimeError("Cloud-paper refuses LIVE_TRADING_ENABLED=true")
    gate = LiveTradingGate()
    result = gate.evaluate(
        LiveExecutionPolicy(
            trading_mode="paper",
            live_trading_enabled=False,
            stage=TradingStage.STAGE_2_CLOUD_PAPER,
            cloud_paper_isolated=True,
            credentials_healthy=True,
            credentials_allow_trading=True,
            market_data_fresh=True,
            exchange_healthy=True,
            reconciliation_ok=True,
            order_valid=True,
            exchange="coinbase",
            exchange_allowlist=["coinbase"],
        )
    )
    if result["approved"]:
        raise RuntimeError("Cloud-paper isolation failed: live gate approved")


def main() -> None:
    assert_cloud_paper_isolation()
    loop = AutonomousPaperLoop(
        config={
            "interval_seconds": float(os.getenv("PAPER_LOOP_INTERVAL", "30")),
            "symbols": ["BTC/USD"],
            "persist_state": True,
            "live_trading_enabled": False,
            "duplicate_cycle_protection": True,
        }
    )
    print(
        {
            "mode": "cloud_paper",
            "TRADING_MODE": "paper",
            "LIVE_TRADING_ENABLED": False,
            "Live Execution": "DISABLED",
            "stage": TradingStage.STAGE_2_CLOUD_PAPER.value,
        }
    )
    loop.start(background=False, max_cycles=int(os.getenv("PAPER_MAX_CYCLES", "0") or 0) or None)
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
