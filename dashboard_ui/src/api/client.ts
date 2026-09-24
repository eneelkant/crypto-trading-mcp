export type AgentView = {
  agent_id: string;
  name: string;
  role: string;
  status: string;
  provider: string;
  model: string;
  confidence?: number | null;
  last_decision?: Record<string, unknown> | null;
  last_error?: string | null;
};

export type DashboardEvent = {
  event_id: string;
  timestamp: string;
  event_type: string;
  agent_id?: string | null;
  symbol?: string | null;
  payload?: Record<string, unknown>;
};

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, init);
  if (!res.ok) {
    throw new Error(`API ${path} failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const dashboardApi = {
  health: () => api<{ status: string }>("/health"),
  system: () => api<Record<string, unknown>>("/system/status"),
  agents: () => api<AgentView[]>("/agents"),
  events: (limit = 100) => api<DashboardEvent[]>(`/events?limit=${limit}`),
  risk: () => api<Record<string, unknown>>("/risk"),
  portfolio: () => api<Record<string, unknown>>("/portfolio"),
  performance: () => api<Record<string, unknown>>("/performance"),
  market: (symbol = "BTC-USD") => api<Record<string, unknown>>(`/market/${symbol}?bars=120`),
  backtests: () => api<Record<string, unknown>>("/backtests"),
  walkForward: () => api<Record<string, unknown>>("/walk-forward"),
  benchmarks: () => api<Record<string, unknown>>("/benchmarks"),
  llm: () => api<Record<string, unknown>>("/llm/providers"),
  mcp: () => api<Record<string, unknown>[]>("/mcp/activity"),
  healthFull: () => api<Record<string, unknown>>("/health"),
  systemHealth: async () => {
    const res = await fetch("/api/system/status");
    return res.json();
  },
  post: (path: string) => api<Record<string, unknown>>(path, { method: "POST" }),
  learningStatus: () => api<Record<string, unknown>>("/learning/status"),
  learningMemory: () => api<Record<string, unknown>>("/learning/memory"),
  learningCalibration: () => api<Record<string, unknown>>("/learning/calibration"),
  learningModels: () => api<Record<string, unknown>>("/learning/models"),
  learningProposals: () => api<Record<string, unknown>>("/learning/proposals"),
  learningDrift: () => api<Record<string, unknown>>("/learning/drift"),
  learningAudit: () => api<Record<string, unknown>>("/learning/audit"),
};
