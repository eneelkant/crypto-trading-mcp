from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from crypto_trading_mcp.config.settings import REPO_ROOT, get_settings
from crypto_trading_mcp.live.gate import LiveTradingGate
from crypto_trading_mcp.live.policy import LiveExecutionPolicy
from crypto_trading_mcp.live.stages import TradingStage, TradingStageManager


SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (RSA |EC )?PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(r"COINBASE_API_SECRET\s*=\s*\S+"),
    re.compile(r"DELTA_API_SECRET\s*=\s*\S+"),
]


def assert_default_safety() -> dict[str, Any]:
    settings = get_settings()
    errors: list[str] = []
    if settings.trading_mode != "paper":
        errors.append("TRADING_MODE must be paper in default CI")
    if settings.live_trading_enabled:
        errors.append("LIVE_TRADING_ENABLED must be false in default CI")
    gate = LiveTradingGate()
    result = gate.evaluate(
        LiveExecutionPolicy(
            trading_mode=settings.trading_mode,
            live_trading_enabled=settings.live_trading_enabled,
            stage=TradingStage.STAGE_1_LOCAL_PAPER,
        )
    )
    if result["approved"]:
        errors.append("LiveTradingGate approved under paper defaults")
    return {"ok": not errors, "errors": errors, "gate": result}


def assert_no_stage_skip() -> dict[str, Any]:
    mgr = TradingStageManager()
    try:
        mgr.promote(
            TradingStage.STAGE_5_CONTROLLED_LIVE,
            operator="ci",
            evidence="skip-attempt",
        )
        return {"ok": False, "errors": ["stage skip was allowed"]}
    except Exception:
        return {"ok": True, "errors": []}


def scan_path_for_secrets(root: Path | None = None) -> dict[str, Any]:
    root = root or REPO_ROOT
    hits: list[str] = []
    skip_dirs = {".git", ".venv", "node_modules", "__pycache__", ".runtime", "dist"}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in skip_dirs for part in path.parts):
            continue
        if path.suffix not in {".py", ".md", ".yaml", ".yml", ".toml", ".txt", ".env"}:
            continue
        if path.name == ".env":
            hits.append(str(path.relative_to(root)) + ": committed .env forbidden")
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for pat in SECRET_PATTERNS:
            if pat.search(text):
                # Allow documentation mentioning variable names without values
                if "API_SECRET=" in text and not re.search(
                    r"API_SECRET\s*=\s*[^\s#]+", text
                ):
                    continue
                if path.name.endswith(".example"):
                    continue
                hits.append(f"{path.relative_to(root)}: pattern {pat.pattern}")
    return {"ok": not hits, "hits": hits}


def run_all_gates() -> dict[str, Any]:
    results = {
        "default_safety": assert_default_safety(),
        "stage_skip": assert_no_stage_skip(),
        "secret_scan": scan_path_for_secrets(),
        "env_live": {
            "ok": os.getenv("LIVE_TRADING_ENABLED", "false").lower() in {"0", "false", ""},
        },
    }
    ok = all(v.get("ok", False) for v in results.values())
    return {"ok": ok, "results": results}
