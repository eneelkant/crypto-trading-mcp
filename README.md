# Crypto Trading MCP

A read-only MCP server for public crypto market prices and swap-profit estimates.

## Setup

```bash
pip install -e .
```

## Run locally

```bash
python -m crypto_trading_mcp
```

The server uses standard input/output for MCP clients such as Claude Desktop.

## Tools

- `get_spot_price(symbol, exchange_id="kraken")` — retrieves public spot-market data.
- `estimate_swap_profit(...)` — estimates net profit after trading and network fees.

This server does not store exchange credentials, execute trades, or move funds.
