from __future__ import annotations

from typing import Any, Sequence

from crypto_trading_mcp.backtest.models import NormalizedCandle
from crypto_trading_mcp.learning.audit import LearningAuditLog
from crypto_trading_mcp.learning.calibration import CalibrationTracker
from crypto_trading_mcp.learning.champion_challenger import evaluate_challenger
from crypto_trading_mcp.learning.config import LearningConfig, load_learning_config
from crypto_trading_mcp.learning.drift import DriftMonitor
from crypto_trading_mcp.learning.features import extract_features
from crypto_trading_mcp.learning.kelly import bounded_kelly_multiplier
from crypto_trading_mcp.learning.memory import LearningMemory
from crypto_trading_mcp.learning.models import (
    LearningProposal,
    MarketRegime,
    ProposalStatus,
    TradeLearningRecord,
    TradeOutcome,
)
from crypto_trading_mcp.learning.post_mortem import run_post_mortem
from crypto_trading_mcp.learning.proposals import ProposalStore
from crypto_trading_mcp.learning.reflection import ReflectionEngine
from crypto_trading_mcp.learning.regime import detect_regime
from crypto_trading_mcp.learning.retraining import RetrainingEngine
from crypto_trading_mcp.learning.rollback import RollbackManager
from crypto_trading_mcp.learning.scheduler import LearningScheduler
from crypto_trading_mcp.learning.validation import validate_proposal
from crypto_trading_mcp.learning.versioning import ModelVersionRegistry


