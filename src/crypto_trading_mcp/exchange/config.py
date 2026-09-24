from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from crypto_trading_mcp.config.settings import REPO_ROOT
from crypto_trading_mcp.exchange.models import AssetClass, InstrumentMeta


def load_paper_config(path: Path | None = None) -> dict[str, Any]:
    path = path or (REPO_ROOT / "config" / "paper.yaml")
    if not path.exists():
        return {
            "paper": {
                "initial_cash": 10000,
                "quote_currency": "USD",
                "fees": {"default_rate": 0.001},
                "slippage": {"mode": "fixed_bps", "value": 5},
                "strategy_conflict_mode": "NO_TRADE",
                "kill_switch_file": "STOP",
                "max_consecutive_api_failures": 3,
                "timezone": "UTC",
            },
            "instruments": {},
            "symbol_strategy_map": {},
        }
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data if isinstance(data, dict) else {}


def instrument_catalog(config: dict[str, Any] | None = None) -> dict[str, InstrumentMeta]:
    config = config or load_paper_config()
    out: dict[str, InstrumentMeta] = {}
    for symbol, meta in (config.get("instruments") or {}).items():
        out[symbol.upper()] = InstrumentMeta(
            symbol=symbol.upper(),
            asset_class=AssetClass(str(meta.get("asset_class", "CRYPTO")).upper()),
            tick_size=float(meta.get("tick_size", 0.01)),
            lot_size=float(meta.get("lot_size", 0.0001)),
            multiplier=float(meta.get("multiplier", 1.0)),
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
