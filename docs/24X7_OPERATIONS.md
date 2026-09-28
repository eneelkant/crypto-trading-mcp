# 24×7 Operations

- Automatic restart: compose `restart: unless-stopped` / systemd / k8s
- Health: Dockerfile HEALTHCHECK asserts live gate disabled
- Graceful shutdown: stop autonomous loop + persist state
- Durable state: SQLite local / Postgres interface for prod
- Kill switch + alerts + stale-data monitoring required before Stage 5
