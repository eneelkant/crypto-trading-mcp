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


if __name__ == "__main__":
    mcp.run(transport="stdio")
