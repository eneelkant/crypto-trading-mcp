from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from crypto_trading_mcp.backtest.baselines import run_baselines
from crypto_trading_mcp.backtest.data import generate_synthetic_candles
from crypto_trading_mcp.backtest.engine import BacktestEngine
from crypto_trading_mcp.backtest.monte_carlo import monte_carlo_trade_resample
from crypto_trading_mcp.backtest.prediction import evaluate_prediction_rows
from crypto_trading_mcp.backtest.reporting import summarize_result
from crypto_trading_mcp.backtest.sensitivity import parameter_sensitivity
from crypto_trading_mcp.backtest.walk_forward import WalkForwardValidator
from crypto_trading_mcp.dashboard.event_bus import get_event_bus
from crypto_trading_mcp.dashboard.events import EventType
from crypto_trading_mcp.dashboard.serializers import serialize_order, serialize_trade
from crypto_trading_mcp.dashboard.state import get_dashboard_state
from crypto_trading_mcp.market.indicators import atr, ema, macd, rsi, sma
from crypto_trading_mcp.performance.metrics import compute_performance

router = APIRouter()


def _state():
    return get_dashboard_state()


@router.get("/health")
def health() -> dict[str, Any]:
    state = _state()
    return {
        "status": "ok",
        "TRADING_MODE": "PAPER",
        "LIVE_TRADING_ENABLED": False,
        "uptime_seconds": state.uptime_seconds(),
    }


@router.get("/system/status")
def system_status() -> dict[str, Any]:
    return _state().system_status()


@router.get("/agents")
def agents() -> list[dict[str, Any]]:
    return _state().agents_view()


@router.get("/agents/{agent_id}")
def agent_detail(agent_id: str) -> dict[str, Any]:
    for agent in _state().agents_view():
        if agent["agent_id"] == agent_id:
            return agent
    raise HTTPException(status_code=404, detail="agent_not_found")


@router.get("/events")
def events(limit: int = 200, event_type: str | None = None) -> list[dict[str, Any]]:
    return get_event_bus().history(limit=limit, event_type=event_type)


@router.get("/events/{event_id}")
def event_detail(event_id: str) -> dict[str, Any]:
    event = get_event_bus().get(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="event_not_found")
    return event


@router.get("/market/{symbol}")
def market(symbol: str, bars: int = 120) -> dict[str, Any]:
    state = _state()
    sym = symbol.upper().replace("-", "/")
    candles = generate_synthetic_candles(symbol=sym, n=bars, seed=42)
    closes = [c.close for c in candles]
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    macd_data = macd(closes)
    payload = {
        "symbol": sym,
        "candles": [c.to_dict() for c in candles],
        "indicators": {
            "sma_20": sma(closes, 20),
            "ema_20": ema(closes, 20),
            "rsi_14": rsi(closes, 14),
            "atr_14": atr(highs, lows, closes, 14),
            "macd": macd_data,
        },
        "source": "deterministic_indicators",
        "note": "Indicators computed server-side; not duplicated in JS.",
    }
    state.market_cache[sym] = payload
    return payload


@router.get("/portfolio")
def portfolio() -> dict[str, Any]:
    return _state().portfolio_view()


@router.get("/positions")
def positions() -> list[dict[str, Any]]:
    return _state().paper.exchange.get_positions()


@router.get("/orders")
def orders() -> list[dict[str, Any]]:
    return [
        serialize_order(o.model_dump(mode="json"))
        for o in _state().paper.exchange.orders.values()
    ]


@router.get("/trades")
def trades() -> list[dict[str, Any]]:
    return [serialize_trade(t) for t in _state().paper.exchange.trades]


@router.get("/risk")
def risk() -> dict[str, Any]:
    return _state().risk_view()


@router.get("/performance")
def performance() -> dict[str, Any]:
    state = _state()
    trades = state.paper.exchange.trades
    return {
        **compute_performance(trades, starting_equity=float(state.paper.session.starting_capital)),
        "TRADING_MODE": "PAPER",
        "REAL_MONEY": "DISABLED",
    }


@router.get("/backtests")
def backtests() -> dict[str, Any]:
    state = _state()
    return {"runs": state.backtest_store.list_runs(), "latest": state.latest_backtests[-20:]}


@router.get("/backtests/{backtest_id}")
def backtest_detail(backtest_id: str) -> dict[str, Any]:
    payload = _state().backtest_store.get_run(backtest_id)
    if not payload:
        raise HTTPException(status_code=404, detail="backtest_not_found")
    return payload


@router.get("/walk-forward")
def walk_forward() -> dict[str, Any]:
    return _state().walk_forward or {"folds": [], "note": "No walk-forward run yet"}


@router.get("/sensitivity")
def sensitivity() -> dict[str, Any]:
    return {"rows": _state().sensitivity, "note": "No automatic parameter selection"}


@router.get("/monte-carlo")
def monte_carlo() -> dict[str, Any]:
    return _state().monte_carlo or {"enabled": False, "label": "simulation_not_prediction"}


@router.get("/benchmarks")
def benchmarks() -> dict[str, Any]:
    return _state().benchmarks or {"note": "No benchmark run yet"}


@router.get("/prediction-backtests")
def prediction_backtests() -> dict[str, Any]:
    return _state().prediction_backtests or {"note": "No prediction backtest yet"}


@router.get("/strategies")
def strategies() -> list[dict[str, Any]]:
    knowledge = _state().knowledge
    rows = []
    for record in knowledge.repository.list():
        rows.append(
            {
                "strategy_id": record.strategy_id,
                "name": record.name,
                "version": record.version,
                "config_hash": record.config_hash,
                "status": record.status.value,
            }
        )
    return rows


@router.get("/llm/providers")
def llm_providers() -> dict[str, Any]:
    return {"providers": list(_state().llm_stats.values()), "note": "No API keys exposed"}


