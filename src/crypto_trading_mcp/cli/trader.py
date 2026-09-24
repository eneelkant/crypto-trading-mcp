from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from crypto_trading_mcp.config.settings import get_settings
from crypto_trading_mcp.exchange.models import OrderSide
from crypto_trading_mcp.exchange.prediction import EnsembleAttribution, PredictionContract
from crypto_trading_mcp.execution.planner import TradePlan
from crypto_trading_mcp.market.data import MockMarketData
from crypto_trading_mcp.orchestration.orchestrator import TradingOrchestrator
from crypto_trading_mcp.orchestration.proposal import default_mock_candles
from crypto_trading_mcp.paper.engine import PaperTradingEngine
from crypto_trading_mcp.performance.metrics import compute_performance, group_performance
from crypto_trading_mcp.risk.config import load_risk_config, merge_effective_limits
from crypto_trading_mcp.strategy.repository import StrategyKnowledgeService

_ENGINE: PaperTradingEngine | None = None


def _engine() -> PaperTradingEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = PaperTradingEngine()
    return _ENGINE


def _print(data: Any) -> None:
    print(json.dumps(data, indent=2, default=str))


def _format_propose(result: dict[str, Any]) -> str:
    strategy = result.get("strategy", {})
    models = result.get("models", {})
    confluence = result.get("confluence", {})
    consensus = result.get("consensus", {})
    plan = result.get("trade_plan", {})
    risk = result.get("risk", {})
    lines = [
        "Strategy:",
        f"{strategy.get('name', strategy.get('strategy_id', 'unknown'))}",
        f"Version: {strategy.get('version', 'unknown')}",
        "",
        "Symbol:",
        f"{plan.get('symbol', result.get('analysis', {}).get('symbol', 'unknown'))}",
        "",
        "Models:",
    ]
    for mid, status in (models or {}).items():
        lines.append(f"{mid}: {status}")
    lines.extend(
        [
            "",
            "Confluence:",
            f"{confluence.get('confirmed', 0)}/{confluence.get('available', 0)} available models",
            "",
            "Consensus:",
            f"{consensus.get('decision', 'NO_TRADE')}",
            "",
            "Trade Plan:",
            f"Status: {plan.get('status')}",
            f"Side: {plan.get('side')}",
            f"Entry: {plan.get('entry_price')}",
            f"Stop: {plan.get('stop_loss')}",
            f"Target: {plan.get('take_profit')}",
            f"Quantity: {plan.get('quantity')}",
            "",
            "Risk:",
            "APPROVED" if risk.get("approved") else "REJECTED",
            "Reason:",
            ", ".join(str(x) for x in risk.get("reason_codes", [])),
            "",
            "TRADING MODE: PAPER",
            "REAL MONEY: DISABLED",
        ]
    )
    return "\n".join(lines)


