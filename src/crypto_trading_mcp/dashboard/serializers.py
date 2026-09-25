from __future__ import annotations

from typing import Any

from crypto_trading_mcp.dashboard.events import sanitize_payload


def serialize_order(order: dict[str, Any]) -> dict[str, Any]:
    return sanitize_payload(order)


def serialize_trade(trade: dict[str, Any]) -> dict[str, Any]:
    return sanitize_payload(trade)


def serialize_backtest_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return sanitize_payload(payload)
