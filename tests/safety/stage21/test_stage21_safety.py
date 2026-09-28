from __future__ import annotations

from crypto_trading_mcp.ci.safety_gates import run_all_gates, scan_path_for_secrets
from crypto_trading_mcp.config.settings import get_settings
from crypto_trading_mcp.live.stages import TradingStage, TradingStageManager
from crypto_trading_mcp.sandbox.testnet_validation import run_stage21_validation


def test_stage21_production_safety_invariants():
    settings = get_settings()
    assert settings.trading_mode == "paper"
    assert settings.live_trading_enabled is False
    assert settings.real_money_enabled is False
    assert TradingStageManager().current == TradingStage.STAGE_1_LOCAL_PAPER


def test_stage21_secret_scan_clean():
    scan = scan_path_for_secrets()
    assert scan["ok"] is True
    assert scan["hits"] == []


def test_stage21_safety_gates():
    gates = run_all_gates()
    assert gates["ok"] is True


def test_stage21_report_does_not_claim_real_without_creds():
    report = run_stage21_validation(force_harness=True)
    assert report["credentials_configured"] is False or report["mode"] != "REAL_TESTNET"
    # WebSocket real path not claimed
    assert report["sections"]["websocket"]["classification"] in {
        "HARNESS/MOCK",
        "NOT_TESTED",
    }
    # Never embed secret-like values
    blob = str(report)
    assert "tn-secret" not in blob
    assert "BEGIN PRIVATE" not in blob
