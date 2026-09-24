from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from crypto_trading_mcp.dashboard.config import DashboardSettings, load_dashboard_config
from crypto_trading_mcp.dashboard.event_bus import get_event_bus
from crypto_trading_mcp.dashboard.events import EventType
from crypto_trading_mcp.dashboard.routes import router
from crypto_trading_mcp.dashboard.state import get_dashboard_state
from crypto_trading_mcp.dashboard.websocket import ws_router


def create_app(settings: DashboardSettings | None = None) -> FastAPI:
    settings = settings or load_dashboard_config()
    app = FastAPI(
        title=settings.title,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    # Localhost-only CORS for Vite dev
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:8050",
            "http://localhost:8050",
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router, prefix="/api")
    app.include_router(ws_router)

    static_dir = settings.static_path
    if static_dir.exists():
        assets = static_dir / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(static_dir / "index.html")

    else:
        @app.get("/", response_class=HTMLResponse)
        def fallback_index() -> str:
            return _fallback_html()

    @app.on_event("startup")
    async def _startup() -> None:
        state = get_dashboard_state()
        state.running = True
        get_event_bus().emit(
            EventType.DASHBOARD_STARTED,
            payload={"url": settings.url, "host": settings.host, "port": settings.port},
        )
        get_event_bus().emit(
            EventType.SYSTEM_HEALTH_CHANGED,
            payload={"status": "ONLINE", "components": list(state.components.keys())},
        )

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        # Dashboard stop must not tear down trading engines.
        state = get_dashboard_state()
        state.running = False
        state.components["WebSocket"].status = "OFFLINE"

    app.state.dashboard_settings = settings  # type: ignore[attr-defined]
    return app


