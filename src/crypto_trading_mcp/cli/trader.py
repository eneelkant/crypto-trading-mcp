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
    sub.add_parser("risk", help="Show effective risk limits and kill-switch status")
    sub.add_parser("portfolio", help="Show deterministic portfolio snapshot")

    analyze = sub.add_parser("analyze", help="Run analysis pipeline (no execution)")
    analyze.add_argument("symbol")
    analyze.add_argument("--timeframe", default="1h")
    analyze.add_argument("--exchange", default=None)

    propose = sub.add_parser("propose", help="Analyze + trade plan + risk (no execution)")
    propose.add_argument("symbol")
    propose.add_argument("--timeframe", default="5m")
    propose.add_argument("--exchange", default=None)
    propose.add_argument("--json", action="store_true")

    paper = sub.add_parser("paper", help="Paper trading commands")
    paper_sub = paper.add_subparsers(dest="paper_command", required=True)
    paper_sub.add_parser("status")
    paper_sub.add_parser("start")
    paper_sub.add_parser("stop")
    paper_sub.add_parser("positions")
    paper_sub.add_parser("orders")
    paper_sub.add_parser("trades")
    paper_sub.add_parser("performance")
    paper_sub.add_parser("reset")
    paper_sub.add_parser("markets")
    run = paper_sub.add_parser("run")
    run.add_argument("symbol")
    run.add_argument("--price", type=float, default=None)
    run.add_argument("--side", default="LONG", choices=["LONG", "SHORT"])
    predict = paper_sub.add_parser("predict")
    predict.add_argument("market")
    predict.add_argument("--price", type=float, default=0.55)
    predict.add_argument("--model-prob", type=float, default=0.62)
    predict.add_argument("--quantity", type=float, default=10.0)

    args = parser.parse_args(argv)
    settings = get_settings()

    if args.command == "status":
        _print(
            {
                "trading_mode": settings.trading_mode,
                "live_trading_enabled": settings.live_trading_enabled,
                "real_money": False,
                "phase": 5,
                "note": "Paper exchange enabled; live execution disabled.",
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
                "trading_mode": settings.trading_mode,
                "live_trading_enabled": settings.live_trading_enabled,
                "kill_switch": cfg.kill_switch.model_dump(),
                "global_risk": cfg.risk.model_dump(),
                "effective_limits": merge_effective_limits(cfg.risk, strategy.config),
            }
        )
        return 0

    if args.command == "portfolio":
        eng = _engine()
        _print(eng.exchange.portfolio.snapshot(eng.exchange.prices).to_dict())
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
        if cmd == "positions":
            _print(eng.exchange.get_positions())
            return 0
        if cmd == "orders":
            _print([o.model_dump(mode="json") for o in eng.exchange.get_open_orders()])
            return 0
        if cmd == "trades":
            _print(eng.exchange.trades)
            return 0
        if cmd == "performance":
            trades = eng.exchange.trades
            _print(
                {
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

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
