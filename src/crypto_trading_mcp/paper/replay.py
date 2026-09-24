from __future__ import annotations

import hashlib
import json
from typing import Any

from crypto_trading_mcp.exchange.models import Order, OrderSide, OrderType
from crypto_trading_mcp.exchange.paper import PaperExchange
from crypto_trading_mcp.execution.planner import TradePlan
from crypto_trading_mcp.paper.engine import PaperTradingEngine


class DeterministicReplay:
    """Replay identical paper runs from a frozen event tape."""

    def run(
        self,
        *,
        initial_cash: float,
        prices: list[tuple[str, float]],
        plans: list[TradePlan],
        seed_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        engine = PaperTradingEngine()
        engine.reset()
        engine.exchange.portfolio = engine.exchange.portfolio.__class__(starting_cash=initial_cash)
        engine.start()
        results = []
        for symbol, price in prices:
            engine.exchange.set_price(symbol, price)
            engine.exchange.on_price_update(symbol, price)
        for plan in plans:
            px = engine.exchange.prices.get(plan.symbol.upper(), plan.entry_price)
            results.append(
                engine.execute_approved_plan(
                    plan,
                    market_price=px,
                    asset_class="CRYPTO",
                    analysis={"consensus": {"decision": plan.side, "confidence": plan.confidence}},
                )
            )
        snap = engine.exchange.portfolio.snapshot(engine.exchange.prices)
        payload = {
            "seed_meta": seed_meta or {},
            "orders": [o.model_dump(mode="json") for o in engine.exchange.orders.values()],
            "fills": [f.model_dump(mode="json") for f in engine.exchange.fills],
            "positions": snap.to_dict(),
            "fees": snap.fees,
            "trades": engine.exchange.trades,
            "execution_results": results,
        }
        # Stable hash ignoring timestamps / random ids for structural compare helpers
        structural = {
            "fill_count": len(engine.exchange.fills),
            "order_count": len(engine.exchange.orders),
            "cash": round(snap.cash, 8),
            "equity": round(snap.equity, 8),
            "realized_pnl": round(snap.realized_pnl, 8),
            "fees": round(snap.fees, 8),
        }
        payload["structural"] = structural
        payload["structural_hash"] = hashlib.sha256(
            json.dumps(structural, sort_keys=True).encode()
        ).hexdigest()
        return payload