def _fallback_html() -> str:
    """Served when frontend dist is not built yet."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>AI Trading Command Center</title>
  <style>
    :root {
      --bg: #0b1220;
      --panel: #121a2b;
      --text: #e6edf7;
      --muted: #8b9bb4;
      --accent: #3dd6c6;
      --warn: #f0b429;
      --danger: #ff6b6b;
      --ok: #3ecf8e;
      --line: #243047;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0; font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      background: radial-gradient(1200px 600px at 10% -10%, #15233d, var(--bg));
      color: var(--text);
    }
    header {
      display: flex; justify-content: space-between; align-items: center;
      padding: 14px 20px; border-bottom: 1px solid var(--line);
      background: rgba(10,16,28,.85); backdrop-filter: blur(8px);
      position: sticky; top: 0; z-index: 10;
    }
    h1 { font-size: 1rem; letter-spacing: .08em; margin: 0; }
    .badge { color: var(--accent); font-size: .8rem; }
    .grid {
      display: grid; gap: 12px; padding: 12px;
      grid-template-columns: 240px 1fr 260px;
    }
    .panel {
      background: linear-gradient(180deg, #141e31, var(--panel));
      border: 1px solid var(--line); border-radius: 10px; padding: 12px;
      min-height: 120px;
    }
    .panel h2 { margin: 0 0 8px; font-size: .75rem; color: var(--muted); letter-spacing: .06em; }
    .agents { display: grid; gap: 6px; max-height: 70vh; overflow: auto; }
    .agent { display:flex; justify-content:space-between; gap:8px; font-size:.8rem; padding:6px 8px; border-radius:6px; background:#0e1626; }
    .dot { width:8px; height:8px; border-radius:50%; display:inline-block; margin-right:6px; background: var(--muted); }
    .dot.RUNNING { background: var(--warn); }
    .dot.COMPLETED { background: var(--ok); }
    .dot.FAILED { background: var(--danger); }
    .dot.IDLE { background: #4a5872; }
    #timeline { max-height: 220px; overflow:auto; font-size:.8rem; }
    .evt { border-left: 2px solid var(--accent); padding: 6px 8px; margin: 6px 0; background:#0e1626; }
    button {
      background: #1a2740; color: var(--text); border: 1px solid var(--line);
      border-radius: 8px; padding: 8px 12px; cursor: pointer;
    }
    button.danger { background: #3a1520; border-color: #6b2434; color: #ffb4b4; }
    .metrics { display:grid; grid-template-columns: repeat(3,1fr); gap:8px; }
    .metric { background:#0e1626; padding:8px; border-radius:8px; }
    .metric span { display:block; color:var(--muted); font-size:.7rem; }
    .wide { grid-column: 1 / -1; }
    @media (max-width: 980px) {
      .grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>AI TRADING COMMAND CENTER</h1>
      <div class="badge" id="mode">MODE: PAPER · LIVE: DISABLED</div>
    </div>
    <div>
      <button onclick="runDemo()">Run Paper Cycle</button>
      <button onclick="runBacktest()">Run Backtest</button>
      <button class="danger" onclick="killSwitch()">EMERGENCY STOP</button>
    </div>
  </header>
  <div class="grid">
    <section class="panel">
      <h2>16 AGENTS</h2>
      <div class="agents" id="agents"></div>
    </section>
    <section class="panel">
      <h2>ACCOUNT / MARKET</h2>
      <div class="metrics" id="metrics"></div>
      <div id="chartNote" style="margin-top:10px;color:var(--muted);font-size:.8rem">
        Candles & indicators served from /api/market/BTC-USD (server-side).
      </div>
      <pre id="market" style="font-size:.7rem;overflow:auto;max-height:240px;background:#0e1626;padding:8px;border-radius:8px"></pre>
    </section>
    <section class="panel">
      <h2>RISK</h2>
      <pre id="risk" style="font-size:.75rem;white-space:pre-wrap"></pre>
    </section>
    <section class="panel wide">
      <h2>AGENT COMMUNICATION / EVENTS</h2>
      <div id="timeline"></div>
    </section>
    <section class="panel wide">
      <h2>SYSTEM HEALTH</h2>
      <pre id="health" style="font-size:.75rem;white-space:pre-wrap"></pre>
    </section>
  </div>
  <script>
    const api = (path, opts) => fetch('/api'+path, opts).then(r => r.json());
    function renderAgents(agents) {
      const el = document.getElementById('agents');
      el.innerHTML = agents.map(a => `
        <div class="agent"><span><span class="dot ${a.status}"></span>${a.name}</span><span>${a.status}</span></div>
      `).join('');
    }
    function pushEvent(ev) {
      const t = document.getElementById('timeline');
      const div = document.createElement('div');
      div.className = 'evt';
      div.textContent = `${ev.timestamp || ''}  ${ev.event_type}  ${ev.agent_id || ''}  ${JSON.stringify(ev.payload || {}).slice(0,180)}`;
      t.prepend(div);
    }
    async function refresh() {
      const [agents, status, risk, health, market] = await Promise.all([
        api('/agents'), api('/system/status'), api('/risk'), api('/health'), api('/market/BTC-USD?bars=40')
      ]);
      renderAgents(agents);
      document.getElementById('mode').textContent =
        `MODE: ${status.TRADING_MODE} · LIVE: DISABLED · EQUITY: ${Number(status.equity).toFixed(2)}`;
      document.getElementById('risk').textContent = JSON.stringify(risk, null, 2);
      document.getElementById('health').textContent = JSON.stringify(health, null, 2);
      document.getElementById('metrics').innerHTML = `
        <div class="metric"><span>Equity</span>${Number(status.equity).toFixed(2)}</div>
        <div class="metric"><span>Agents</span>${status.agents_ready}</div>
        <div class="metric"><span>Signal Mode</span>${status.signal_mode}</div>`;
      document.getElementById('market').textContent = JSON.stringify({
        symbol: market.symbol,
        last: market.candles?.at(-1),
        rsi: market.indicators?.rsi_14?.at(-1)
      }, null, 2);
    }
    async function runDemo() {
      await api('/actions/paper/start', {method:'POST'});
      await api('/actions/demo-cycle', {method:'POST'}).catch(()=>{});
      await refresh();
    }
    async function runBacktest() {
      await api('/actions/run-backtest', {method:'POST'});
      await refresh();
    }
    async function killSwitch() {
      await api('/actions/kill-switch', {method:'POST'});
      await refresh();
    }
    function connectWs() {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws';
      const ws = new WebSocket(`${proto}://${location.host}/ws`);
      ws.onmessage = (m) => {
        const data = JSON.parse(m.data);
        if (data.type === 'event') pushEvent(data.event);
      };
      ws.onclose = () => setTimeout(connectWs, 1500);
    }
    refresh();
    connectWs();
    setInterval(refresh, 5000);
  </script>
</body>
</html>"""
