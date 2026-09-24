from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

SlippageModel = Literal["fixed_bps", "percentage", "volatility_adjusted", "volume_adjusted"]


@dataclass(frozen=True)
class SlippageResult:
    fill_price: float
    slippage_abs: float
    slippage_bps: float
    model: str
    enabled: bool


class SlippageEngine:
    """Configurable simulated slippage. Records exact slippage for every fill."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = dict(config or {})
        self.enabled = bool(cfg.get("enabled", True))
        # Support both spec keys (model/default_bps) and legacy (mode/value).
        model = str(cfg.get("model") or cfg.get("mode") or "fixed_bps").lower()
        if model == "fixed":
            model = "fixed_bps"
        self.model: str = model
        self.default_bps = float(cfg.get("default_bps", cfg.get("value", 5)))
        self.max_bps = float(cfg.get("max_bps", 50))
        self.percentage = float(cfg.get("percentage", self.default_bps / 10_000.0))
        self.volatility_multiplier = float(cfg.get("volatility_multiplier", 1.0))
        self.volume_impact = float(cfg.get("volume_impact", 0.0))

    @classmethod
    def from_paper_config(cls, paper_cfg: dict[str, Any] | None) -> SlippageEngine:
        slip = (paper_cfg or {}).get("slippage") or {}
        return cls(slip if isinstance(slip, dict) else {})

    def _bps(
        self,
        *,
        volatility: float | None = None,
        trade_qty: float | None = None,
        adv: float | None = None,
    ) -> float:
        if not self.enabled:
            return 0.0
        if self.model == "percentage":
            bps = self.percentage * 10_000.0
        elif self.model == "volatility_adjusted":
            vol = float(volatility if volatility is not None else 0.01)
            bps = self.default_bps * (1.0 + abs(vol) * self.volatility_multiplier)
        elif self.model == "volume_adjusted":
            qty = float(trade_qty or 0.0)
            average_daily = float(adv or 1.0)
            participation = qty / average_daily if average_daily > 0 else 0.0
            bps = self.default_bps * (1.0 + participation * self.volume_impact)
        else:
            bps = self.default_bps
        return min(max(bps, 0.0), self.max_bps)

    def apply(
        self,
        *,
        side: str,
        market_price: float,
        prediction: bool = False,
        volatility: float | None = None,
        trade_qty: float | None = None,
        adv: float | None = None,
    ) -> SlippageResult:
        bps = self._bps(volatility=volatility, trade_qty=trade_qty, adv=adv)
        slip = market_price * (bps / 10_000.0)
        side_u = side.upper()
        is_buy = side_u in {"BUY", "BUY_YES", "BUY_NO", "LONG"}
        if is_buy:
            fill = market_price + slip
        else:
            fill = market_price - slip
        if prediction:
            fill = min(1.0, max(0.0, fill))
        return SlippageResult(
            fill_price=fill,
            slippage_abs=abs(fill - market_price),
            slippage_bps=bps,
            model=self.model if self.enabled else "disabled",
            enabled=self.enabled,
        )
