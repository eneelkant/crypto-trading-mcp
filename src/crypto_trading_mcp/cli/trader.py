from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from crypto_trading_mcp.config.settings import get_settings
from crypto_trading_mcp.orchestration.orchestrator import TradingOrchestrator
from crypto_trading_mcp.orchestration.proposal import default_mock_candles
from crypto_trading_mcp.market.data import MockMarketData
from crypto_trading_mcp.risk.config import load_risk_config, merge_effective_limits
from crypto_trading_mcp.strategy.repository import StrategyKnowledgeService


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
        "Timeframes:",
        "Execution: 5m",
        "Bias: 240m",
        "",
        "Models:",
    ]
    names = {
        "M1": "PO3 Sweep",
        "M2": "VWAP Reclaim",
        "M3": "Order Flow Absorption",
        "M4": "ICT FVG",
    }
    for mid in ("M1", "M2", "M3", "M4"):
        lines.append(f"{mid} {names.get(mid, mid)}: {models.get(mid, 'UNKNOWN')}")
    lines.extend(
        [
            "",
            "Confluence:",
            f"{confluence.get('confirmed', 0)}/{confluence.get('available', 0)} available models",
            "",
            "Consensus:",
            f"{consensus.get('decision', 'NO_TRADE')}",
            "",
            "Confidence:",
            f"{consensus.get('confidence', 0)}",
            "",
            "Trade Plan:",
            f"Status: {plan.get('status')}",
            f"Side: {plan.get('side')}",
            f"Entry: {plan.get('entry_price')}",
            f"Stop: {plan.get('stop_loss')}",
            f"Target: {plan.get('take_profit')}",
            f"Quantity: {plan.get('quantity')}",
            f"Risk/Reward: {plan.get('risk_reward_ratio')}",
            "",
            "Risk:",
            "APPROVED" if risk.get("approved") else "REJECTED",
            "Reason:",
            ", ".join(str(x) for x in risk.get("reason_codes", [])),
            "",
            "execution_attempted: false",
            "live_trading_enabled: false",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="trader", description="Crypto trading MCP CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Show trading mode and safety flags")
    sub.add_parser("agents", help="List registered analysis agents")
    sub.add_parser("risk", help="Show effective risk limits and kill-switch status")
    sub.add_parser("portfolio", help="Show deterministic portfolio snapshot")

    analyze = sub.add_parser("analyze", help="Run analysis pipeline (no execution)")
    analyze.add_argument("symbol", help="Symbol such as BTC/USD")
    analyze.add_argument("--timeframe", default="1h")
    analyze.add_argument("--exchange", default=None)

    propose = sub.add_parser(
        "propose", help="Analyze + trade plan + risk (no execution)"
    )
    propose.add_argument("symbol", help="Symbol such as BTC-USD or BTC/USD")
    propose.add_argument("--timeframe", default="5m")
    propose.add_argument("--exchange", default=None)
    propose.add_argument("--json", action="store_true")
    propose.add_argument(
        "--mock",
        action="store_true",
        help="Use mock market data (default when public fetch is undesired)",
    )

    args = parser.parse_args(argv)
    settings = get_settings()

    if args.command == "status":
        _print(
            {
                "trading_mode": settings.trading_mode,
                "live_trading_enabled": settings.live_trading_enabled,
                "real_money": settings.real_money_enabled,
                "llm_provider": settings.llm_provider,
                "model_name": settings.model_name,
                "phase": 4,
                "note": "Proposal/risk only; no trade execution.",
            }
        )
        return 0

    if args.command == "agents":
        from crypto_trading_mcp.agents.registry import build_default_registry

        registry = build_default_registry()
        rows = [
            {
                "id": agent.agent_id,
                "name": agent.name,
                "version": agent.version,
                "responsibility": agent.responsibility,
            }
            for agent in registry.list()
        ]
        _print(rows)
        return 0

    if args.command == "risk":
        cfg = load_risk_config()
        knowledge = StrategyKnowledgeService()
        strategy = knowledge.get_strategy()
        effective = merge_effective_limits(cfg.risk, strategy.config)
        _print(
            {
                "trading_mode": settings.trading_mode,
                "live_trading_enabled": settings.live_trading_enabled,
                "kill_switch": cfg.kill_switch.model_dump(),
                "global_risk": cfg.risk.model_dump(),
                "strategy_risk": strategy.config.risk_management.model_dump(),
                "effective_limits": effective,
                "note": "Global risk engine wins when stricter than strategy.",
            }
        )
        return 0

    if args.command == "portfolio":
        orch = TradingOrchestrator(settings=settings)
        _print(orch.portfolio.snapshot().to_dict())
        return 0

    if args.command == "analyze":
        orch = TradingOrchestrator(
            settings=settings,
            market_data=MockMarketData(candles=default_mock_candles(400))
            if args.exchange is None
            else None,
        )
        result = asyncio.run(
            orch.analyze(
                args.symbol,
                timeframe=args.timeframe,
                exchange_id=args.exchange,
            )
        )
        _print(result)
        return 0

    if args.command == "propose":
        market_data = MockMarketData(candles=default_mock_candles(400))
        orch = TradingOrchestrator(settings=settings, market_data=market_data)
        result = asyncio.run(
            orch.propose(
                args.symbol,
                timeframe=args.timeframe,
                exchange_id=args.exchange,
            )
        )
        if args.json:
            _print(result)
        else:
            print(_format_propose(result))
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