class LearningEngine:
    """Self-learning infrastructure subordinate to deterministic RiskEngine."""

    def __init__(
        self,
        config: LearningConfig | None = None,
        store: Any | None = None,
        event_bus: Any | None = None,
    ) -> None:
        self.config = config or load_learning_config()
        self.config.assert_safety()
        self.store = store
        self.bus = event_bus
        self.memory = LearningMemory(self.config, store=store)
        self.calibration = CalibrationTracker(self.config)
        self.drift = DriftMonitor(self.config)
        self.registry = ModelVersionRegistry()
        self.proposals = ProposalStore()
        self.reflection = ReflectionEngine()
        self.retraining = RetrainingEngine(self.config, self.registry)
        self.rollback = RollbackManager(self.registry, self.proposals)
        self.audit = LearningAuditLog()
        self.scheduler = LearningScheduler()
        self.reflections: list[dict[str, Any]] = []
        self.post_mortems: list[dict[str, Any]] = []
        self.trades_processed = 0
        self.kelly_multiplier = self.config.kelly_base_fraction
        self._emit("LEARNING_STARTED", {"enabled": self.config.enabled})

    def _emit(self, event_type: str, payload: dict[str, Any], **kwargs: Any) -> None:
        self.audit.record(event_type, evidence=payload, **{
            k: kwargs.get(k) for k in ("trade_id", "model", "strategy", "proposal", "decision") if k in kwargs
        })
        if self.bus is None:
            return
        try:
            # Prefer EventType enum values when available
            from crypto_trading_mcp.dashboard.events import EventType

            et = getattr(EventType, event_type, None) or event_type
            self.bus.emit(et, payload=payload, **{k: v for k, v in kwargs.items() if k in {"symbol", "agent_id", "run_id"}})
        except Exception:
            try:
                self.bus.emit(event_type, payload=payload)
            except Exception:
                return

    def status(self) -> dict[str, Any]:
        champ = self.registry.champion()
        chall = self.registry.challenger()
        latest_ref = self.reflections[-1] if self.reflections else None
        return {
            "enabled": self.config.enabled,
            "trades_processed": self.trades_processed,
            "learning_records": len(self.memory.records),
            "failures": len(self.memory.failures()),
            "successes": len(self.memory.successes()),
            "champion": None if champ is None else champ.model_version,
            "challenger": None if chall is None else chall.model_version,
            "latest_reflection": latest_ref,
            "next_retraining_in": max(
                0, self.config.interval_trades - (self.trades_processed - self.retraining.last_trained_at_count)
            ),
            "calibration": self.calibration.status(),
            "drift": self.drift.status(),
            "kelly_multiplier": self.kelly_multiplier,
            "safety": {
                "automatic_live_deployment": False,
                "learning_can_modify_hard_risk_limits": False,
                "learning_can_disable_kill_switch": False,
                "learning_can_create_exchange_orders": False,
                "LIVE_TRADING_ENABLED": False,
                "TRADING_MODE": "paper",
            },
        }

    def detect_market_regime(self, candles: Sequence[NormalizedCandle]) -> MarketRegime:
        regime = detect_regime(candles) if self.config.regime_enabled else MarketRegime.UNKNOWN
        self._emit("REGIME_DETECTED", {"regime": regime.value})
        return regime

    def learning_context_for(
        self, candles: Sequence[NormalizedCandle] | None = None, features: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        try:
            feats = features or (extract_features(candles or []) if candles else {})
            regime = MarketRegime.UNKNOWN
            if candles:
                regime = self.detect_market_regime(candles)
            cal = self.calibration.status()
            drift = self.drift.status()
            ctx = self.memory.search(
                feats,
                regime=regime,
                brier_status=cal.get("status", "UNKNOWN"),
                drift_status="DRIFT" if not drift.get("ok", True) else "OK",
            )
            self._emit("MEMORY_RETRIEVAL_COMPLETED", ctx.to_dict())
            self._emit("LEARNING_CONTEXT_READY", ctx.to_dict())
            return ctx.to_dict()
        except Exception:
            # Failure-safe: continue without memory
            return {
                "similar_case_count": 0,
                "recommended_caution": False,
                "brier_status": "UNAVAILABLE",
                "drift_status": "UNAVAILABLE",
                "failure_safe": True,
            }

    def kelly_adapt(
        self, win_probability: float, payoff_ratio: float = 1.5
    ) -> dict[str, float | bool]:
        degraded = self.calibration.status().get("status") == "DEGRADED"
        result = bounded_kelly_multiplier(
            win_probability=win_probability,
            payoff_ratio=payoff_ratio,
            config=self.config,
            calibration_degraded=degraded,
        )
        self.kelly_multiplier = float(result["kelly_multiplier"])
        self._emit("KELLY_ADAPTED", dict(result))
        return result

    def on_trade_close(self, record: TradeLearningRecord, async_mode: bool = False) -> dict[str, Any]:
        if not self.config.enabled:
            return {"skipped": True}

        def _run() -> dict[str, Any]:
            return self._process_closed_trade(record)

        if async_mode:
            self.scheduler.submit(lambda: _run(), name=f"learn-{record.trade_id}")
            return {"scheduled": True, "trade_id": record.trade_id}
        return _run()

    def _process_closed_trade(self, record: TradeLearningRecord) -> dict[str, Any]:
        self._emit("TRADE_POSTMORTEM_STARTED", {"trade_id": record.trade_id}, trade_id=record.trade_id)
        pm = run_post_mortem(record)
        self.post_mortems.append(pm)
        self._emit("TRADE_POSTMORTEM_COMPLETED", pm, trade_id=record.trade_id)
        self._emit(
            "TRADE_CLASSIFIED",
            {
                "trade_id": record.trade_id,
                "failures": pm.get("classification", {}).get("failure_categories", []),
                "successes": pm.get("classification", {}).get("success_categories", []),
            },
            trade_id=record.trade_id,
        )

        if self.config.memory_enabled:
            self.memory.add(record)
            if record.outcome == TradeOutcome.LOSS:
                self._emit("FAILURE_MEMORY_UPDATED", {"memory_id": record.memory_id}, trade_id=record.trade_id)
            elif record.outcome == TradeOutcome.WIN:
                self._emit("SUCCESS_MEMORY_UPDATED", {"memory_id": record.memory_id}, trade_id=record.trade_id)

        outcome_bit = 1 if record.outcome == TradeOutcome.WIN else 0
        if record.predicted_probability is not None:
            cal = self.calibration.update(
                record.predicted_probability,
                outcome_bit,
                strategy_id=record.strategy_id,
                regime=record.market_regime.value,
            )
            self._emit("BRIER_UPDATED", cal, trade_id=record.trade_id)
            self._emit("CALIBRATION_UPDATED", cal, trade_id=record.trade_id)
            if cal.get("degraded"):
                self.kelly_adapt(record.predicted_probability)

        wins = len(self.memory.successes())
        total = max(1, len(self.memory.records))
        drift_events = self.drift.update(
            brier=self.calibration.status().get("brier_score"),
            winrate=wins / total,
        )
        for de in drift_events:
            self._emit("DRIFT_DETECTED", de, trade_id=record.trade_id)

        reflection_out = None
        if self.config.reflection_enabled and self.config.after_every_trade:
            self._emit("REFLECTION_STARTED", {"trade_id": record.trade_id}, trade_id=record.trade_id)
            reflection = self.reflection.reflect(record, pm)
            reflection_out = reflection.to_dict()
            self.reflections.append(reflection_out)
            self._emit("REFLECTION_COMPLETED", reflection_out, trade_id=record.trade_id)

        self.trades_processed += 1
        retrain_result = None
        if self.retraining.should_retrain(self.trades_processed):
            retrain_result = self.run_retraining(seed=42)

        proposal = None
        if record.outcome == TradeOutcome.LOSS and record.failure_categories:
            proposal = self.proposals.create(
                reason="Post-mortem suggested review",
                evidence={"trade_id": record.trade_id, "lesson": record.lesson},
                parent_version=None if self.registry.champion() is None else self.registry.champion().model_version,
                risk_analysis={"can_modify_hard_limits": False},
            )
            self._emit(
                "LEARNING_PROPOSAL_CREATED",
                proposal.to_dict(),
                proposal=proposal.proposal_id,
                trade_id=record.trade_id,
            )

        return {
            "post_mortem": pm,
            "reflection": reflection_out,
            "retraining": retrain_result,
            "proposal": None if proposal is None else proposal.to_dict(),
            "status": self.status(),
        }

    def run_retraining(self, seed: int = 42) -> dict[str, Any]:
        self._emit("RETRAINING_STARTED", {"trades": self.trades_processed})
        try:
            result = self.retraining.train(self.memory.records, seed=seed, use_walk_forward=True)
        except Exception as exc:
            # Keep champion on failure
            result = {"ok": False, "reason": "RETRAINING_FAILED", "error": str(exc)}
            self._emit("RETRAINING_COMPLETED", result)
            return result

        self._emit("RETRAINING_COMPLETED", {k: v for k, v in result.items() if k != "model"})
        if not result.get("ok"):
            return result

        version_data = result["model_version"]
        self._emit("MODEL_VERSION_CREATED", version_data, model=version_data.get("model_version"))
        challenger = self.registry.versions[-1]
        self._emit("CHALLENGER_CREATED", challenger.to_dict(), model=challenger.model_version)

        champ = self.registry.champion()
        decision = evaluate_challenger(
            challenger,
            champ,
            config=self.config,
            sample_size=int(result.get("sample_size") or 0),
            oos_return=None,
            champion_oos_return=None,
            risk_violations=0,
        )
        if decision["accepted"]:
            self._emit("CHALLENGER_VALIDATED", decision, model=challenger.model_version)
            self._emit("CHAMPION_UPDATED", challenger.to_dict(), model=challenger.model_version)
            proposal = self.proposals.create(
                reason="Challenger validated via OOS/calibration gates",
                evidence=decision,
                parent_version=None if champ is None else champ.model_version,
                candidate_version=challenger.model_version,
                status=ProposalStatus.ACCEPTED,
                risk_analysis={"can_modify_hard_limits": False},
            )
            self._emit("LEARNING_PROPOSAL_ACCEPTED", proposal.to_dict(), proposal=proposal.proposal_id)
        else:
            self._emit("CHALLENGER_REJECTED", decision, model=challenger.model_version)
            proposal = self.proposals.create(
                reason="Challenger rejected",
                evidence=decision,
                candidate_version=challenger.model_version,
                status=ProposalStatus.REJECTED,
                warning_flags=decision.get("flags") or [],
                risk_analysis={"can_modify_hard_limits": False},
            )
            self._emit("LEARNING_PROPOSAL_REJECTED", proposal.to_dict(), proposal=proposal.proposal_id)
        result["challenger_decision"] = decision
        return result

    def validate_learning(self, proposal_id: str | None = None) -> dict[str, Any]:
        if proposal_id:
            p = self.proposals.get(proposal_id)
            if p is None:
                return {"ok": False, "reason": "not_found"}
            return validate_proposal(
                p, config=self.config, sample_size=len(self.memory.records)
            )
        return {
            "ok": True,
            "champion": None if self.registry.champion() is None else self.registry.champion().to_dict(),
            "calibration": self.calibration.status(),
            "safety": self.status()["safety"],
        }

    def rollback_candidate(self, reason: str = "manual_rollback") -> dict[str, Any]:
        event = self.rollback.rollback_to_champion(reason)
        self._emit("LEARNING_ROLLBACK", event)
        return event


_ENGINE: LearningEngine | None = None


def get_learning_engine(reset: bool = False) -> LearningEngine:
    global _ENGINE
    if reset or _ENGINE is None:
        try:
            from crypto_trading_mcp.dashboard.event_bus import get_event_bus

            bus = get_event_bus()
        except Exception:
            bus = None
        _ENGINE = LearningEngine(event_bus=bus)
    return _ENGINE
