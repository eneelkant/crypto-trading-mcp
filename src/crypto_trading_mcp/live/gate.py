from __future__ import annotations

from typing import Any

from crypto_trading_mcp.live.policy import LiveExecutionPolicy, LiveGateReason
from crypto_trading_mcp.live.stages import TradingStage


class LiveTradingGate:
    """Fail-closed gate. LLM output cannot bypass. Paper can never reach live adapters."""

    def evaluate(self, policy: LiveExecutionPolicy) -> dict[str, Any]:
        reasons: list[str] = []

        if policy.cloud_paper_isolated:
            reasons.append(LiveGateReason.LIVE_GATE_CLOUD_PAPER_ISOLATION.value)

        if policy.trading_mode != "live":
            reasons.append(LiveGateReason.LIVE_GATE_MODE_BLOCKED.value)
        if not policy.live_trading_enabled:
            reasons.append(LiveGateReason.LIVE_GATE_FLAG_BLOCKED.value)

        if policy.stage not in {
            TradingStage.STAGE_5_CONTROLLED_LIVE,
            TradingStage.STAGE_6_AUTONOMOUS_LIVE,
        }:
            reasons.append(LiveGateReason.LIVE_GATE_STAGE_NOT_ALLOWED.value)

        if policy.kill_switch_active:
            reasons.append(LiveGateReason.LIVE_GATE_KILL_SWITCH.value)
        if not policy.credentials_healthy:
            reasons.append(LiveGateReason.LIVE_GATE_CREDENTIAL_FAILURE.value)
        if not policy.credentials_allow_trading:
            reasons.append(LiveGateReason.LIVE_GATE_PERMISSION_FAILURE.value)
        if not policy.market_data_fresh:
            reasons.append(LiveGateReason.LIVE_GATE_MARKET_DATA_STALE.value)
        if not policy.exchange_healthy:
            reasons.append(LiveGateReason.LIVE_GATE_EXCHANGE_UNAVAILABLE.value)
        if not policy.risk_engine_healthy:
            reasons.append(LiveGateReason.LIVE_GATE_RISK_ENGINE_FAILURE.value)
        if not policy.reconciliation_ok:
            reasons.append(LiveGateReason.LIVE_GATE_RECONCILIATION_FAILURE.value)
        if not policy.clock_skew_ok:
            reasons.append(LiveGateReason.LIVE_GATE_CLOCK_SKEW.value)
        if not policy.idempotency_ok or policy.duplicate:
            reasons.append(LiveGateReason.LIVE_GATE_DUPLICATE_ORDER.value)
        if not policy.order_valid:
            reasons.append(LiveGateReason.LIVE_GATE_INVALID_ORDER.value)
        if not policy.daily_loss_ok:
            reasons.append(LiveGateReason.LIVE_GATE_DAILY_LOSS.value)
        if not policy.drawdown_ok:
            reasons.append(LiveGateReason.LIVE_GATE_DRAWDOWN.value)
        if not policy.position_ok:
            reasons.append(LiveGateReason.LIVE_GATE_POSITION_LIMIT.value)
        if not policy.exposure_ok:
            reasons.append(LiveGateReason.LIVE_GATE_EXPOSURE_LIMIT.value)

        exch = policy.exchange.lower().strip()
        if exch not in {e.lower() for e in policy.exchange_allowlist}:
            reasons.append(LiveGateReason.LIVE_GATE_EXCHANGE_NOT_ALLOWLISTED.value)
        if policy.instrument_allowlist and policy.symbol:
            if policy.symbol.upper() not in {s.upper() for s in policy.instrument_allowlist}:
                reasons.append(LiveGateReason.LIVE_GATE_INSTRUMENT_NOT_ALLOWLISTED.value)

        # Hard invariant: paper mode or disabled flag can never approve
        if policy.trading_mode != "live" or not policy.live_trading_enabled:
            approved = False
            if LiveGateReason.LIVE_GATE_MODE_BLOCKED.value not in reasons:
                reasons.append(LiveGateReason.LIVE_GATE_MODE_BLOCKED.value)
            if not policy.live_trading_enabled and (
                LiveGateReason.LIVE_GATE_FLAG_BLOCKED.value not in reasons
            ):
                reasons.append(LiveGateReason.LIVE_GATE_FLAG_BLOCKED.value)
        else:
            approved = not reasons

        if approved:
            reasons = [LiveGateReason.LIVE_GATE_OK.value]

        return {
            "approved": approved,
            "reason_codes": reasons,
            "Live Execution": "ENABLED" if approved else "DISABLED",
            "trading_mode": policy.trading_mode,
            "live_trading_enabled": policy.live_trading_enabled,
            "stage": policy.stage.value,
        }

    def assert_paper_cannot_live(self, policy: LiveExecutionPolicy) -> None:
        result = self.evaluate(policy)
        if policy.trading_mode == "paper" and result["approved"]:
            raise RuntimeError("Invariant violated: paper mode approved live execution")
