# Stage 2 Secrets

```text
TRADING_MODE=paper
LIVE_TRADING_ENABLED=false
```

## Local

`EnvironmentSecretProvider` / `EnvironmentCredentialProvider` read:

- `DELTA_API_KEY`
- `DELTA_API_SECRET`
- `DELTA_API_BASE_URL` (must be Stage-2 allowlisted testnet host)

## Cloud

`GoogleSecretManagerProvider` loads JSON secrets via injected GCP client.

Logical name: `exchange/delta_india`

Access audits record secret name + ok flag only — never values.

## Forbidden

- Production hosts/credentials in Stage 2
- `WITHDRAWAL` permission
- Logging/MCP/dashboard/RAG exposure of secret values
- Persisting secrets in SQLite/Postgres
