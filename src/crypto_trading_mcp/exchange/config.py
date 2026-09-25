from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from crypto_trading_mcp.config.settings import REPO_ROOT
from crypto_trading_mcp.exchange.models import (
    AssetClass,
    InstrumentMeta,
    SettlementType,
    TradingHours,
)


def load_paper_config(path: Path | None = None) -> dict[str, Any]:
    """Load paper trading configuration.

    Prefers ``config/paper_trading.yaml`` when present, otherwise ``config/paper.yaml``.
    """
    if path is None:
        preferred = REPO_ROOT / "config" / "paper_trading.yaml"
        legacy = REPO_ROOT / "config" / "paper.yaml"
        path = preferred if preferred.exists() else legacy
    if not path.exists():
        return {
            "paper": {
                "initial_cash": 10000,
                "quote_currency": "USD",
                "fees": {"default_rate": 0.001, "maker_bps": 10, "taker_bps": 20},
                "slippage": {
                    "enabled": True,
                    "model": "fixed_bps",
                    "default_bps": 5,
                    "max_bps": 50,
                },
                "strategy_conflict_mode": "NO_TRADE",
                "kill_switch_file": "STOP",
                "max_consecutive_api_failures": 3,
                "timezone": "UTC",
                "flatten_at_eod": False,
            },
            "instruments": {},
            "symbol_strategy_map": {},
        }
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        return {}
    # Normalize paper_trading key into paper for callers.
    if "paper_trading" in data and "paper" not in data:
        data = {**data, "paper": data["paper_trading"]}
    return data


def instrument_catalog(config: dict[str, Any] | None = None) -> dict[str, InstrumentMeta]:
    config = config or load_paper_config()
    out: dict[str, InstrumentMeta] = {}
    for symbol, meta in (config.get("instruments") or {}).items():
        hours = meta.get("trading_hours") or {}
        out[symbol.upper()] = InstrumentMeta(
            instrument_id=meta.get("instrument_id"),
            symbol=symbol.upper(),
            asset_class=AssetClass(str(meta.get("asset_class", "CRYPTO")).upper()),
            quote_currency=str(meta.get("quote_currency", "USD")),
            tick_size=float(meta.get("tick_size", 0.01)),
            lot_size=float(meta.get("lot_size", 0.0001)),
            contract_multiplier=float(meta.get("contract_multiplier", meta.get("multiplier", 1.0))),
            multiplier=float(meta.get("multiplier", meta.get("contract_multiplier", 1.0))),
            margin_required=float(meta.get("margin_required", 0.0)),
            shortable=bool(meta.get("shortable", True)),
            trading_hours=TradingHours(
                timezone=str(hours.get("timezone", "UTC")),
                sessions=list(hours.get("sessions") or ["00:00-23:59"]),
                always_open=bool(hours.get("always_open", True)),
            ),
            settlement_type=SettlementType(
                str(meta.get("settlement_type", "CASH")).upper()
            ),
        )
    return out


def resolve_strategy_for_symbol(symbol: str, config: dict[str, Any] | None = None) -> str | None:
    config = config or load_paper_config()
    mapping = config.get("symbol_strategy_map") or {}
    sym = symbol.upper()
    if sym in mapping:
        return str(mapping[sym])
    for pattern, strategy_id in mapping.items():
        if str(pattern).endswith("/*") and sym.startswith(str(pattern)[:-1].upper()):
            return str(strategy_id)
    return None
