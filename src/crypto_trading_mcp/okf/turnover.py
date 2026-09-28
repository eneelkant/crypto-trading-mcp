"""Low-turnover guard wired to OKF + existing trade-frequency controls."""

from __future__ import annotations

from typing import Any


class LowTurnoverGuard:
    """Favor swing / momentum / high-conviction; block uncontrolled scalping styles.

    Connects OKF low-turnover requirement to existing max_trades_per_day and
    cooldown_bars controls. Defaults conservatively.
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        max_trades_per_day: int = 8,
        min_cooldown_bars: int = 5,
        preferred_styles: list[str] | None = None,
        forbidden_styles: list[str] | None = None,
    ) -> None:
        self.enabled = enabled
        self.max_trades_per_day = max_trades_per_day
        self.min_cooldown_bars = min_cooldown_bars
        self.preferred_styles = {
            s.lower() for s in (preferred_styles or ["swing", "momentum", "high_conviction"])
        }
        self.forbidden_styles = {
            s.lower()
            for s in (
                forbidden_styles
                or ["uncontrolled_scalping", "high_frequency_scalping"]
            )
        }

    def evaluate(
        self,
        *,
        trades_today: int,
        bars_since_last_trade: int | None,
        strategy_style: str | None = None,
    ) -> dict[str, Any]:
        if not self.enabled:
            return {"allowed": True, "reason_code": "LOW_TURNOVER_DISABLED"}

        style = (strategy_style or "").lower().strip()
        if style and style in self.forbidden_styles:
            return {
                "allowed": False,
                "reason_code": "LOW_TURNOVER_FORBIDDEN_STYLE",
                "style": style,
                "llm_can_override": False,
            }

        if trades_today >= self.max_trades_per_day:
            return {
                "allowed": False,
                "reason_code": "LOW_TURNOVER_TRADE_CAP",
                "trades_today": trades_today,
                "cap": self.max_trades_per_day,
                "llm_can_override": False,
            }

        if (
            bars_since_last_trade is not None
            and self.min_cooldown_bars > 0
            and bars_since_last_trade < self.min_cooldown_bars
        ):
            return {
                "allowed": False,
                "reason_code": "LOW_TURNOVER_COOLDOWN",
                "bars_since_last_trade": bars_since_last_trade,
                "min_cooldown_bars": self.min_cooldown_bars,
                "llm_can_override": False,
            }

        return {
            "allowed": True,
            "reason_code": "LOW_TURNOVER_OK",
            "preferred_styles": sorted(self.preferred_styles),
            "cap": self.max_trades_per_day,
            "min_cooldown_bars": self.min_cooldown_bars,
        }
