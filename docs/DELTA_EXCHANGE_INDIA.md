# Delta Exchange India Adapter

Base URL: `https://api.india.delta.exchange`

Auth: HMAC-SHA256 over `method + timestamp + requestPath + query_params + body`.

Live orders remain blocked in Phase 9. Env: `DELTA_API_KEY`, `DELTA_API_SECRET`,
`DELTA_API_BASE_URL`.

## Stage 2 TESTNET

For `STAGE_2_CLOUD_PAPER`, use only allowlisted testnet base URLs from `config/sandbox.yaml`.
Production `https://api.india.delta.exchange` is rejected by `SandboxEndpointGuard`.

Wrapper: `crypto_trading_mcp.sandbox.DeltaIndiaSandboxAdapter`.

Env (sandbox only, never commit values):

```env
DELTA_API_KEY=
DELTA_API_SECRET=
DELTA_API_BASE_URL=https://cdn-ind.testnet.deltaex.org
```
