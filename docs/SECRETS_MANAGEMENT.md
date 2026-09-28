# Secrets Management

## Rules

1. Never commit `.env` or real keys.
2. Local Stage 1: `EnvironmentCredentialProvider` only.
3. Stage 3+: `SecretManagerCredentialProvider` (GCP/AWS/Vault backend).
4. Redact with `credentials.redact_payload` before any outbound event.
5. Rotate keys with dual-version overlap; withdrawals always disabled at the venue.
6. Prefer static egress + IP allowlists for production keys.

## CI

`crypto_trading_mcp.ci.safety_gates.scan_path_for_secrets` fails on private key blocks and populated secret assignments outside `.example` files.
