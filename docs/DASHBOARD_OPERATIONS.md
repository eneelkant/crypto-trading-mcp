# Dashboard Operations

## Config

`config/dashboard.yaml`

```yaml
dashboard:
  enabled: true
  host: "127.0.0.1"
  port: 8050
  auto_open: true
  websocket_enabled: true
  event_history_limit: 5000
```

Env: `DASHBOARD_ENABLED`, `DASHBOARD_HOST`, `DASHBOARD_PORT`, `DASHBOARD_AUTO_OPEN`.

Disable browser open:

```bash
DASHBOARD_AUTO_OPEN=false trader run --no-browser
```

## Troubleshooting

- Health: `curl http://127.0.0.1:8050/api/health`
- If UI missing, fallback HTML is served until `dashboard_ui/dist` is built (`cd dashboard_ui && npm run build`)
- Dashboard stop does not stop paper trading

## Kill switch

Dashboard **EMERGENCY STOP** activates the existing Phase 5 kill switch.
LLM cannot deactivate it. Restart requires operator path / `safe_restart`.
