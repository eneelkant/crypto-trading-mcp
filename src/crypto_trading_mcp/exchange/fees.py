from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FeeResult:
    fee: float
    rate: float
    schedule: str
    maker_bps: float
    taker_bps: float


class FeeEngine:
    """Configurable trading-fee schedules by venue and asset class.

    Prefer explicit maker/taker bps when provided. Legacy paper configs that only
    set ``default_rate`` continue to work unchanged.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = dict(config or {})
        self._raw = cfg
        self.default_rate = float(cfg.get("default_rate", 0.001))
        self.maker_bps = float(cfg.get("maker_bps", 10))
        self.taker_bps = float(cfg.get("taker_bps", 20))
        self.by_asset_class: dict[str, float] = {
            str(k).upper(): float(v) for k, v in (cfg.get("by_asset_class") or {}).items()
        }
        self.by_exchange: dict[str, dict[str, float]] = {
            str(k).lower(): {str(ik): float(iv) for ik, iv in (v or {}).items()}
            for k, v in (cfg.get("by_exchange") or {}).items()
            if isinstance(v, dict)
        }
        # When only default_rate is present (legacy paper.yaml), honor it for taker fills.
        self._legacy_default_only = (
            "default_rate" in cfg and "maker_bps" not in cfg and "taker_bps" not in cfg
        )

    @classmethod
    def from_paper_config(cls, paper_cfg: dict[str, Any] | None) -> FeeEngine:
        fees = (paper_cfg or {}).get("fees") or {}
        return cls(fees if isinstance(fees, dict) else {})

    def rate_for(
        self,
        *,
        asset_class: str = "CRYPTO",
        liquidity: str = "taker",
        exchange: str | None = None,
    ) -> tuple[float, str]:
        ac = asset_class.upper()
        liq = liquidity.lower()
        if exchange:
            venue = self.by_exchange.get(exchange.lower())
            if venue:
                if f"{liq}_bps" in venue:
                    return float(venue[f"{liq}_bps"]) / 10_000.0, f"exchange:{exchange}:{liq}"
                if "default_rate" in venue:
                    return float(venue["default_rate"]), f"exchange:{exchange}:default"
        if ac in self.by_asset_class:
            return self.by_asset_class[ac], f"asset:{ac}"
        # Prefer explicit default_rate when present (paper.yaml / paper_trading.yaml).
        if "default_rate" in self._raw:
            return self.default_rate, "default_rate"
        if liq == "maker":
            return self.maker_bps / 10_000.0, "maker"
        return self.taker_bps / 10_000.0, "taker"

    def calculate(
        self,
        *,
        notional: float,
        asset_class: str = "CRYPTO",
        liquidity: str = "taker",
        exchange: str | None = None,
    ) -> FeeResult:
        rate, schedule = self.rate_for(
            asset_class=asset_class, liquidity=liquidity, exchange=exchange
        )
        return FeeResult(
            fee=abs(float(notional)) * rate,
            rate=rate,
            schedule=schedule,
            maker_bps=self.maker_bps,
            taker_bps=self.taker_bps,
        )
