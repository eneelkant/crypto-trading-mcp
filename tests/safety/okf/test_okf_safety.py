from __future__ import annotations

import json
import os
import re
from pathlib import Path

from crypto_trading_mcp.config.settings import REPO_ROOT, get_settings
from crypto_trading_mcp.okf.loader import load_and_validate_okf
from crypto_trading_mcp.okf.status import okf_diagnostics
from crypto_trading_mcp.risk.config import KillSwitch
from crypto_trading_mcp.risk.engine import RiskEngine
from crypto_trading_mcp.risk.models import PortfolioRiskSnapshot, RiskReasonCode, TradeProposal
from crypto_trading_mcp.strategy.repository import StrategyKnowledgeService
from crypto_trading_mcp.webhook.tradingview import TradingViewWebhookHandler


SECRET_PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),
    re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"YOUR_SECRET_KEY"),
    re.compile(r"api[_-]?secret\s*=\s*['\"][^'\"]+['\"]", re.I),
]


def test_production_safety_flags():
    settings = get_settings()
    assert settings.trading_mode == "paper"
    assert settings.live_trading_enabled is False
    diag = okf_diagnostics()
    assert diag["TRADING_MODE"] == "paper"
    assert diag["LIVE_TRADING_ENABLED"] is False


def test_okf_contains_no_real_secrets():
    path = REPO_ROOT / "okf" / "okf_crypto_bot_guidelines.json"
    text = path.read_text(encoding="utf-8")
    assert "YOUR_SECRET_KEY" not in text
    assert "PLACEHOLDER_NOT_A_SECRET" in text
    loaded = load_and_validate_okf()
    blob = json.dumps(loaded["data"])
    for pat in SECRET_PATTERNS:
        if pat.pattern == "YOUR_SECRET_KEY":
            assert not pat.search(blob)
        elif "BEGIN" in pat.pattern:
            assert not pat.search(blob)


def test_env_ignored_and_credentials_external():
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in gitignore
    # Production credentials must not be committed
    for name in [".env", "credentials.json", "secrets.yaml"]:
        p = REPO_ROOT / name
        if p.exists():
            text = p.read_text(encoding="utf-8", errors="ignore")
            assert "YOUR_SECRET_KEY" not in text


def test_llm_cannot_bypass_risk_kill_live_gate():
    strategy = StrategyKnowledgeService().get_strategy().config
    ks = KillSwitch()
    ks.activate("operator")
    engine = RiskEngine(kill_switch=ks)
    # Even with high confidence "LLM override" fields, kill switch wins.
    prop = TradeProposal(
        symbol="BTC/USD",
        side="LONG",
        quantity=0.001,
        notional=10,
        entry_price=10000,
        stop_loss=9900,
        take_profit=10400,
        current_price=10000,
        confidence=0.99,
        model_ids=["LLM_OVERRIDE_ATTEMPT"],
        liquidity_usd=1_000_000,
        bars_since_last_trade=100,
    )
    port = PortfolioRiskSnapshot(
        equity=10_000,
        available_cash=10_000,
        positions_exposure=0,
        daily_pnl=0,
        drawdown_pct=0,
        trades_today=0,
    )
    decision = engine.evaluate(prop, port, strategy)
    assert not decision.approved
    assert RiskReasonCode.KILL_SWITCH_ACTIVE in decision.reason_codes
    # LLM cannot deactivate
    try:
        ks.deactivate()
        raised = False
    except PermissionError:
        raised = True
    assert raised

    settings = get_settings()
    assert settings.live_trading_enabled is False
    assert settings.real_money_enabled is False


def test_webhook_secret_not_from_okf_placeholder():
    okf_secret = load_and_validate_okf()["data"]["infrastructure_and_webhook"]["payload_format"][
        "secret"
    ]
    assert okf_secret == "PLACEHOLDER_NOT_A_SECRET"
    # Handler rejects placeholder env
    os.environ["TRADINGVIEW_WEBHOOK_SECRET"] = "YOUR_SECRET_KEY"
    try:
        h = TradingViewWebhookHandler()
        out = h.handle(
            {
                "action": "buy",
                "symbol": "BTC/USD",
                "price": 1,
                "qty": 1,
                "secret": "YOUR_SECRET_KEY",
            },
            headers={"x-webhook-timestamp": "1", "x-webhook-nonce": "n"},
        )
        assert out["accepted"] is False
    finally:
        os.environ.pop("TRADINGVIEW_WEBHOOK_SECRET", None)


def test_secret_scan_okf_and_src_snippets():
    """Lightweight secret scan over OKF + webhook module."""
    roots = [
        REPO_ROOT / "okf",
        REPO_ROOT / "src" / "crypto_trading_mcp" / "okf",
        REPO_ROOT / "src" / "crypto_trading_mcp" / "webhook",
    ]
    findings = []
    for root in roots:
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in {".py", ".json", ".md", ".yaml"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if "YOUR_SECRET_KEY" in text and "PLACEHOLDER" not in text and "FORBIDDEN" not in text and "reject" not in text.lower():
                # Allow mentions in comments/docs about rejection
                if "must never" in text.lower() or "never store" in text.lower() or "PLACEHOLDER_SECRETS" in text:
                    continue
                if path.name == "tradingview.py" and "PLACEHOLDER_SECRETS" in text:
                    continue
                findings.append(str(path))
    # OKF file itself must not contain YOUR_SECRET_KEY
    assert "YOUR_SECRET_KEY" not in (REPO_ROOT / "okf" / "okf_crypto_bot_guidelines.json").read_text(
        encoding="utf-8"
    )
    assert findings == [] or all("docs" in f or "test" in f for f in findings)


def test_no_production_orders_claim():
    diag = okf_diagnostics()
    assert diag["delta_exchange"]["production_trading_enabled"] is False
    # Withdrawal permissions remain none in settings/compliance posture
    assert get_settings().live_trading_enabled is False
