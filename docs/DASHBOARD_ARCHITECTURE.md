# Dashboard Architecture

```text
dashboard/
  app.py           FastAPI app + static UI
  routes.py        REST API
  websocket.py     /ws stream
  event_bus.py     pub/sub + history
  events.py        typed/sanitized events
  state.py         shared snapshot (not a second engine)
  cycle.py         demo paper cycle via PaperTradingEngine
  runtime.py       uvicorn daemon thread
  browser.py       one-shot local auto-open
  config.py        config/dashboard.yaml + env
```

Frontend: `dashboard_ui/` (React + Vite + Lightweight Charts), built to `dashboard_ui/dist`.

Data sources reused (not duplicated):

- PaperTradingEngine / PaperExchange / Portfolio / RiskEngine
- BacktestEngine / BacktestStore / WalkForward / Baselines / Metrics

## Learning integration

`routes.py` exposes `/learning/*`. `cycle.py` runs post-mortem after demo close.
Learning engine publishes to the same EventBus; no second dashboard process.
