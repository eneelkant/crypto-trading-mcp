# Credential Provider

Interfaces:

- `CredentialProvider`
- `EnvironmentCredentialProvider` — local/dev via env vars
- `SecretManagerCredentialProvider` — cloud backend inject (`get_secret`)
- `CredentialPermissionValidator` — rejects `WITHDRAWAL`
- `CredentialHealthCheck` — public status only

Public APIs expose `has_api_key` / `has_api_secret` booleans — never secret values.

Secrets must never appear in logs, EventBus, dashboard, MCP, agents, RAG, learning memory, exceptions, tests reports, DB records, or Git.
