from __future__ import annotations

from typing import Any, Mapping

from crypto_trading_mcp.risk.config import (
    KillSwitch,
    load_risk_config,
    merge_effective_limits,
    pair_allowed,
)
from crypto_trading_mcp.risk.models import (
    PortfolioRiskSnapshot,
    RiskDecision,
    RiskReasonCode,
    TradeProposal,
)
from crypto_trading_mcp.strategy.schema import StrategyConfig


class RiskEngine:
    """Deterministic risk boundary. LLMs cannot override limits."""

    def __init__(
        self,
        *,
        kill_switch: KillSwitch | None = None,
        risk_config_path=None,
        apply_okf: bool = True,
    ) -> None:
        self.config = load_risk_config(risk_config_path)
        self.kill_switch = kill_switch or KillSwitch(self.config.kill_switch)
        self.apply_okf = apply_okf
        self._okf_resolved: dict[str, Any] | None = None
        if apply_okf:
            try:
                from crypto_trading_mcp.okf.resolver import OKFConfigResolver

                resolver = OKFConfigResolver()
                updated, resolved = resolver.apply_to_limits(self.config.risk)
                self._okf_resolved = resolved.to_dict()
                self.config.risk = updated
            except Exception:
                # OKF load failure must not silently weaken safety; keep system limits.
                self._okf_resolved = None

    @property
    def okf(self) -> dict[str, Any] | None:
        return self._okf_resolved

    def evaluate(
        self,
        proposal: TradeProposal,
        portfolio: PortfolioRiskSnapshot,
        strategy: StrategyConfig | None = None,
        *,
        open_positions: Mapping[str, float] | None = None,
        correlation_data_available: bool = True,
        is_new_entry: bool = True,
        is_position_modification: bool = False,
        strategy_style: str | None = None,
        memory_gate_result: dict[str, Any] | None = None,
        okf_context: dict[str, Any] | None = None,
    ) -> RiskDecision:
        okf_constraints = okf_context if okf_context is not None else self._okf_resolved
        limits = merge_effective_limits(
            self.config.risk, strategy, okf_constraints=okf_constraints
        )
        reasons: list[RiskReasonCode] = []
        warnings: list[str] = []

        if self.kill_switch.active or portfolio.kill_switch_active:
            reasons.append(RiskReasonCode.KILL_SWITCH_ACTIVE)
        if portfolio.trading_halted:
            reasons.append(RiskReasonCode.TRADING_HALTED)

        if proposal.market_data_stale:
            reasons.append(RiskReasonCode.STALE_MARKET_DATA)

        if not pair_allowed(proposal.symbol, limits["allowed_pairs"]):
            reasons.append(RiskReasonCode.PAIR_NOT_ALLOWED)

        if proposal.quantity <= 0 or proposal.notional <= 0 or proposal.entry_price <= 0:
            reasons.append(RiskReasonCode.INVALID_TRADE)

        if limits["require_stop_loss"] and proposal.stop_loss is None:
            reasons.append(RiskReasonCode.STOP_LOSS_REQUIRED)
        elif proposal.stop_loss is not None:
            if proposal.side.upper() in {"LONG", "BUY"} and proposal.stop_loss >= proposal.entry_price:
                reasons.append(RiskReasonCode.INVALID_STOP)
            if proposal.side.upper() in {"SHORT", "SELL"} and proposal.stop_loss <= proposal.entry_price:
                reasons.append(RiskReasonCode.INVALID_STOP)

        risk_amount = 0.0
        if proposal.stop_loss is not None:
            risk_per_unit = abs(proposal.entry_price - proposal.stop_loss)
            risk_amount = risk_per_unit * proposal.quantity
            if proposal.take_profit is not None and risk_per_unit > 0:
                rr = abs(proposal.take_profit - proposal.entry_price) / risk_per_unit
                if rr < limits["min_risk_reward"]:
                    reasons.append(RiskReasonCode.RISK_REWARD_TOO_LOW)

        equity = max(portfolio.equity, 0.0)
        max_position_notional = equity * limits["max_position_pct"]
        max_trade_notional = equity * limits["max_trade_pct"]
        max_risk_notional_by_stop = equity * limits["risk_per_trade_pct"]
        max_allowed_notional = min(max_position_notional, max_trade_notional)
        if proposal.entry_price > 0 and proposal.stop_loss is not None:
            stop_dist = abs(proposal.entry_price - proposal.stop_loss)
            if stop_dist > 0:
                max_qty_by_risk = max_risk_notional_by_stop / stop_dist
                max_allowed_notional = min(
                    max_allowed_notional, max_qty_by_risk * proposal.entry_price
                )

        if proposal.notional > max_position_notional + 1e-9:
            reasons.append(RiskReasonCode.POSITION_LIMIT_EXCEEDED)
        if proposal.notional > max_trade_notional + 1e-9:
            reasons.append(RiskReasonCode.TRADE_SIZE_LIMIT_EXCEEDED)

        resulting_exposure = portfolio.positions_exposure + proposal.notional
        max_exposure = equity * limits["max_portfolio_exposure_pct"]
        if resulting_exposure > max_exposure + 1e-9:
            reasons.append(RiskReasonCode.EXPOSURE_LIMIT_EXCEEDED)

        if equity > 0 and portfolio.daily_pnl < 0:
            daily_loss_pct = abs(portfolio.daily_pnl) / equity
            if daily_loss_pct >= limits["max_daily_loss_pct"]:
                reasons.append(RiskReasonCode.DAILY_LOSS_LIMIT)

        if portfolio.drawdown_pct >= limits["max_drawdown_pct"]:
            reasons.append(RiskReasonCode.DRAWDOWN_LIMIT)

        if portfolio.trades_today >= limits["max_trades_per_day"]:
            reasons.append(RiskReasonCode.TRADE_COUNT_LIMIT)

        cooldown = int(limits["cooldown_bars"])
        if (
            proposal.bars_since_last_trade is not None
            and cooldown > 0
            and proposal.bars_since_last_trade < cooldown
        ):
            reasons.append(RiskReasonCode.COOLDOWN_ACTIVE)

        if proposal.estimated_slippage_pct > limits["max_slippage_pct"]:
            reasons.append(RiskReasonCode.SLIPPAGE_LIMIT)

        if proposal.leverage > limits["max_leverage"]:
            reasons.append(RiskReasonCode.LEVERAGE_LIMIT)

        if (
            proposal.liquidity_usd is not None
            and proposal.liquidity_usd < limits["min_liquidity_usd"]
        ):
            reasons.append(RiskReasonCode.INSUFFICIENT_LIQUIDITY)

        if proposal.notional > portfolio.available_cash + 1e-9 and proposal.side.upper() in {
            "LONG",
            "BUY",
        }:
            reasons.append(RiskReasonCode.INSUFFICIENT_CASH)

        if proposal.confidence < limits["min_confidence"]:
            reasons.append(RiskReasonCode.INSUFFICIENT_CONFIDENCE)
            warnings.append("Confidence below configured minimum")

        if not proposal.model_ids:
            reasons.append(RiskReasonCode.NO_VALID_MODEL)

        if strategy is None:
            reasons.append(RiskReasonCode.STRATEGY_DATA_UNAVAILABLE)

        # --- OKF strategy constraints (below RiskEngine hard limits; above LLM) ---
        if okf_constraints:
            from crypto_trading_mcp.okf.correlation_gate import OKFCorrelationGate
            from crypto_trading_mcp.okf.turnover import LowTurnoverGuard

            # Correlation: evaluate when positions provided, or when caller
            # explicitly marks correlation data unavailable (fail closed).
            if open_positions is not None or correlation_data_available is False:
                corr = OKFCorrelationGate(
                    enabled=bool(okf_constraints.get("correlation_enabled", True)),
                    risk_on_assets=list(okf_constraints.get("risk_on_assets") or []),
                    correlated_long_blockers=list(
                        okf_constraints.get("correlated_long_blockers") or []
                    ),
                )
                corr_result = corr.evaluate(
                    symbol=proposal.symbol,
                    side=proposal.side,
                    open_positions=open_positions,
                    correlation_data_available=correlation_data_available,
                    is_new_entry=is_new_entry,
                    is_position_modification=is_position_modification,
                )
                if not corr_result.get("allowed", True):
                    code = str(corr_result.get("reason_code") or "")
                    if code == "CORRELATION_DATA_UNAVAILABLE":
                        reasons.append(RiskReasonCode.CORRELATION_DATA_UNAVAILABLE)
                    else:
                        reasons.append(RiskReasonCode.CORRELATION_FILTER_BLOCK)
                    warnings.append(code)

            turnover = LowTurnoverGuard(
                enabled=bool(okf_constraints.get("low_turnover_enabled", True)),
                max_trades_per_day=int(okf_constraints.get("max_trades_per_day", 8)),
                min_cooldown_bars=int(okf_constraints.get("cooldown_bars", 5)),
                preferred_styles=list(okf_constraints.get("preferred_styles") or []),
                forbidden_styles=list(okf_constraints.get("forbidden_styles") or []),
            )
            to_result = turnover.evaluate(
                trades_today=portfolio.trades_today,
                bars_since_last_trade=proposal.bars_since_last_trade,
                strategy_style=strategy_style,
            )
            if not to_result.get("allowed", True):
                reasons.append(RiskReasonCode.LOW_TURNOVER_BLOCK)
                warnings.append(str(to_result.get("reason_code")))

            if limits.get("okf_conflicts"):
                warnings.append(
                    f"OKF_CONFLICTS:{len(limits['okf_conflicts'])}"
                )

        if memory_gate_result is not None and not memory_gate_result.get("allowed", True):
            code = str(memory_gate_result.get("reason_code") or "")
            if "UNAVAILABLE" in code:
                reasons.append(RiskReasonCode.FAILURE_MEMORY_UNAVAILABLE)
            else:
                reasons.append(RiskReasonCode.FAILURE_MEMORY_MATCH_BLOCK)
            warnings.append(code)

        max_allowed_quantity = (
            max_allowed_notional / proposal.entry_price if proposal.entry_price > 0 else 0.0
        )
        # Filter out non-blocking informational — reasons list may include only blocks
        blocking = [r for r in reasons if r != RiskReasonCode.RISK_OK]
        approved = not blocking
        if approved:
            reasons = [RiskReasonCode.RISK_OK]

        return RiskDecision(
            approved=approved,
            reason_codes=reasons,
            warnings=warnings,
            max_allowed_quantity=max_allowed_quantity,
            max_allowed_notional=max_allowed_notional,
            risk_per_trade=risk_amount,
            portfolio_exposure=resulting_exposure,
            daily_loss=abs(min(portfolio.daily_pnl, 0.0)),
            drawdown=portfolio.drawdown_pct,
            effective_limits=limits,
        )