def _simple_plan(symbol: str, side: str, price: float, strategy_id: str) -> TradePlan:
    stop = price * 0.98 if side == "LONG" else price * 1.02
    tp = price * 1.08 if side == "LONG" else price * 0.92
    qty = 1.0 if symbol.upper() in {"SPY", "QQQ", "GLD", "USO"} else 0.01
    return TradePlan(
        strategy_id=strategy_id,
        strategy_version="1.0.0",
        model_ids=["PAPER"],
        symbol=symbol.upper(),
        side=side,
        entry_price=price,
        quantity=qty,
        notional=qty * price,
        stop_loss=stop,
        take_profit=tp,
        risk_amount=abs(price - stop) * qty,
        expected_fee=qty * price * 0.001,
        expected_slippage=0.0005,
        risk_reward_ratio=abs(tp - price) / abs(price - stop),
        confidence=0.8,
        status="PROPOSED",
        confluence={"move_be_at_1r": strategy_id == "multi_model_po3_vwap", "partial_tp_pct": 50},
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="trader", description="Crypto trading MCP CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Show trading mode and safety flags")
    sub.add_parser("agents", help="List registered analysis agents")
    sub.add_parser("risk", help="Show effective risk limits and kill-switch status (PAPER)")
    sub.add_parser("portfolio", help="Show deterministic portfolio snapshot (PAPER)")
    sub.add_parser("trades", help="Show paper trades")
    sub.add_parser("performance", help="Show paper performance metrics")

    analyze = sub.add_parser("analyze", help="Run analysis pipeline (no execution)")
    analyze.add_argument("symbol")
    analyze.add_argument("--timeframe", default="1h")
    analyze.add_argument("--exchange", default=None)

    propose = sub.add_parser("propose", help="Analyze + trade plan + risk (no execution)")
    propose.add_argument("symbol")
    propose.add_argument("--timeframe", default="5m")
    propose.add_argument("--exchange", default=None)
    propose.add_argument("--json", action="store_true")

    paper = sub.add_parser("paper", help="Paper trading commands (simulated capital only)")
    paper_sub = paper.add_subparsers(dest="paper_command", required=True)
    paper_sub.add_parser("status")
    paper_sub.add_parser("start")
    paper_sub.add_parser("stop")
    paper_sub.add_parser("positions")
    paper_sub.add_parser("portfolio")
    paper_sub.add_parser("orders")
    paper_sub.add_parser("trades")
    paper_sub.add_parser("performance")
    paper_sub.add_parser("reset")
    paper_sub.add_parser("markets")
    paper_sub.add_parser("restart")
    run = paper_sub.add_parser("run")
    run.add_argument("symbol")
    run.add_argument("--price", type=float, default=None)
    run.add_argument("--side", default="LONG", choices=["LONG", "SHORT"])
    predict = paper_sub.add_parser("predict")
    predict.add_argument("market")
    predict.add_argument("--price", type=float, default=0.55)
    predict.add_argument("--model-prob", type=float, default=0.62)
    predict.add_argument("--quantity", type=float, default=10.0)
    replay = paper_sub.add_parser("replay")
    replay.add_argument("--symbol", default="BTC/USD")
    replay.add_argument("--price", type=float, default=100.0)
    replay.add_argument("--qty", type=float, default=1.0)

    run_cmd = sub.add_parser("run", help="Start paper runtime + dashboard (no live trading)")
    run_cmd.add_argument("--no-browser", action="store_true")
    run_cmd.add_argument("--demo", action="store_true", help="Run one paper demo cycle after start")

    dash = sub.add_parser("dashboard", help="Dashboard control")
    dash_sub = dash.add_subparsers(dest="dashboard_command")
    dash_sub.add_parser("start")
    dash_sub.add_parser("stop")
    dash_sub.add_parser("status")
    dash_sub.add_parser("open")

    backtest = sub.add_parser("backtest", help="Historical backtest (offline / paper only)")
    backtest.add_argument("symbol")
    backtest.add_argument("--strategy", default="momentum_breakout_crypto")
    backtest.add_argument("--timeframe", default="1h")
    backtest.add_argument("--start", default=None)
    backtest.add_argument("--end", default=None)
    backtest.add_argument("--bars", type=int, default=120)
    backtest.add_argument("--json", action="store_true")
    backtest.add_argument("--csv", default=None, help="Optional CSV historical path")

    wf = sub.add_parser("walk-forward", help="Walk-forward validation (offline)")
    wf.add_argument("symbol")
    wf.add_argument("--strategy", default="momentum_breakout_crypto")
    wf.add_argument("--timeframe", default="1h")
    wf.add_argument("--bars", type=int, default=120)

    sub.add_parser("backtests", help="List persisted backtest runs")
    report = sub.add_parser("backtest-report", help="Show a backtest report by id")
    report.add_argument("backtest_id")

    bench = sub.add_parser("benchmark", help="Run baseline benchmarks (B&H / DCA / SMA)")
    bench.add_argument("symbol")
    bench.add_argument("--timeframe", default="1h")
    bench.add_argument("--bars", type=int, default=120)

    sub.add_parser("prediction-backtest", help="Run prediction-market evaluation fixture")

    args = parser.parse_args(argv)
    settings = get_settings()

    if args.command == "status":
        _print(
            {
                "trading_mode": settings.trading_mode,
                "live_trading_enabled": settings.live_trading_enabled,
                "real_money": False,
                "phase": 7,
                "note": "Paper trading + observability dashboard; live execution disabled.",
                "dashboard": "http://127.0.0.1:8050",
                "TRADING_MODE": "PAPER",
                "REAL_MONEY": "DISABLED",
            }
        )
        return 0

    if args.command == "agents":
        from crypto_trading_mcp.agents.registry import build_default_registry

        registry = build_default_registry()
        _print(
            [
                {
                    "id": a.agent_id,
                    "name": a.name,
                    "version": a.version,
                    "responsibility": a.responsibility,
                }
                for a in registry.list()
            ]
        )
        return 0

    if args.command == "risk":
        cfg = load_risk_config()
        knowledge = StrategyKnowledgeService()
        strategy = knowledge.get_strategy()
        _print(
            {
                "TRADING_MODE": "PAPER" if settings.trading_mode == "paper" else settings.trading_mode.upper(),
                "REAL_MONEY": "DISABLED",
                "live_trading_enabled": settings.live_trading_enabled,
                "kill_switch": cfg.kill_switch.model_dump(),
                "global_risk": cfg.risk.model_dump(),
                "effective_limits": merge_effective_limits(cfg.risk, strategy.config),
            }
        )
        return 0

    if args.command == "portfolio":
        eng = _engine()
        _print(
            {
                **eng.exchange.portfolio.snapshot(eng.exchange.prices).to_dict(),
                "TRADING_MODE": "PAPER",
                "REAL_MONEY": "DISABLED",
            }
        )
        return 0

    if args.command == "trades":
        eng = _engine()
        _print({"TRADING_MODE": "PAPER", "trades": eng.exchange.trades})
        return 0

    if args.command == "performance":
        eng = _engine()
        _print(
            {
                "TRADING_MODE": "PAPER",
                "REAL_MONEY": "DISABLED",
                "performance": compute_performance(eng.exchange.trades),
            }
        )
        return 0

    if args.command == "analyze":
        orch = TradingOrchestrator(
            settings=settings,
            market_data=MockMarketData(candles=default_mock_candles(400)),
        )
        _print(
            asyncio.run(
                orch.analyze(args.symbol, timeframe=args.timeframe, exchange_id=args.exchange)
            )
        )
        return 0

    if args.command == "propose":
        orch = TradingOrchestrator(
            settings=settings,
            market_data=MockMarketData(candles=default_mock_candles(400)),
        )
        result = asyncio.run(
            orch.propose(args.symbol, timeframe=args.timeframe, exchange_id=args.exchange)
        )
        if args.json:
            _print(result)
        else:
            print(_format_propose(result))
        return 0

    if args.command == "paper":
        eng = _engine()
        cmd = args.paper_command
        if cmd == "status":
            _print(eng.status())
            return 0
        if cmd == "start":
            _print(eng.start())
            return 0
        if cmd == "stop":
            _print(eng.stop())
            return 0
        if cmd == "reset":
            _print(eng.reset())
            return 0
        if cmd == "restart":
            _print(eng.safe_restart())
            return 0
        if cmd == "positions":
            _print({"TRADING_MODE": "PAPER", "positions": eng.exchange.get_positions()})
            return 0
        if cmd == "portfolio":
            _print(
                {
                    **eng.exchange.portfolio.snapshot(eng.exchange.prices).to_dict(),
                    "TRADING_MODE": "PAPER",
                    "REAL_MONEY": "DISABLED",
                }
            )
            return 0
        if cmd == "orders":
            _print(
                {
                    "TRADING_MODE": "PAPER",
                    "orders": [o.model_dump(mode="json") for o in eng.exchange.get_open_orders()],
                }
            )
            return 0
        if cmd == "trades":
            _print({"TRADING_MODE": "PAPER", "trades": eng.exchange.trades})
            return 0
        if cmd == "performance":
            trades = eng.exchange.trades
            _print(
                {
                    "TRADING_MODE": "PAPER",
                    "REAL_MONEY": "DISABLED",
                    "portfolio": compute_performance(trades),
                    "by_strategy": group_performance(trades, "strategy_id"),
                    "by_asset_class": group_performance(trades, "asset_class"),
                    "books": eng.strategy_book_report(),
                }
            )
            return 0
        if cmd == "markets":
            _print(eng.prediction_book.list_markets())
            return 0
        if cmd == "replay":
            from crypto_trading_mcp.paper.replay import DeterministicReplay

            plan = _simple_plan(args.symbol, "LONG", args.price, eng.select_strategy(args.symbol) or "momentum_breakout_crypto")
            plan.quantity = args.qty
            plan.notional = args.qty * args.price
            plan.risk_amount = abs(args.price - plan.stop_loss) * args.qty
            result = DeterministicReplay().run(
                initial_cash=10_000,
                prices=[(args.symbol.upper(), args.price)],
                plans=[plan],
            )
            _print({"TRADING_MODE": "PAPER", "replay": result["structural"], "hash": result["structural_hash"]})
            return 0
        if cmd == "run":
            eng.start()
            symbol = args.symbol.upper()
            strategy_id = eng.select_strategy(symbol) or "multi_model_po3_vwap"
            price = args.price
            if price is None:
                price = 100.0 if symbol in {"SPY", "QQQ", "GLD", "USO"} else 50000.0
            eng.exchange.set_price(symbol, price)
            plan = _simple_plan(symbol, args.side, price, strategy_id)
            asset = eng.exchange._asset_class(symbol).value
            result = eng.execute_approved_plan(
                plan,
                market_price=price,
                asset_class=asset,
                analysis={"consensus": {"decision": args.side, "confidence": 0.8}, "messages": {}},
            )
            _print(result)
            return 0
        if cmd == "predict":
            eng.start()
            market_id = args.market
            contract = PredictionContract(
                market_id=market_id,
                question=f"Simulated market {market_id}",
                outcome="YES",
                price=args.price,
                probability=args.price,
                liquidity=100000,
            )
            eng.prediction_book.register_market(contract)
            attr = EnsembleAttribution(
                grok_weight=0.2,
                claude_weight=0.2,
                gpt_weight=0.2,
                gemini_weight=0.2,
                deepseek_weight=0.2,
                individual_predictions={
                    "grok": args.model_prob,
                    "claude": args.model_prob,
                    "gpt": args.model_prob,
                    "gemini": args.model_prob,
                    "deepseek": args.model_prob,
                },
                ensemble_probability=args.model_prob,
                market_probability=args.price,
                edge=args.model_prob - args.price,
            )
            order = eng.prediction_book.buy(
                contract.symbol,
                args.quantity,
                side=OrderSide.BUY_YES,
                strategy_id="prediction_market_ai",
                attribution=attr,
                model_probability=args.model_prob,
            )
            _print(order.model_dump(mode="json"))
            return 0

    if args.command in {"run", "dashboard"}:
        from crypto_trading_mcp.dashboard.browser import open_dashboard_browser
        from crypto_trading_mcp.dashboard.config import load_dashboard_config
        from crypto_trading_mcp.dashboard.cycle import run_paper_demo_cycle
        from crypto_trading_mcp.dashboard.runtime import get_dashboard_server
        from crypto_trading_mcp.dashboard.state import get_dashboard_state

        cfg = load_dashboard_config()
        server = get_dashboard_server()

        if args.command == "dashboard":
            cmd = args.dashboard_command or "start"
            if cmd == "stop":
                _print(server.stop())
                return 0
            if cmd == "status":
                _print(server.status())
                return 0
            if cmd == "open":
                _print(open_dashboard_browser(cfg, force=True))
                return 0
            # start / default
            result = server.start(open_browser=True)
            _print(result)
            return 0

        # trader run
        state = get_dashboard_state()
        paper = state.paper
        print("AI Trading System")
        print("────────────────────────────────")
        print()
        print("Mode: PAPER")
        print(f"Dashboard: {cfg.url}")
        print()
        dash = server.start(open_browser=not args.no_browser)
        paper.start()
        print("Market Data: ONLINE")
        print("Risk Engine: ONLINE")
        print("Portfolio: ONLINE")
        print("Paper Exchange: ONLINE")
        print("Event Bus: ONLINE")
        print()
        print(f"LLM Provider: {settings.llm_provider.upper()}")
        print(f"Agents: {len(state.agents)} READY")
        print()
        if (dash.get("browser") or {}).get("opened"):
            print("Dashboard opened in browser.")
        elif args.no_browser:
            print("Dashboard browser open skipped (--no-browser).")
        else:
            print(f"Dashboard browser: {dash.get('browser')}")
        print("LIVE TRADING: DISABLED")
        if args.demo:
            demo = run_paper_demo_cycle(state=state)
            _print({"demo": demo, "dashboard": dash})
        else:
            _print({"dashboard": dash, "paper": paper.status(), "TRADING_MODE": "PAPER"})
        return 0

    # --- Phase 6 backtesting (offline) ---
    if args.command in {
        "backtest",
        "walk-forward",
        "backtests",
        "backtest-report",
        "benchmark",
        "prediction-backtest",
    }:
        from datetime import datetime

        from crypto_trading_mcp.backtest.baselines import run_baselines
        from crypto_trading_mcp.backtest.data import (
            CSVHistoricalDataProvider,
            generate_synthetic_candles,
        )
        from crypto_trading_mcp.backtest.engine import BacktestEngine
        from crypto_trading_mcp.backtest.prediction import evaluate_prediction_rows
        from crypto_trading_mcp.backtest.reporting import summarize_result, write_json_report, write_markdown_report
        from crypto_trading_mcp.backtest.store import BacktestStore
        from crypto_trading_mcp.backtest.walk_forward import WalkForwardValidator

        store = getattr(main, "_backtest_store", None)
        if store is None:
            store = BacktestStore()
            setattr(main, "_backtest_store", store)

        def _load_candles(symbol: str, timeframe: str, bars: int, csv_path: str | None = None):
            if csv_path:
                return CSVHistoricalDataProvider(csv_path).load(symbol, timeframe=timeframe)
            return generate_synthetic_candles(
                symbol=symbol.upper(), timeframe=timeframe, n=bars, seed=42
            )

        if args.command == "backtest":
            start = datetime.fromisoformat(args.start) if args.start else None
            end = datetime.fromisoformat(args.end) if args.end else None
            candles = _load_candles(args.symbol, args.timeframe, args.bars, args.csv)
            if start or end:
                candles = [
                    c
                    for c in candles
                    if (start is None or c.timestamp >= start) and (end is None or c.timestamp <= end)
                ]
            engine = BacktestEngine()
            result = engine.run(
                candles=candles,
                strategy_id=args.strategy,
                symbol=args.symbol.upper(),
                timeframe=args.timeframe,
                data_source="csv" if args.csv else "mock",
                signal_params={"volume_mult": 1.0},
            )
            store.save_result(result)
            write_json_report(result)
            write_markdown_report(result)
            payload = summarize_result(result) if not args.json else result.to_dict()
            _print(payload)
            return 0

        if args.command == "walk-forward":
            candles = _load_candles(args.symbol, args.timeframe, args.bars)
            out = WalkForwardValidator().run(
                candles,
                strategy_id=args.strategy,
                symbol=args.symbol.upper(),
                timeframe=args.timeframe,
            )
            _print(out)
            return 0

        if args.command == "backtests":
            _print({"TRADING_MODE": "PAPER", "runs": store.list_runs()})
            return 0

        if args.command == "backtest-report":
            payload = store.get_run(args.backtest_id)
            _print(payload or {"error": "NOT_FOUND", "backtest_id": args.backtest_id})
            return 0

        if args.command == "benchmark":
            candles = _load_candles(args.symbol, args.timeframe, args.bars)
            _print(run_baselines(candles, initial_capital=100_000))
            return 0

        if args.command == "prediction-backtest":
            rows = [
                {
                    "model": "ensemble",
                    "weight": 1.0,
                    "predicted_probability": 0.62,
                    "ensemble_probability": 0.62,
                    "market_probability": 0.55,
                    "confidence": 0.7,
                    "outcome": 1,
                    "quantity": 10,
                },
                {
                    "model": "ensemble",
                    "weight": 1.0,
                    "predicted_probability": 0.40,
                    "ensemble_probability": 0.40,
                    "market_probability": 0.48,
                    "confidence": 0.6,
                    "outcome": 0,
                    "quantity": 10,
                },
            ]
            _print(evaluate_prediction_rows(rows))
            return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
