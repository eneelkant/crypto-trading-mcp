from __future__ import annotations

from crypto_trading_mcp.backtest.data import generate_synthetic_candles
from crypto_trading_mcp.learning.brier import rolling_brier
from crypto_trading_mcp.learning.calibration import CalibrationTracker
from crypto_trading_mcp.learning.champion_challenger import evaluate_challenger
from crypto_trading_mcp.learning.config import LearningConfig, load_learning_config
from crypto_trading_mcp.learning.embeddings import cosine_similarity, embed_features
from crypto_trading_mcp.learning.engine import LearningEngine
from crypto_trading_mcp.learning.features import extract_features, feature_vector
from crypto_trading_mcp.learning.kelly import bounded_kelly_multiplier, kelly_fraction
from crypto_trading_mcp.learning.models import (
    FailureCategory,
    MarketRegime,
    ModelVersion,
    TradeLearningRecord,
    TradeOutcome,
)
from crypto_trading_mcp.learning.post_mortem import run_post_mortem
from crypto_trading_mcp.learning.regime import detect_regime
from crypto_trading_mcp.learning.versioning import ModelVersionRegistry


def test_brier_and_calibration():
    pairs = [(0.8, 1), (0.2, 0), (0.9, 0)]
    score = rolling_brier(pairs)
    assert score is not None and score > 0
    cfg = LearningConfig()
    tracker = CalibrationTracker(cfg)
    out = tracker.update(0.9, 0)
    assert out["degraded"] or out["brier_score"] is not None


def test_kelly_bounds():
    cfg = LearningConfig()
    full = kelly_fraction(0.6, 2.0)
    assert full > 0
    result = bounded_kelly_multiplier(
        win_probability=0.6, payoff_ratio=2.0, config=cfg, calibration_degraded=True
    )
    assert result["kelly_multiplier"] <= cfg.kelly_max_multiplier
    assert result["kelly_multiplier"] >= cfg.kelly_min_multiplier
    assert result["can_override_risk_limits"] is False


def test_regime_and_features():
    candles = generate_synthetic_candles(symbol="BTC/USD", n=80, seed=7)
    regime = detect_regime(candles)
    assert isinstance(regime, MarketRegime)
    feats = extract_features(candles)
    assert "RSI_14" in feats
    vec = feature_vector(feats)
    assert len(vec) >= 10


def test_post_mortem_classification_not_all_losses_are_strategy_failures():
    rec = TradeLearningRecord(
        trade_id="T1",
        symbol="BTC/USD",
        net_pnl=-1.0,
        predicted_probability=0.4,
        slippage=0.0,
        entry_price=100.0,
        execution_quality="GOOD",
    )
    pm = run_post_mortem(rec)
    cats = pm["classification"]["failure_categories"]
    assert "NORMAL_VARIANCE" in cats or "BAD_PREDICTION" not in cats or FailureCategory.NORMAL_VARIANCE.value in cats


def test_similarity_retrieval_does_not_veto():
    eng = LearningEngine(config=LearningConfig())
    candles = generate_synthetic_candles(symbol="BTC/USD", n=60, seed=3)
    feats = extract_features(candles)
    for i in range(3):
        eng.memory.add(
            TradeLearningRecord(
                trade_id=f"F{i}",
                symbol="BTC/USD",
                features={k: v for k, v in feats.items() if not isinstance(v, str)},
                net_pnl=-1.0,
                outcome=TradeOutcome.LOSS,
                failure_categories=[FailureCategory.BAD_PREDICTION],
                predicted_probability=0.7,
            )
        )
    ctx = eng.learning_context_for(features=feats)
    assert "recommended_caution" in ctx
    # caution is advisory — never an automatic abort flag named veto
    assert "auto_abort" not in ctx
    assert ctx.get("failure_safe") is not True or ctx["similar_case_count"] >= 0


def test_champion_challenger_rejects_bad_calibration():
    cfg = LearningConfig(min_sample_size=5)
    registry = ModelVersionRegistry()
    champ = registry.register(
        training_dataset_hash="a",
        feature_hash="b",
        configuration_hash="c",
        brier_score=0.1,
        champion=True,
    )
    chall = registry.register(
        training_dataset_hash="d",
        feature_hash="e",
        configuration_hash="f",
        brier_score=0.5,
    )
    decision = evaluate_challenger(chall, champ, config=cfg, sample_size=50)
    assert decision["accepted"] is False


def test_learning_config_safety_defaults():
    cfg = load_learning_config()
    assert cfg.automatic_live_deployment is False
    assert cfg.learning_can_modify_hard_risk_limits is False
    cfg.assert_safety()


def test_learning_loop_on_trade_close():
    eng = LearningEngine(config=LearningConfig(interval_trades=10_000))
    candles = generate_synthetic_candles(symbol="ETH/USD", n=50, seed=11)
    feats = extract_features(candles)
    rec = TradeLearningRecord(
        trade_id="CLOSE1",
        symbol="ETH/USD",
        strategy_id="momentum_breakout_crypto",
        features={k: v for k, v in feats.items() if not isinstance(v, str)},
        market_regime=detect_regime(candles),
        entry_price=100,
        exit_price=105,
        quantity=1,
        net_pnl=4.5,
        predicted_probability=0.65,
        execution_quality="GOOD",
    )
    out = eng.on_trade_close(rec)
    assert out["post_mortem"]["outcome"] == "WIN"
    assert eng.trades_processed == 1
    assert eng.calibration.status()["prediction_count"] == 1


def test_embeddings_deterministic():
    a = embed_features([1.0, 2.0, 3.0])
    b = embed_features([1.0, 2.0, 3.0])
    assert a == b
    assert cosine_similarity(a, b) > 0.99


def test_rollback_keeps_audit():
    eng = LearningEngine(config=LearningConfig())
    eng.registry.register(
        training_dataset_hash="x",
        feature_hash="y",
        configuration_hash="z",
        champion=True,
    )
    eng.proposals.create(reason="test", evidence={})
    event = eng.rollback_candidate("test")
    assert event["action"] == "ROLLBACK"
    assert len(eng.audit.list()) >= 1
