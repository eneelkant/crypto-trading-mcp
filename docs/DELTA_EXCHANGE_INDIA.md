# Delta Exchange India Adapter

Base URL: `https://api.india.delta.exchange`

Auth: HMAC-SHA256 over `method + timestamp + requestPath + query_params + body`.

Live orders remain blocked in Phase 9. Env: `DELTA_API_KEY`, `DELTA_API_SECRET`,
`DELTA_API_BASE_URL`.
