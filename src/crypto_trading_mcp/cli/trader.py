from __future__ import annotations

import argparse
import asyncio
import json

from crypto_trading_mcp.config.settings import get_settings
from crypto_trading_mcp.orchestration.orchestrator import TradingOrchestrator


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="trader", description="Crypto trading MCP CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Show trading mode and safety flags")
    sub.add_parser("agents", help="List registered analysis agents")

    analyze = sub.add_parser("analyze", help="Run analysis pipeline (no execution)")
    analyze.add_argument("symbol", help="Symbol such as BTC/USD")
    analyze.add_argument("--timeframe", default="1h")
    analyze.add_argument("--exchange", default=None)

    args = parser.parse_args(argv)
    settings = get_settings()

    if args.command == "status":
        print(
            json.dumps(
                {
                    "trading_mode": settings.trading_mode,
                    "live_trading_enabled": settings.live_trading_enabled,
                    "real_money": settings.real_money_enabled,
                    "llm_provider": settings.llm_provider,
                    "model_name": settings.model_name,
                    "phase": 3,
                    "note": "Analysis agents only; no trade execution.",
                },
                indent=2,
            )
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
        print(json.dumps(rows, indent=2))
        return 0

    if args.command == "analyze":
        orch = TradingOrchestrator(settings=settings)
        result = asyncio.run(
            orch.analyze(
                args.symbol,
                timeframe=args.timeframe,
                exchange_id=args.exchange,
            )
        )
        print(json.dumps(result, indent=2, default=str))
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
