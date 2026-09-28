"""OKF correlation filter: block risk-on longs when correlated indices are long."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


def _norm(symbol: str) -> str:
    return symbol.replace("-", "/").replace("_", "/").upper()


class OKFCorrelationGate:
    """Deterministic portfolio correlation rule from OKF guidelines."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        risk_on_assets: Sequence[str] | None = None,
        correlated_long_blockers: Sequence[str] | None = None,
        fail_closed_when_unavailable: bool = True,
    ) -> None:
        self.enabled = enabled
        self.risk_on_assets = {_norm(a) for a in (risk_on_assets or [])}
        self.correlated_long_blockers = {
            _norm(a) for a in (correlated_long_blockers or [])
        }
        self.fail_closed_when_unavailable = fail_closed_when_unavailable

    def is_risk_on(self, symbol: str) -> bool:
        sym = _norm(symbol)
        candidates = {
            sym,
            sym.replace("/", ""),
            sym.replace("/", "-"),
        }
        for asset in self.risk_on_assets:
            ac = {asset, asset.replace("/", ""), asset.replace("/", "-")}
            if candidates & ac:
                return True
        return False

    def evaluate(
        self,
        *,
        symbol: str,
        side: str,
        open_positions: Mapping[str, float] | None,
        correlation_data_available: bool = True,
        is_new_entry: bool = True,
        is_position_modification: bool = False,
    ) -> dict[str, Any]:
        """Return allow/block decision.

        open_positions: symbol -> signed quantity (positive = long).
        """
        if not self.enabled:
            return {
                "allowed": True,
                "reason_code": "CORRELATION_FILTER_DISABLED",
                "matched_blockers": [],
            }

        side_u = side.upper()
        # Shorts are not blocked by this OKF rule.
        if side_u in {"SHORT", "SELL"}:
            return {
                "allowed": True,
                "reason_code": "CORRELATION_NOT_APPLICABLE_SHORT",
                "matched_blockers": [],
            }

        # Position modifications (reduce/add to existing) are not new risk-on entries.
        if is_position_modification or not is_new_entry:
            return {
                "allowed": True,
                "reason_code": "CORRELATION_NOT_APPLICABLE_MODIFICATION",
                "matched_blockers": [],
            }

        if not self.is_risk_on(symbol):
            return {
                "allowed": True,
                "reason_code": "CORRELATION_NOT_RISK_ON_ASSET",
                "matched_blockers": [],
            }

        if not correlation_data_available or open_positions is None:
            if self.fail_closed_when_unavailable:
                return {
                    "allowed": False,
                    "reason_code": "CORRELATION_DATA_UNAVAILABLE",
                    "matched_blockers": [],
                    "fail_closed": True,
                }
            return {
                "allowed": True,
                "reason_code": "CORRELATION_DATA_UNAVAILABLE_FAIL_OPEN",
                "matched_blockers": [],
                "fail_closed": False,
            }

        longs = {
            _norm(sym): qty
            for sym, qty in open_positions.items()
            if float(qty) > 0
        }
        matched = [
            blocker
            for blocker in sorted(self.correlated_long_blockers)
            if any(
                _norm(sym) == blocker
                or _norm(sym).replace("/", "") == blocker.replace("/", "")
                for sym in longs
            )
        ]

        # OKF rule: block when correlated index assets are *both* currently long.
        required = sorted(self.correlated_long_blockers)
        if required and set(matched) >= set(required):
            return {
                "allowed": False,
                "reason_code": "CORRELATION_FILTER_BLOCK",
                "matched_blockers": matched,
                "rule": (
                    "Block new long entries on risk-on assets when all configured "
                    "correlated long blockers are currently long."
                ),
                "llm_can_override": False,
            }

        return {
            "allowed": True,
            "reason_code": "CORRELATION_OK",
            "matched_blockers": matched,
        }
