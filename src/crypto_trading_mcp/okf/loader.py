from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

from crypto_trading_mcp.config.settings import REPO_ROOT

DEFAULT_OKF_PATH = REPO_ROOT / "okf" / "okf_crypto_bot_guidelines.json"

REQUIRED_TOP = {
    "okf_specification",
    "regulatory_and_tax_compliance",
    "risk_management_citadel",
    "self_learning_agent_framework",
    "trading_models_and_strategies",
    "infrastructure_and_webhook",
}

REQUIRED_STRATEGY_IDS = {
    "M1_PO3_SWEEP",
    "M2_VWAP_RECLAIM",
    "M3_ICT_FVG_SWING",
    "M4_PREDICTION_MARKET_AI",
    "M5_MOMENTUM_BREAKOUT",
}

FORBIDDEN_SECRET_VALUES = {
    "YOUR_SECRET_KEY",
    "your_secret_key",
    "sk-live",
    "BEGIN PRIVATE KEY",
}

TIMEFRAME_RE = re.compile(
    r"^(\d+[smhdw]|[1-9]\d*[smhdw])(\s*/\s*(\d+[smhdw]|[1-9]\d*[smhdw]|HTF|LTF))*(\s+HTF|\s+LTF)*$",
    re.IGNORECASE,
)


class OKFValidationError(ValueError):
    pass


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_okf_raw(path: Path | None = None) -> tuple[dict[str, Any], str, bytes]:
    path = path or DEFAULT_OKF_PATH
    raw = path.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise OKFValidationError("OKF root must be an object")
    return data, _sha256_bytes(raw), raw


def validate_okf(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = REQUIRED_TOP - set(data)
    if missing:
        errors.append(f"missing_top_level:{sorted(missing)}")

    spec = data.get("okf_specification") or {}
    if str(spec.get("spec_version") or "") != "0.2.0":
        errors.append("unsupported_spec_version")
    if str(spec.get("status") or "").upper() != "APPROVED":
        errors.append("status_not_approved")

    risk = (data.get("risk_management_citadel") or {}).get("position_sizing") or {}
    max_risk = float(risk.get("max_risk_per_trade_percent") or 0)
    if not (0 < max_risk <= 5.0):
        errors.append("max_risk_per_trade_percent_out_of_bounds")

    breakers = (data.get("risk_management_citadel") or {}).get("hard_circuit_breakers") or {}
    dd = float(breakers.get("max_portfolio_drawdown_percent") or 0)
    daily = float(breakers.get("max_daily_loss_percent") or 0)
    if not (0 < dd <= 50):
        errors.append("max_drawdown_out_of_bounds")
    if not (0 < daily <= 50):
        errors.append("max_daily_loss_out_of_bounds")

    strategies = data.get("trading_models_and_strategies") or []
    ids = {str(s.get("model_id")) for s in strategies if isinstance(s, dict)}
    if ids != REQUIRED_STRATEGY_IDS:
        errors.append(f"strategy_ids_mismatch:{sorted(ids)}")

    for s in strategies:
        if not isinstance(s, dict):
            errors.append("strategy_not_object")
            continue
        tf = str(s.get("timeframe") or "")
        if tf and not TIMEFRAME_RE.match(tf.replace(" HTF", "").replace(" LTF", "")):
            # allow documented compound forms like "240m HTF / 15m LTF"
            if "HTF" not in tf and "LTF" not in tf and "/" not in tf:
                errors.append(f"bad_timeframe:{s.get('model_id')}")
        weights = s.get("ensemble_weights")
        if weights is not None:
            if not isinstance(weights, dict):
                errors.append("ensemble_weights_not_object")
            else:
                total = sum(float(v) for v in weights.values())
                if not math.isclose(total, 1.0, abs_tol=1e-9):
                    errors.append(f"ensemble_weights_sum:{total}")

    exch = ((data.get("regulatory_and_tax_compliance") or {}).get("exchange_api_spec") or {})
    if str(exch.get("auth_type") or "") != "HMAC-SHA256":
        errors.append("exchange_auth_type")
    if str(exch.get("target_exchange") or "") != "Delta Exchange India":
        errors.append("exchange_target")
    skew = int(exch.get("max_clock_skew_seconds") or 0)
    if skew <= 0 or skew > 60:
        errors.append("clock_skew_out_of_bounds")

    # Secret-like values
    blob = json.dumps(data)
    for bad in FORBIDDEN_SECRET_VALUES:
        if bad in blob:
            errors.append(f"forbidden_secret_like_value:{bad}")
    # webhook secret field must be placeholder-only
    secret = (
        ((data.get("infrastructure_and_webhook") or {}).get("payload_format") or {}).get("secret")
    )
    if secret and str(secret) not in {"PLACEHOLDER_NOT_A_SECRET", "{{secret}}", ""}:
        if not str(secret).startswith("{{") and "PLACEHOLDER" not in str(secret).upper():
            errors.append("webhook_secret_not_placeholder")

    features = (
        ((data.get("self_learning_agent_framework") or {}).get("machine_learning") or {}).get(
            "features"
        )
        or []
    )
    required_feats = {
        "RSI_14",
        "MACD_HISTOGRAM",
        "VWAP_DISTANCE",
        "BOLLINGER_BAND_WIDTH",
        "VOLUME_BREAKOUT_MULT",
    }
    if set(features) < required_feats:
        errors.append("ml_features_incomplete")

    return errors


def load_and_validate_okf(path: Path | None = None) -> dict[str, Any]:
    data, digest, _raw = load_okf_raw(path)
    errors = validate_okf(data)
    if errors:
        raise OKFValidationError(";".join(errors))
    return {
        "ok": True,
        "data": data,
        "version": data["okf_specification"]["spec_version"],
        "bundle_name": data["okf_specification"]["bundle_name"],
        "hash": digest,
        "path": str(path or DEFAULT_OKF_PATH),
        "executable": False,
        "note": "OKF is a guideline specification; it cannot directly execute trades.",
    }
