# Production Credentials

**Status:** Architecture implemented; no production secrets created.

```text
TRADING_MODE=paper
LIVE_TRADING_ENABLED=false
Withdrawal permissions: NONE
```

## Providers

| Provider | Use |
|----------|-----|
| EnvironmentCredentialProvider | Local paper / dev |
| SecretManagerCredentialProvider | Cloud Stage 3+ (backend injected) |

## Permission model

- Allowed: `READ_ONLY`, `TRADING`
- Forbidden: `WITHDRAWAL` (validator raises)

## Environments

`MOCK` · `SANDBOX` · `TESTNET` · `PRODUCTION_READ_ONLY` · `PRODUCTION_TRADING`

Production trading orders remain disabled in adapters even if flags were flipped; `LiveTradingGate` additionally fails closed under paper defaults.

## Related

- `docs/EXCHANGE_CREDENTIALS.md`
- `docs/CREDENTIAL_PROVIDER.md`
- `docs/SECRETS_MANAGEMENT.md`
