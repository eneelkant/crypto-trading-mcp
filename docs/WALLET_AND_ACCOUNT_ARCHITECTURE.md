# Wallet and Account Architecture

```text
TRADING_MODE=paper
LIVE_TRADING_ENABLED=false
```

## Does CEX trading need blockchain private keys?

**No.** Coinbase and Delta Exchange India are custodial CEX APIs.

| Model | Secrets | Required for spot/perp API trading? |
|-------|---------|-------------------------------------|
| CENTRALIZED_EXCHANGE | API key/secret | Yes (for authenticated reads/trades) |
| BLOCKCHAIN_WALLET | seed / private key | **No** for CEX path |
| PAPER_SIMULATED | none | Stage 1–2 |

Code: `wallet.cex_trading_requires_blockchain_key() -> False`.

## CEX account surface

Balances, available balances, positions, margin/collateral fields, open orders, fills, realized/unrealized PnL — via `AccountSnapshot` and exchange adapters.

## Blockchain wallets

Only for future isolated on-chain / prediction adapters via `IsolatedSigner`. Never store seeds in `.env`, Git, DB, logs, RAG, agents, or dashboard.
