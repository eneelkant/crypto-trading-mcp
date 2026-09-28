"""OKF position sizing: ATR/stop-distance and quarter-Kelly (bounded by hard risk)."""

from __future__ import annotations

from typing import Any


def atr_position_quantity(
    *,
    account_equity: float,
    risk_percent: float,
    entry_price: float,
    stop_loss_price: float | None,
    min_qty: float = 0.0,
    qty_precision: int = 8,
    max_qty: float | None = None,
) -> dict[str, Any]:
    """Position_Qty = (Equity * Risk_Percent) / abs(Entry - Stop).

    risk_percent is a fraction (e.g. 0.01 for 1%).
    """
    if stop_loss_price is None:
        return {
            "ok": False,
            "quantity": 0.0,
            "reason_code": "STOP_LOSS_REQUIRED",
            "formula": "ATR_Volatility_Based",
        }
    denom = abs(float(entry_price) - float(stop_loss_price))
    if denom <= 0:
        return {
            "ok": False,
            "quantity": 0.0,
            "reason_code": "ZERO_STOP_DISTANCE",
            "formula": "ATR_Volatility_Based",
        }
    if account_equity <= 0 or risk_percent <= 0 or entry_price <= 0:
        return {
            "ok": False,
            "quantity": 0.0,
            "reason_code": "INVALID_SIZING_INPUTS",
            "formula": "ATR_Volatility_Based",
        }
    raw = (account_equity * risk_percent) / denom
    qty = round(raw, qty_precision)
    if max_qty is not None:
        qty = min(qty, max_qty)
    if qty < min_qty:
        return {
            "ok": False,
            "quantity": 0.0,
            "reason_code": "BELOW_MIN_ORDER_SIZE",
            "raw_quantity": raw,
            "min_qty": min_qty,
            "formula": "ATR_Volatility_Based",
        }
    return {
        "ok": True,
        "quantity": qty,
        "raw_quantity": raw,
        "risk_notional": account_equity * risk_percent,
        "stop_distance": denom,
        "reason_code": "SIZING_OK",
        "formula": "ATR_Volatility_Based",
        "can_bypass_risk_engine": False,
    }


def quarter_kelly_fraction(
    *,
    p: float,
    b: float,
    kelly_multiplier: float = 0.25,
    max_fraction: float | None = None,
) -> dict[str, Any]:
    """f* = (p*b - q)/b; effective = kelly_multiplier * f*.

    Never bypasses hard portfolio/risk limits (caller must still enforce).
    """
    if b <= 0:
        return {
            "ok": False,
            "full_kelly": 0.0,
            "effective_fraction": 0.0,
            "reason_code": "INVALID_PAYOFF_RATIO",
            "can_bypass_risk_limits": False,
        }
    q = 1.0 - p
    full = max(0.0, (p * b - q) / b)
    effective = max(0.0, kelly_multiplier * full)
    if max_fraction is not None:
        effective = min(effective, max_fraction)
    return {
        "ok": True,
        "full_kelly": full,
        "kelly_multiplier": kelly_multiplier,
        "effective_fraction": effective,
        "reason_code": "KELLY_OK",
        "can_bypass_risk_limits": False,
        "method": "Quarter_Kelly_Criterion",
    }
