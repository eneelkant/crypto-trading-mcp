from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

from crypto_trading_mcp.backtest.data import generate_synthetic_candles
from crypto_trading_mcp.dashboard.event_bus import EventBus, get_event_bus
from crypto_trading_mcp.dashboard.events import EventType
from crypto_trading_mcp.dashboard.state import AgentRuntimeStatus, DashboardState, get_dashboard_state
from crypto_trading_mcp.execution.planner import TradePlan
from crypto_trading_mcp.learning.engine import get_learning_engine
from crypto_trading_mcp.learning.models import TradeLearningRecord, TradeOutcome


def run_paper_demo_cycle(
    state: DashboardState | None = None,
    bus: EventBus | None = None,
    *,
    symbol: str = "BTC/USD",
    price: float = 100.0,
) -> dict[str, Any]:
    """Deterministic end-to-end paper cycle for dashboard demonstration.

    Dashboard-only orchestration — still routes execution through PaperTradingEngine
    and RiskEngine. Never enables live trading.
    """
    state = state or get_dashboard_state()
    bus = bus or get_event_bus()
    learning = get_learning_engine()
    run_id = str(uuid4())
    symbol = symbol.upper()

    candles = generate_synthetic_candles(symbol=symbol, timeframe="1h", n=80, seed=42)
    learning_ctx = learning.learning_context_for(candles)

    pipeline = [
        (
            "market_intelligence",
            EventType.MARKET_DATA_UPDATED,
            {"regime": learning_ctx.get("regime", "TRENDING"), "confidence": 0.7, "learning_context": learning_ctx},
        ),
        ("technical_analysis", EventType.TECHNICAL_ANALYSIS_UPDATED, {"rsi": 58, "ema_alignment": True}),
        ("trend", EventType.AGENT_COMPLETED, {"decision": "BULLISH", "confidence": 0.68}),
        ("sentiment", EventType.AGENT_COMPLETED, {"decision": "NEUTRAL", "confidence": 0.55}),
        ("on_chain", EventType.AGENT_COMPLETED, {"status": "UNAVAILABLE"}),
        ("macro_event", EventType.AGENT_COMPLETED, {"event_risk": "LOW"}),
        (
            "strategy",
            EventType.STRATEGY_SIGNAL_GENERATED,
            {
                "direction": "LONG",
                "confidence": 0.71,
                "strategy": "MOMENTUM_BREAKOUT_CRYPTO",
                "reason_codes": ["DONCHIAN_BREAKOUT", "VOLUME_CONFIRMATION", "TREND_ALIGNMENT"],
                "learning_caution": learning_ctx.get("recommended_caution"),
            },
        ),
        (
            "bull",
            EventType.BULL_ANALYSIS,
            {"assessment": "BULLISH", "confidence": 0.76, "evidence": ["BREAKOUT", "VOLUME_EXPANSION"]},
        ),
        (
            "bear",
            EventType.BEAR_ANALYSIS,
            {"assessment": "CAUTIOUS", "confidence": 0.58, "risks": ["ELEVATED_VOLATILITY"]},
        ),
        (
            "consensus",
            EventType.CONSENSUS_GENERATED,
            {"decision": "BUY", "confidence": 0.70, "agreement": "2/3", "learning_context": learning_ctx},
        ),
    ]

    for agent_id, event_type, payload in pipeline:
        state.set_agent_status(agent_id, AgentRuntimeStatus.RUNNING, task=str(event_type))
        bus.emit(EventType.AGENT_STARTED, agent_id=agent_id, symbol=symbol, run_id=run_id)
        time.sleep(0)  # cooperative yield point
        bus.emit(event_type, payload=payload, agent_id=agent_id, symbol=symbol, run_id=run_id)
        state.set_agent_status(
            agent_id,
            AgentRuntimeStatus.COMPLETED,
            decision=payload,
            confidence=float(payload.get("confidence") or 0),
            duration_ms=1.0,
        )
        bus.emit(
            EventType.AGENT_COMPLETED,
            payload={"summary": payload},
            agent_id=agent_id,
            symbol=symbol,
            run_id=run_id,
        )

    # Risk
    state.set_agent_status("risk_manager", AgentRuntimeStatus.RUNNING, task="risk_check")
    bus.emit(EventType.RISK_CHECK_STARTED, agent_id="risk_manager", symbol=symbol, run_id=run_id)

    plan = TradePlan(
        strategy_id="momentum_breakout_crypto",
        strategy_version="1.0.0",
        model_ids=["DONCHIAN20"],
        symbol=symbol,
        side="LONG",
        entry_price=price,
        quantity=1.0 if price < 1000 else 0.01,
        notional=(1.0 if price < 1000 else 0.01) * price,
        stop_loss=price * 0.97,
        take_profit=price * 1.08,
        risk_amount=price * 0.03 * (1.0 if price < 1000 else 0.01),
        risk_reward_ratio=2.5,
        confidence=0.7,
        status="PROPOSED",
        confluence={"dashboard_demo": True},
    )
    bus.emit(
        EventType.TRADE_PLAN_CREATED,
        payload={"plan": plan.to_dict()},
        agent_id="trade_planner",
        symbol=symbol,
        run_id=run_id,
    )
    state.set_agent_status("trade_planner", AgentRuntimeStatus.COMPLETED, decision=plan.to_dict())

    state.paper.start()
    result = state.paper.execute_approved_plan(
        plan,
        market_price=price,
        asset_class="CRYPTO",
        analysis={
            "consensus": {"decision": "LONG", "confidence": 0.7},
            "messages": {
                "bull": {"payload": {"assessment": "BULLISH"}},
                "bear": {"payload": {"assessment": "CAUTIOUS"}},
            },
        },
    )
    approved = bool(result.get("executed"))
    if approved:
        bus.emit(
            EventType.RISK_APPROVED,
            payload={"risk": result.get("risk"), "reason_codes": ["RISK_OK"]},
            agent_id="risk_manager",
            symbol=symbol,
            run_id=run_id,
        )
        state.set_agent_status("risk_manager", AgentRuntimeStatus.COMPLETED, decision={"approved": True})
        order = result.get("order") or {}
        bus.emit(EventType.ORDER_CREATED, payload={"order_id": order.get("order_id")}, symbol=symbol, run_id=run_id)
        bus.emit(EventType.ORDER_SUBMITTED, payload=order, agent_id="execution", symbol=symbol, run_id=run_id)
        bus.emit(EventType.ORDER_FILLED, payload=order, agent_id="execution", symbol=symbol, run_id=run_id)
        state.set_agent_status("execution", AgentRuntimeStatus.COMPLETED, decision={"filled": True})
        bus.emit(EventType.POSITION_OPENED, payload={"symbol": symbol}, agent_id="portfolio_manager", run_id=run_id)
        bus.emit(EventType.PORTFOLIO_UPDATED, payload=state.portfolio_view(), run_id=run_id)
        bus.emit(EventType.PNL_UPDATED, payload={"equity": state.portfolio_view().get("equity")}, run_id=run_id)
        state.set_agent_status("portfolio_manager", AgentRuntimeStatus.COMPLETED)

        # Close trade + Phase 8 learning lifecycle
        exit_price = price * 1.04
        bus.emit(
            EventType.POSITION_CLOSED,
            payload={"symbol": symbol, "exit_price": exit_price, "net_pnl": (exit_price - price) * plan.quantity},
            agent_id="portfolio_manager",
            run_id=run_id,
            symbol=symbol,
        )
        from crypto_trading_mcp.learning.features import extract_features
        from crypto_trading_mcp.learning.regime import detect_regime

        features = extract_features(candles)
        record = TradeLearningRecord(
            trade_id=f"DEMO-{run_id[:8]}",
            strategy_id=plan.strategy_id,
            strategy_version=plan.strategy_version,
            model_id="demo",
            model_version="champion",
            symbol=symbol,
            timeframe="1h",
            market_regime=detect_regime(candles),
            features={k: v for k, v in features.items() if not isinstance(v, str)},
            side="LONG",
            entry_price=price,
            exit_price=exit_price,
            quantity=plan.quantity,
            stop_loss=plan.stop_loss,
            take_profit=plan.take_profit,
            gross_pnl=(exit_price - price) * plan.quantity,
            fees=0.01,
            slippage=0.001,
            net_pnl=(exit_price - price) * plan.quantity - 0.01,
            predicted_probability=0.70,
            consensus_confidence=0.70,
            kelly_multiplier=float(learning.kelly_adapt(0.70)["kelly_multiplier"]),
            risk_decision="APPROVED",
            execution_quality="GOOD",
            outcome=TradeOutcome.WIN,
        )
        learn_out = learning.on_trade_close(record)
        state.set_agent_status(
            "performance_judge",
            AgentRuntimeStatus.COMPLETED,
            decision={"note": "Paper metrics only", "brier": learn_out.get("post_mortem", {}).get("brier_score")},
        )
        state.set_agent_status(
            "reflection",
            AgentRuntimeStatus.COMPLETED,
            decision={
                "hooks": "recorded",
                "auto_optimize": False,
                "lesson": (learn_out.get("post_mortem") or {}).get("lesson"),
                "proposal": (learn_out.get("proposal") or {}).get("proposal_id"),
            },
        )
    else:
        bus.emit(
            EventType.RISK_REJECTED,
            payload={"reason_codes": result.get("reason_codes")},
            agent_id="risk_manager",
            symbol=symbol,
            run_id=run_id,
        )
        state.set_agent_status(
            "risk_manager",
            AgentRuntimeStatus.FAILED,
            error=",".join(str(x) for x in (result.get("reason_codes") or [])),
        )

    return {
        "run_id": run_id,
        "executed": approved,
        "result": result,
        "learning": learning.status() if approved else None,
        "learning_context": learning_ctx,
        "TRADING_MODE": "PAPER",
        "LIVE_TRADING_ENABLED": False,
        "Live Execution": "DISABLED",
    }
