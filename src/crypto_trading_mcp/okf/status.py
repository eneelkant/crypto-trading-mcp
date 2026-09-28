"""OKF diagnostics for status endpoints and paper-run metadata."""

from __future__ import annotations

from typing import Any

from crypto_trading_mcp.okf.loader import load_and_validate_okf
from crypto_trading_mcp.okf.resolver import OKFConfigResolver
from crypto_trading_mcp.risk.config import load_risk_config


def xgboost_availability() -> dict[str, Any]:
    try:
        import xgboost  # noqa: F401

        return {"available": True, "reported_as_active": False, "note": "Installed; activation requires training path."}
    except Exception:
        return {
            "available": False,
            "reported_as_active": False,
            "fallback": "logistic_or_random_forest",
            "note": "XGBoost unavailable; existing Phase 8 fallback models retained.",
        }


def okf_diagnostics() -> dict[str, Any]:
    loaded = load_and_validate_okf()
    system = load_risk_config().risk
    resolved = OKFConfigResolver(loaded).resolve(system)
    xgb = xgboost_availability()
    return {
        "ok": True,
        "version": loaded["version"],
        "hash": loaded["hash"],
        "bundle_name": loaded["bundle_name"],
        "path": loaded["path"],
        "executable": False,
        "status": loaded["data"]["okf_specification"].get("status"),
        "resolved": resolved.to_dict(),
        "ml": {
            "okf_model": resolved.ml_model,
            "features": resolved.ml_features,
            "optional": resolved.ml_optional,
            "xgboost": xgb,
            "evaluation": "Out-of-Sample Walk-Forward Validation",
            "in_sample_not_production_proof": True,
        },
        "tax_reference": resolved.tax_reference,
        "delta_exchange": {
            "okf_production_reference_url": resolved.exchange_base_url,
            "auth_type": resolved.exchange_auth_type,
            "max_clock_skew_seconds": resolved.max_clock_skew_seconds,
            "rate_limit_units_per_5min": resolved.rate_limit_units_per_5min,
            "production_trading_enabled": False,
            "stage2_uses_testnet_sandbox": True,
            "note": "OKF production URL is reference only; Stage 2 remains testnet/harness.",
        },
        "hierarchy": [
            "HARD_SYSTEM_SAFETY",
            "LIVE_TRADING_STAGE_GATES",
            "KILL_SWITCH",
            "EXCHANGE_VALIDATION",
            "RECONCILIATION",
            "DETERMINISTIC_RISK_ENGINE",
            "OKF_STRATEGY_CONSTRAINTS",
            "AGENT_LLM_PROPOSAL",
            "TRADE_PLAN",
            "EXECUTION_POLICY",
        ],
        "LIVE_TRADING_ENABLED": False,
        "TRADING_MODE": "paper",
    }


def okf_paper_metadata() -> dict[str, Any]:
    diag = okf_diagnostics()
    return {
        "okf_version": diag["version"],
        "okf_hash": diag["hash"],
        "okf_bundle": diag["bundle_name"],
        "okf_executable": False,
    }
