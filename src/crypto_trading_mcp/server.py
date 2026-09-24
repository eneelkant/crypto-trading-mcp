from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import ccxt
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

mcp = FastMCP(
    "Crypto Trading MCP",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[
            "127.0.0.1:*",
            "localhost:*",
            "unknowing-humility-refinance.ngrok-free.dev",
            "unknowing-humility-refinance.ngrok-free.dev:*",
        ],
    ),
)


def _exchange(exchange_id: str) -> Any:
    exchange_name = exchange_id.lower()
    if exchange_name not in ccxt.exchanges:
        raise ValueError(f"Unsupported exchange: {exchange_id}")

    return getattr(ccxt, exchange_name)({"enableRateLimit": True})


@mcp.tool()
def get_spot_price(symbol: str, exchange_id: str = "kraken") -> dict[str, Any]:
    """Return the latest public spot-market price for an exchange symbol such as BTC/USD."""
    exchange = _exchange(exchange_id)

    try:
        ticker = exchange.fetch_ticker(symbol.upper())
    except ccxt.BaseError as error:
        raise ValueError(
            f"Could not fetch {symbol.upper()} from {exchange_id}: {error}"
        ) from error

    return {
        "exchange": exchange_id.lower(),
        "symbol": ticker["symbol"],
        "last_price": ticker["last"],
        "bid": ticker["bid"],
        "ask": ticker["ask"],
        "quote_volume": ticker["quoteVolume"],
        "fetched_at": datetime.now(UTC).isoformat(),
        "note": "Public market data only; this tool does not place trades.",
    }


@mcp.tool()
def estimate_swap_profit(
    asset_amount: float,
    entry_price_usd: float,
    exit_price_usd: float,
    entry_fee_percent: float = 0.0,
    exit_fee_percent: float = 0.0,
    network_fee_usd: float = 0.0,
) -> dict[str, float | str]:
    """Estimate USD profit or loss after trading and network fees. This is not investment advice."""
    values = [
        asset_amount,
        entry_price_usd,
        exit_price_usd,
        entry_fee_percent,
        exit_fee_percent,
        network_fee_usd,
    ]
    if any(value < 0 for value in values):
        raise ValueError("Amounts, prices, and fees must be zero or greater.")
    if entry_price_usd == 0:
        raise ValueError("entry_price_usd must be greater than zero.")
    if entry_fee_percent >= 100 or exit_fee_percent >= 100:
        raise ValueError("Percentage fees must be below 100.")

    gross_cost = asset_amount * entry_price_usd
    entry_fee_usd = gross_cost * (entry_fee_percent / 100)
    gross_proceeds = asset_amount * exit_price_usd
    exit_fee_usd = gross_proceeds * (exit_fee_percent / 100)
    total_cost = gross_cost + entry_fee_usd + network_fee_usd
    net_proceeds = gross_proceeds - exit_fee_usd
    profit_usd = net_proceeds - total_cost
    profit_percent = (profit_usd / total_cost * 100) if total_cost else 0.0

    return {
        "gross_cost_usd": round(gross_cost, 2),
        "net_proceeds_usd": round(net_proceeds, 2),
        "total_fees_usd": round(entry_fee_usd + exit_fee_usd + network_fee_usd, 2),
        "profit_usd": round(profit_usd, 2),
        "profit_percent": round(profit_percent, 2),
        "disclaimer": "Estimate only; prices, slippage, and fees can change before execution.",
    }


# --- Phase 5 paper-safe tools (no live execute_trade) ---
_paper_tools = None


def _paper():
    global _paper_tools
    if _paper_tools is None:
        from crypto_trading_mcp.mcp_tools.paper import PaperToolSurface

        _paper_tools = PaperToolSurface()
    return _paper_tools


@mcp.tool()
def get_portfolio() -> dict[str, Any]:
    """Return the paper portfolio snapshot. Real money is never used."""
    return _paper().get_portfolio()


@mcp.tool()
def get_positions() -> list[dict[str, Any]]:
    """Return open paper positions."""
    return _paper().get_positions()


@mcp.tool()
def get_open_orders() -> list[dict[str, Any]]:
    """Return open paper orders."""
    return _paper().get_open_orders()


@mcp.tool()
def get_trade_status(order_id: str) -> dict[str, Any]:
    """Return status for a paper order id."""
    return _paper().get_trade_status(order_id)


@mcp.tool()
def get_performance() -> dict[str, Any]:
    """Return paper trading performance metrics."""
    return _paper().get_performance()


@mcp.tool()
def propose_trade(plan: dict[str, Any]) -> dict[str, Any]:
    """Acknowledge a proposed trade plan (no execution)."""
    return _paper().propose_trade(plan)


@mcp.tool()
def validate_trade(plan: dict[str, Any]) -> dict[str, Any]:
    """Validate a trade for paper mode. Does not place live orders."""
    return _paper().validate_trade(plan)


@mcp.tool()
def paper_execute_trade(plan: dict[str, Any], market_price: float) -> dict[str, Any]:
    """Execute a trade on the PaperExchange only when TRADING_MODE=paper."""
    from crypto_trading_mcp.config.settings import get_settings

    settings = get_settings()
    if settings.trading_mode != "paper":
        return {
            "executed": False,
            "reason_codes": ["TRADING_MODE_NOT_PAPER"],
            "note": "paper_execute_trade refuses non-paper modes.",
        }
    if settings.live_trading_enabled:
        return {
            "executed": False,
            "reason_codes": ["LIVE_TRADING_ENABLED_BLOCKED"],
        }
    return _paper().paper_execute_trade(plan, market_price)


if __name__ == "__main__":
    mcp.run(transport="stdio")
