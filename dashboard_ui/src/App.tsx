import { useCallback, useEffect, useState } from "react";
import { dashboardApi, type AgentView } from "./api/client";
import { MarketChart } from "./components/MarketChart";
import { useEventStream } from "./hooks/useEventStream";

type Tab = "portfolio" | "backtests" | "walkforward" | "llm" | "mcp" | "health";

export default function App() {
  const [agents, setAgents] = useState<AgentView[]>([]);
  const [status, setStatus] = useState<Record<string, unknown>>({});
  const [risk, setRisk] = useState<Record<string, unknown>>({});
  const [market, setMarket] = useState<Record<string, unknown>>({});
  const [panel, setPanel] = useState<Record<string, unknown>>({});
  const [tab, setTab] = useState<Tab>("portfolio");
  const { connected, events } = useEventStream();

  const refresh = useCallback(async () => {
    const [a, s, r, m] = await Promise.all([
      dashboardApi.agents(),
      dashboardApi.system(),
      dashboardApi.risk(),
      dashboardApi.market("BTC-USD"),
    ]);
    setAgents(a);
    setStatus(s);
    setRisk(r);
    setMarket(m);
  }, []);

  useEffect(() => {
    refresh().catch(console.error);
    const id = window.setInterval(() => refresh().catch(() => undefined), 4000);
    return () => window.clearInterval(id);
  }, [refresh]);

  useEffect(() => {
    const load = async () => {
      if (tab === "portfolio") setPanel(await dashboardApi.portfolio());
      if (tab === "backtests") setPanel(await dashboardApi.backtests());
      if (tab === "walkforward") setPanel(await dashboardApi.walkForward());
      if (tab === "llm") setPanel(await dashboardApi.llm());
      if (tab === "mcp") setPanel({ activity: await dashboardApi.mcp() });
      if (tab === "health") setPanel(await dashboardApi.health());
    };
    load().catch(console.error);
  }, [tab, events.length]);

  const candles = (market.candles as Array<{
    timestamp: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
  }>) || [];

  return (
    <div className="app-shell">
      <header className="header">
        <div>
          <h1>AI TRADING COMMAND CENTER</h1>
          <div className="badge">
            SYSTEM: {(status.system as string) || "…"} · MODE: PAPER · LIVE: DISABLED · WS:{" "}
            {connected ? "ONLINE" : "RECONNECTING"} · SIGNAL: DETERMINISTIC
          </div>
        </div>
        <div className="header-actions">
          <button onClick={() => dashboardApi.post("/actions/demo-cycle").then(refresh)}>
            Run Paper Cycle
          </button>
          <button onClick={() => dashboardApi.post("/actions/run-backtest").then(refresh)}>
            Run Backtest
          </button>
          <button onClick={() => dashboardApi.post("/actions/run-walk-forward").then(refresh)}>
            Walk-Forward
          </button>
          <button className="danger" onClick={() => dashboardApi.post("/actions/kill-switch").then(refresh)}>
            EMERGENCY STOP
          </button>
        </div>
      </header>

      <div className="layout">
        <section className="panel">
          <h2>16 Agents</h2>
          <div className="agents">
            {agents.map((a) => (
              <div className="agent-row" key={a.agent_id}>
                <span>
                  <span className={`dot ${a.status}`} />
                  {a.name}
                </span>
                <span>{a.status}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="panel">
          <h2>BTC-USD Live Chart</h2>
          <div className="metrics" style={{ marginBottom: 10 }}>
            <div className="metric">
              <span>Equity</span>
              <strong>{Number(status.equity ?? 0).toFixed(2)}</strong>
            </div>
            <div className="metric">
              <span>Agents Ready</span>
              <strong>{String(status.agents_ready ?? 0)}</strong>
            </div>
            <div className="metric">
              <span>Exchange</span>
              <strong>PAPER</strong>
            </div>
          </div>
          <MarketChart candles={candles} />
        </section>

        <section className="panel">
          <h2>Risk</h2>
          <pre>{JSON.stringify(risk, null, 2)}</pre>
        </section>

        <section className="panel wide">
          <h2>Agent Communication / Decision Events</h2>
          <div className="timeline">
            {events.slice(0, 40).map((e) => (
              <div className="evt" key={e.event_id}>
                <time>{e.timestamp}</time>
                <strong>{e.event_type}</strong>
                {e.agent_id ? ` · ${e.agent_id}` : ""}
                <div>{JSON.stringify(e.payload ?? {}).slice(0, 220)}</div>
              </div>
            ))}
          </div>
        </section>

        <section className="panel wide">
          <h2>Portfolio · Backtests · LLM · MCP · Health</h2>
          <div className="tabs">
            {(
              [
                ["portfolio", "Portfolio"],
                ["backtests", "Backtests"],
                ["walkforward", "Walk-Forward"],
                ["llm", "LLM"],
                ["mcp", "MCP"],
                ["health", "Health"],
              ] as Array<[Tab, string]>
            ).map(([id, label]) => (
              <button
                key={id}
                className={`tab ${tab === id ? "active" : ""}`}
                onClick={() => setTab(id)}
              >
                {label}
              </button>
            ))}
          </div>
          <pre>{JSON.stringify(panel, null, 2)}</pre>
        </section>
      </div>
    </div>
  );
}