@router.get("/mcp/activity")
def mcp_activity() -> list[dict[str, Any]]:
    return list(_state().mcp_activity[-200:])


@router.post("/actions/kill-switch")
def activate_kill_switch() -> dict[str, Any]:
    state = _state()
    state.paper.kill_switch.activate("dashboard_emergency_stop")
    state.paper.exchange.halt("KILL_SWITCH_ACTIVE")
    get_event_bus().emit(
        EventType.KILL_SWITCH_ACTIVATED,
        payload={"reason": "dashboard_emergency_stop", "no_new_trades": True},
        severity="critical",
    )
    return {"activated": True, "note": "LLM cannot deactivate kill switch"}


@router.post("/actions/paper/start")
def paper_start() -> dict[str, Any]:
    return _state().paper.start()


@router.post("/actions/paper/stop")
def paper_stop() -> dict[str, Any]:
    return _state().paper.stop()


@router.post("/actions/paper/reset")
def paper_reset() -> dict[str, Any]:
    return _state().paper.reset()


@router.post("/actions/run-backtest")
def run_backtest(symbol: str = "BTC/USD", bars: int = 80) -> dict[str, Any]:
    state = _state()
    bus = get_event_bus()
    bus.emit(EventType.BACKTEST_STARTED, payload={"symbol": symbol, "bars": bars}, symbol=symbol)
    candles = generate_synthetic_candles(symbol=symbol.upper(), n=bars, seed=42)
    bus.emit(EventType.BACKTEST_PROGRESS, payload={"progress": 0.5}, symbol=symbol)
    result = BacktestEngine().run(
        candles=candles,
        strategy_id="momentum_breakout_crypto",
        signal_params={"volume_mult": 1.0, "lookback": 10},
    )
    state.backtest_store.save_result(result)
    summary = summarize_result(result)
    state.latest_backtests.append(summary)
    bus.emit(EventType.BACKTEST_COMPLETED, payload=summary, symbol=symbol)
    state.record_mcp("run_backtest", status="OK")
    return summary


@router.post("/actions/run-walk-forward")
def run_walk_forward(symbol: str = "BTC/USD", bars: int = 90) -> dict[str, Any]:
    state = _state()
    bus = get_event_bus()
    bus.emit(EventType.WALK_FORWARD_STARTED, payload={"symbol": symbol}, symbol=symbol)
    candles = generate_synthetic_candles(symbol=symbol.upper(), n=bars, seed=3)
    out = WalkForwardValidator().run(candles, strategy_id="momentum_breakout_crypto", symbol=symbol)
    state.walk_forward = out
    bus.emit(EventType.WALK_FORWARD_COMPLETED, payload={"folds": len(out.get("folds") or [])}, symbol=symbol)
    return out


@router.post("/actions/run-benchmark")
def run_benchmark(symbol: str = "BTC/USD", bars: int = 60) -> dict[str, Any]:
    state = _state()
    bus = get_event_bus()
    bus.emit(EventType.BENCHMARK_STARTED, payload={"symbol": symbol}, symbol=symbol)
    candles = generate_synthetic_candles(symbol=symbol.upper(), n=bars, seed=5)
    out = run_baselines(candles)
    state.benchmarks = out
    bus.emit(EventType.BENCHMARK_COMPLETED, payload={"benchmarks": list(out.keys())}, symbol=symbol)
    return out


@router.post("/actions/run-prediction-backtest")
def run_prediction_backtest() -> dict[str, Any]:
    state = _state()
    bus = get_event_bus()
    bus.emit(EventType.PREDICTION_BACKTEST_STARTED, payload={})
    out = evaluate_prediction_rows(
        [
            {
                "predicted_probability": 0.62,
                "market_probability": 0.55,
                "outcome": 1,
                "quantity": 10,
                "model": "ensemble",
                "weight": 1.0,
                "confidence": 0.7,
            }
        ]
    )
    state.prediction_backtests = out
    bus.emit(EventType.PREDICTION_BACKTEST_COMPLETED, payload={"brier_mean": out.get("brier_mean")})
    return out


@router.post("/actions/run-sensitivity")
def run_sensitivity(symbol: str = "BTC/USD", bars: int = 80) -> dict[str, Any]:
    state = _state()
    bus = get_event_bus()
    bus.emit(EventType.SENSITIVITY_STARTED, payload={"symbol": symbol}, symbol=symbol)
    candles = generate_synthetic_candles(symbol=symbol.upper(), n=bars, seed=9)
    rows = parameter_sensitivity(
        BacktestEngine(), candles, lookbacks=[10, 12], atr_multipliers=[2.0]
    )
    state.sensitivity = rows
    bus.emit(EventType.SENSITIVITY_COMPLETED, payload={"rows": len(rows)}, symbol=symbol)
    return {"rows": rows}


@router.post("/actions/run-monte-carlo")
def run_monte_carlo() -> dict[str, Any]:
    state = _state()
    bus = get_event_bus()
    bus.emit(EventType.MONTE_CARLO_STARTED, payload={})
    pnls = [float(t.get("net_pnl") or 0.0) for t in state.paper.exchange.trades] or [1.0, -0.5, 0.2]
    out = monte_carlo_trade_resample(pnls, iterations=100, seed=42)
    state.monte_carlo = out
    bus.emit(EventType.MONTE_CARLO_COMPLETED, payload={"iterations": out.get("iterations")})
    return out


@router.post("/actions/demo-cycle")
def demo_cycle(symbol: str = "BTC/USD", price: float = 100.0) -> dict[str, Any]:
    from crypto_trading_mcp.dashboard.cycle import run_paper_demo_cycle

    return run_paper_demo_cycle(symbol=symbol, price=price)
