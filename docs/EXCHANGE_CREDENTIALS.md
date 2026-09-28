# Exchange Credentials

```text
TRADING_MODE=paper
LIVE_TRADING_ENABLED=false
Withdrawal permissions: NONE (forbidden)
```

No real API keys are created or stored by this repository.

## Coinbase

| Topic | Detail |
|-------|--------|
| Auth | HMAC envelope (`CB-ACCESS-*`) implemented for testable signed reads; Advanced Trade JWT can replace later |
| Required secrets | `COINBASE_API_KEY`, `COINBASE_API_SECRET` |
| Read-only | Accounts, balances, historical orders |
| Trading | Place/cancel — blocked unless sandbox transport or future Stage 5+ gates |
| Withdrawal | **Forbidden** for trading bot keys |
| IP allowlisting | Required for production keys |
| Environments | `MOCK`, `SANDBOX`, `TESTNET`, `PRODUCTION_READ_ONLY`, `PRODUCTION_TRADING` |
| Sandbox | Use injected transport hooks until vendor sandbox is wired |

## Delta Exchange India

| Topic | Detail |
|-------|--------|
| Auth | HMAC-SHA256: `method + timestamp + path + query + body` |
| Required secrets | `DELTA_API_KEY`, `DELTA_API_SECRET`, optional `DELTA_API_BASE_URL` |
| Clock skew | Rejected beyond configured skew |
| Reads | Wallet balances, positions, open orders, order history |
| Trading | Place/cancel gated; production submit not enabled |
| Withdrawal | **Forbidden** |
| Rate limits | Honor exchange limits; circuit breaker on repeated failures |

## Minimum permission set

- `READ_ONLY` for Stage 3
- `READ_ONLY` + `TRADING` for Stage 5+
- Never `WITHDRAWAL`

See `docs/CREDENTIAL_PROVIDER.md` and `docs/SECRETS_MANAGEMENT.md`.
