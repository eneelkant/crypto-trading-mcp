# Architecture Audit — crypto-trading-mcp

**Audit date:** 2026-09-24  
**Repository:** https://github.com/eneelkant/crypto-trading-mcp  
**Commit audited:** `aefae4f` (`main`)  
**Scope:** Phase 1 repository reconnaissance only. No live trading. No architecture implementation in this phase beyond this document.

**Disclaimer:** This software is experimental trading infrastructure. Cryptocurrency trading involves substantial risk. Past performance and backtesting do not guarantee future results. Live trading must remain disabled by default. Autonomous trading can result in financial loss.

---

## 1. Current Architecture

The repository is a **minimal read-only MCP (Model Context Protocol) server** implemented in Python 3.12+.

### How it works today

```text
MCP Client (Claude Desktop / Cursor / etc.)
        │  stdio transport
        ▼
FastMCP server  (crypto_trading_mcp.server)
        │
        ├── get_spot_price        → ccxt public fetch_ticker
        └── estimate_swap_profit  → pure local arithmetic
```

- Entry point: `python -m crypto_trading_mcp` → `src/crypto_trading_mcp/__main__.py` → `mcp.run(transport="stdio")`.
- Server definition: `src/crypto_trading_mcp/server.py` using `mcp.server.fastmcp.FastMCP`.
- Market data: **public** CCXT exchange instances with `enableRateLimit=True`. Default exchange id is **`kraken`**, not Coinbase.
- No authentication to exchanges, no order placement, no wallet access, no persistence, no agents, no LLM SDK usage.
- Packaging: setuptools via `pyproject.toml`; package under `src/crypto_trading_mcp`.
- Dependency intent beyond runtime is only sketched in `requirements/*.txt` stubs (not wired into `pyproject.toml` extras).

### Scale of the codebase

| Metric | Value |
|--------|-------|
| Non-git tracked files | 11 |
| Approximate LOC | ~166 total |
| Application modules | 1 meaningful (`server.py`, ~101 lines) |
| Tests | None |
| Docs (before this audit) | README only |

**Verdict:** Greenfield scaffold with a thin MCP surface. Almost all of the target multi-agent trading platform must be designed and built.

---

## 2. Current Components

| Component | Location | Purpose | Reusable? |
|-----------|----------|---------|-----------|
| Package metadata | `pyproject.toml` | Name, version, Python ≥3.12, core deps | Yes — extend carefully |
| Git ignore | `.gitignore` | Ignores `.venv`, `.env`, caches, logs | Yes — keep; expand for secrets/data |
| README | `README.md` | Setup, run, tool list, read-only disclaimer | Partially — replace with platform docs |
| MCP server | `src/crypto_trading_mcp/server.py` | FastMCP + 2 tools + DNS rebinding hosts | Partially — keep FastMCP pattern; redesign tools |
| Module entry | `src/crypto_trading_mcp/__main__.py` | `mcp.run(stdio)` | Yes |
| Package init | `src/crypto_trading_mcp/__init__.py` | Empty | Yes (placeholder) |
| Core deps list | `requirements/core.txt` | mcp, ccxt, httpx, python-dotenv | Yes as reference |
| AI deps stub | `requirements/ai.txt` | `tradingagents` | No until evaluated; not installed |
| Trading deps stub | `requirements/trading.txt` | `nautilus_trader` | Evaluate later; not installed |
| Backtest deps stub | `requirements/backtesting.txt` | vectorbt, backtrader | Evaluate later; not installed |
| RL deps stub | `requirements/rl.txt` | finrl | Defer; not required for core path |
| CCXT public market access | `_exchange()` + `get_spot_price` | Public ticker fetch | Yes as seed for market-data adapter |
| Fee/PnL estimate | `estimate_swap_profit` | Deterministic fee-aware profit math | Yes as seed for performance helpers |
| Transport security settings | FastMCP `TransportSecuritySettings` | DNS rebinding protection + host allowlist | Partially — review ngrok host |

---

## 3. Existing MCP Tools

### 3.1 `get_spot_price`

| Field | Detail |
|-------|--------|
| **Name** | `get_spot_price` |
| **Input** | `symbol: str` (e.g. `BTC/USD`); `exchange_id: str = "kraken"` |
| **Output** | `exchange`, `symbol`, `last_price`, `bid`, `ask`, `quote_volume`, `fetched_at` (ISO-8601 UTC), `note` |
| **Purpose** | Fetch latest public spot ticker via CCXT |
| **Read/write** | **Read-only** (public market data) |
| **Security implications** | No credentials used. Caller-controlled `exchange_id` instantiates any CCXT exchange by name — low risk while public-only, but must not later accept authenticated exchange construction from tool args. No rate-limit budgeting beyond CCXT defaults. |

### 3.2 `estimate_swap_profit`

| Field | Detail |
|-------|--------|
| **Name** | `estimate_swap_profit` |
| **Input** | `asset_amount`, `entry_price_usd`, `exit_price_usd`, optional `entry_fee_percent`, `exit_fee_percent`, `network_fee_usd` |
| **Output** | `gross_cost_usd`, `net_proceeds_usd`, `total_fees_usd`, `profit_usd`, `profit_percent`, `disclaimer` |
| **Purpose** | Local arithmetic estimate of net profit after fees |
| **Read/write** | **Read-only / compute-only** (no network, no exchange) |
| **Security implications** | Validates non-negative inputs and fee percentages &lt; 100. Does not execute trades. Safe as a calculator; must not be confused with live P&L accounting. |

### Tools that do **not** exist today

All target tools are missing: `get_market_data`, `get_market_regime`, `get_technical_analysis`, `get_sentiment`, `get_portfolio`, `get_positions`, `get_open_orders`, `propose_trade`, `validate_trade`, `execute_trade`, `cancel_order`, `get_trade_status`, `get_performance`, `get_risk_status`, `get_agent_status`, `get_learning_memory`, `run_backtest`, `run_paper_trade`, `activate_kill_switch`.

---

## 4. Existing Trading Capabilities

| Capability | Status |
|------------|--------|
| Public spot price (CCXT) | **Present** (default Kraken) |
| OHLCV / candles | **Absent** |
| Order book | **Absent** |
| Technical indicators | **Absent** |
| Portfolio / balances | **Absent** |
| Positions | **Absent** |
| Order create/cancel | **Absent** |
| Paper trading | **Absent** |
| Backtesting | **Absent** (deps named only) |
| Risk engine | **Absent** |
| Kill switch | **Absent** |
| Autonomous execution | **Absent** |
| Strategy / agents | **Absent** |

**Exact current trading functionality:** none beyond **reading public tickers** and **estimating hypothetical swap profit from caller-supplied prices**. The README correctly states the server does not store credentials, execute trades, or move funds.

---

## 5. Existing LLM Capabilities

| Provider / integration | Status in repo |
|------------------------|----------------|
| OpenAI | **Not present** |
| Anthropic | **Not present** |
| Gemini | **Not present** (`.gemini/` only in `.gitignore`) |
| Ollama | **Not present** |
| OpenAI-compatible endpoints | **Not present** |
| Mock LLM provider | **Not present** |
| LLM router | **Not present** |
| Agent ↔ model binding config | **Not present** |
| `tradingagents` (requirements stub) | Named in `requirements/ai.txt` only; **not imported, not depended in pyproject** |

**Verdict:** Zero LLM runtime integration. All multi-provider routing must be designed greenfield.

---

## 6. Existing Coinbase Integration

| Area | Status |
|------|--------|
| Authentication | **Absent** |
| Official Coinbase Advanced Trade API client | **Absent** |
| Market data via Coinbase | **Absent** (CCXT optional `exchange_id` could theoretically be set to a Coinbase id by caller, but there is no dedicated adapter, auth, or validation) |
| Account / balances | **Absent** |
| Orders | **Absent** |
| Positions | **Absent** |
| Sandbox / test support | **Absent** |
| Live trading support | **Absent** |
| Env vars (`COINBASE_API_KEY`, etc.) | **Absent** |
| `.env.example` | **Absent** |

**Missing (entire Coinbase surface):** adapter interface, credential loading, secret redaction, read-only mode, live mode gates (`TRADING_MODE`, `LIVE_TRADING_ENABLED`), order lifecycle, IP/permission guidance, separation of read-only vs trading credentials.

**Do not assume Coinbase trading exists.** It does not.

---

## 7. Current Security Risks

### Findings (no secret values disclosed)

| Risk | Location / type | Severity | Notes |
|------|-----------------|----------|-------|
| Hardcoded public API keys / tokens | **Not found** in tracked source | — | Grep for key/secret/token patterns found only README disclaimer + `.gitignore` |
| Private keys / wallet material | **Not found** | — | N/A |
| `.env` committed | **Not found** | — | `.env` is gitignored (good) |
| Missing `.env.example` | Repo root | Low | Operators lack a safe template |
| Ngrok host in allowlist | `server.py` `allowed_hosts` | Medium | Hardcodes `unknowing-humility-refinance.ngrok-free.dev` — environment-specific tunnel exposed in source; review/remove for production |
| Unauthenticated public CCXT | `get_spot_price` | Low (current) | Acceptable while public-only; dangerous if later extended to authenticated clients via tool args |
| No trading mode gates | Entire codebase | Informational | Safe today because no order APIs exist; must be built before any live path |
| No secret redaction logging layer | Absent | Medium (future) | Must be designed before Coinbase credentials exist |
| Requirements stubs pull heavy / opaque packages | `requirements/*.txt` | Low | Names only; risk if installed without review (`finrl`, `nautilus_trader`, etc.) |
| Arbitrary exchange id | Tool parameter | Low→High if auth added | Must never construct credentialed exchanges from untrusted tool input |

**Positive controls already present**

- Read-only product posture documented in README.
- No exchange credentials in code.
- `.env` ignored.
- DNS rebinding protection enabled on FastMCP.
- Input validation on fee/profit calculator.

**Required before live trading (not present):** dual flags (`TRADING_MODE=live` + `LIVE_TRADING_ENABLED=true`), deterministic risk engine outside LLM, kill switch, credential isolation from prompts/logs, paper/live adapter separation.

---

## 8. Current Testing

| Item | Status |
|------|--------|
| Test framework | **None configured** (no pytest/unittest layout, no `tests/` directory) |
| Existing tests | **None** |
| Coverage | **N/A** |
| CI | **None** (no `.github/workflows`) |
| How tests are executed | **N/A** |

### Missing tests (relative to target security suite)

1. Live trading disabled by default  
2. Paper mode cannot hit real order endpoints  
3. LLM cannot bypass Risk Engine  
4. LLM cannot change risk limits  
5. LLM cannot access API secrets  
6. Secrets never appear in logs  
7. Invalid orders rejected  
8. Excessive positions rejected  
9. Daily loss / drawdown limits  
10. Kill switch  
11. Duplicate order prevention  
12. Stale market data blocks trading  
13. Missing LLM → no new trades  
14. Exchange failure retry controls  

Also missing: unit tests for indicators, sizing, PnL, risk, fees, slippage, state machine; integration tests for MCP/LLM/exchange; E2E paper pipeline tests.

---

## 9. Missing Architecture

Comparison against the 16 target specialized agents / subsystems:

| Target component | Present? | Gap |
|------------------|----------|-----|
| Market Intelligence | Partial seed | Only last ticker; no OHLCV, regime, liquidity depth |
| Technical Analysis | **Missing** | Deterministic indicator engine required |
| Trend Agent | **Missing** | |
| Sentiment Agent | **Missing** | |
| On-Chain Agent | **Missing** | |
| Macro / Event Agent | **Missing** | |
| Strategy Agent | **Missing** | |
| Bull Analyst | **Missing** | |
| Bear Analyst | **Missing** | |
| Debate / Consensus | **Missing** | |
| Risk Manager (deterministic) | **Missing** | Critical safety boundary |
| Portfolio Manager | **Missing** | |
| Trade Planner | **Missing** | |
| Execution Agent | **Missing** | |
| Reflection / Learning | **Missing** | |
| Performance / Judge | **Missing** | |
| Orchestrator + state machine | **Missing** | |
| LLM Router + fallback | **Missing** | |
| Memory (SQL + vector) | **Missing** | |
| Backtest + walk-forward | **Missing** | |
| Paper exchange | **Missing** | |
| Coinbase adapter | **Missing** | |
| Dashboard / API / CLI (`trader`) | **Missing** | |
| Docker compose stack | **Missing** | |
| Strategy versioning | **Missing** | |

---

## 10. Proposed Architecture

```text
LLM Providers (Ollama / OpenAI / Anthropic / Gemini / OpenAI-compatible / Mock)
      ↓  (reasoning only; structured outputs)
Agent Layer (16 specialized agents)
      ↓  (message envelopes)
Agent Communication Bus + Audit Log
      ↓
Trading Orchestrator (state machine)
      ↓
Multi-Agent Consensus (weighted evidence; not simple majority)
      ↓
Deterministic Risk Engine  ←── hard limits from config (LLM cannot override)
      ↓
Execution Policy (mode gates, idempotency, stale-data checks)
      ↓
ExchangeAdapter
   ├── MockExchange
   ├── PaperExchange
   └── CoinbaseAdapter
      ↓
Order / Fill
      ↓
Position Monitor (deterministic stops / TP / reduce / halt)
      ↓
Reflection / Learning → Structured DB + Vector Memory
      ↓
Performance Engine → Strategy proposals (never auto-deploy to live)
```

### Inviolable rule

```text
LLM → Structured Signal → Consensus → Risk Engine → Execution Policy → Exchange Adapter
```

**Never:** `LLM → Coinbase` directly.

### Live autonomous path (future phases; disabled by default)

```text
SCAN → ANALYZE → DEBATE → DECIDE → RISK CHECK → SIZE → EXECUTE → MONITOR → CLOSE → REFLECT → LEARN
```

No `WAITING_FOR_HUMAN_APPROVAL` in the normal live path. Global controls remain: START / PAUSE / RESUME / HALT / KILL-SWITCH.

Default forever until explicitly enabled:

```env
TRADING_MODE=paper
LIVE_TRADING_ENABLED=false
```

---

## 11. Ollama / Apple M4 Architecture

**Target developer machine:** Apple M4, 16 GB RAM, arm64, macOS.

### Design principles

- Ollama is a **first-class default local provider**, not an afterthought.
- Do **not** require large local models, CUDA, or NVIDIA GPUs.
- Prefer small / quantized 7B–8B-class models configurable by env/YAML.
- Detect Ollama availability (`ollama list` / OpenAI-compatible `/v1` health) and fail closed for **new trades** if no usable reasoning model is available.
- Allow per-agent routing: cheap local models for interpretation; optional cloud models for heavier research.

### Suggested defaults (configurable, not hard-coded)

```env
LLM_PROVIDER=ollama
MODEL_NAME=qwen2.5:7b
OPENAI_API_BASE=http://localhost:11434/v1
```

Compatible optional local tags (operator choice): Qwen 2.5 7B / Qwen 3 8B-class, Llama 3.1 8B, Mistral 7B-class, small/distilled DeepSeek models.

### Resource posture on 16 GB

- Run **one** primary local chat model at a time for agent batches where possible.
- Keep vector DB and SQLite lightweight; avoid loading multiple 7B+ models concurrently.
- Dashboard and workers should be memory-conscious; prefer native macOS run without Docker for day-to-day M4 development.

---

## 12. Multi-LLM Architecture

Introduce `LLMRouter` with providers:

| Provider key | Transport |
|--------------|-----------|
| `ollama` | OpenAI-compatible base URL (local) |
| `openai` | Official OpenAI API |
| `anthropic` | Anthropic Messages API |
| `gemini` | Google Generative AI API |
| `openai_compatible` | Arbitrary base URL + API key |
| `mock` | Deterministic fixtures for tests |

### Capabilities

- Per-agent `{provider, model}` overrides in `config/agents.yaml`.
- Optional fallback chain: primary → secondary → **Safe Mode (no new trades)**.
- Structured output validation (JSON schema / pydantic); retries then fail closed.
- Never place secrets in prompts; never send exchange credentials to any provider.
- Latency, model id, and version recorded on every agent message envelope.

Agents depend only on an abstract `LLMClient` interface, never on a vendor SDK directly.

---

## 13. Autonomous Trading Architecture

### Intended live flow (Phase 10+; not implemented now)

```text
Market Data → Agents → Bull/Bear → Consensus → Deterministic Risk Engine
  → Trade Planner → Automatic Execution → Coinbase → Position Monitoring
```

### Hard controls outside the LLM (config-owned)

- Max position size / %  
- Max portfolio exposure  
- Max daily loss  
- Max drawdown  
- Max trade size / order value  
- Max slippage  
- Max trades per day  
- Allowed trading pairs  
- Minimum confidence / risk-reward  
- Emergency kill switch / circuit breakers  

### Mode gates (mandatory before any adapter can place real orders)

```text
Refuse real orders unless:
  TRADING_MODE == live
  AND LIVE_TRADING_ENABLED == true
  AND system state != HALTED
  AND Risk Engine available and APPROVE
  AND market data fresh
  AND LLM reasoning available (for new discretionary trades)
```

**Phase 1 constraint:** keep `LIVE_TRADING_ENABLED=false`; do not implement live execution yet.

---

## 14. Backtesting Architecture

```text
Historical OHLCV (immutable store)
      ↓
Feature / indicator computation (deterministic, causal only)
      ↓
Agent / strategy signals (as-of timestamp; no future bars)
      ↓
Simulated execution (fees, slippage, sizing, stops, TP)
      ↓
Portfolio accounting + metrics
      ↓
Train / Validation / Out-of-Sample split
      ↓
Walk-forward windows
      ↓
Artifact: dataset id, ranges, params, strategy version, agent versions, models, fees, slippage
```

### Anti-leakage rules

- Indicators computed only from data ≤ decision timestamp.  
- No peeking at future closes for entries/exits.  
- OOS and walk-forward held out from parameter selection.  
- LLM calls in backtests must be recorded or replaced with replayed/cached decisions to keep runs reproducible when using non-deterministic models.

---

## 15. Paper Trading Architecture

```text
TRADING_MODE=paper
        │
        ▼
PaperExchange (in-process simulated matching)
        │
        ├── Orders / fills / fees / slippage
        ├── Portfolio & P&L
        └── Same ExchangeAdapter interface as live
```

### Isolation requirements

- Paper path **must not** import or call Coinbase order create/cancel methods.  
- Prefer separate adapter class + factory selection by mode (not a boolean inside Coinbase client).  
- UI/CLI must display prominently: `TRADING MODE: PAPER` / `REAL MONEY: DISABLED`.

---

## 16. Coinbase Architecture

```text
ExchangeAdapter (protocol)
 ├── MockExchange      # unit/integration tests
 ├── PaperExchange      # simulated autonomous loop
 └── CoinbaseAdapter   # official Advanced Trade API auth
```

### Interface (target)

`get_balance`, `get_positions`, `get_market_price`, `get_orderbook`, `create_order`, `cancel_order`, `get_order`, `get_open_orders`.

### Credential architecture

| Credential class | Use |
|------------------|-----|
| READ_ONLY | Balances, market, open orders |
| TRADING | Order place/cancel only; withdrawals disabled |
| WALLET | Never treated as ordinary API key; avoid in this system |

Secrets via env only (`COINBASE_API_KEY`, `COINBASE_API_SECRET`, …). Never in git, README, memory, prompts, or logs. Prefer IP allowlisting and trading-only keys with withdrawals disabled.

**Phase order:** read-only validation → sandbox/test if available → live autonomous only after safety tests pass.

---

## 17. Memory Architecture

```text
Structured DB (SQLite default; PostgreSQL optional)
  - trades, orders, fills, portfolio snapshots
  - agent messages / decisions
  - risk events, kill-switch events
  - strategy versions + deployment status
  - model performance / calibration

Vector store (ChromaDB or equivalent)
  - market fingerprints
  - reflections
  - winning / losing pattern embeddings
```

### Retrieval path

```text
Current Market → Fingerprint → Vector Search → Similar Historical Trades
  → Reflection Memory → Agent Context
```

Learning **proposes** strategy/prompt/weight changes; deployment requires proposal → backtest → OOS → paper → version → deploy. Never auto-edit production trading code.

---

## 18. Proposed Directory Structure

Proposed tree (create incrementally across phases; **do not create all files in Phase 1**):

```text
crypto-trading-mcp/
├── README.md
├── pyproject.toml
├── .env.example
├── .gitignore
├── config/
│   ├── trading.yaml
│   ├── agents.yaml
│   ├── risk.yaml
│   └── llm.yaml
├── docs/
│   ├── ARCHITECTURE_AUDIT.md          # this document
│   ├── ARCHITECTURE.md
│   ├── AGENTS.md
│   ├── LLM_PROVIDERS.md
│   ├── LOCAL_MAC_SETUP.md
│   ├── BACKTESTING.md
│   ├── BACKTESTING_METHODOLOGY.md
│   ├── PAPER_TRADING.md
│   ├── COINBASE.md
│   ├── SECURITY.md
│   ├── RISK_MANAGEMENT.md
│   ├── MCP_TOOLS.md
│   ├── MEMORY.md
│   ├── LEARNING.md
│   ├── AUTONOMOUS_TRADING.md
│   ├── OPERATIONS.md
│   ├── TROUBLESHOOTING.md
│   └── IMPLEMENTATION_STATUS.md
├── requirements/
│   ├── core.txt
│   ├── ai.txt
│   ├── trading.txt
│   ├── backtesting.txt
│   └── rl.txt
├── src/crypto_trading_mcp/
│   ├── __init__.py
│   ├── __main__.py
│   ├── server.py                      # MCP tool registration (thin)
│   ├── cli/
│   │   └── trader.py                  # `trader` CLI
│   ├── config/
│   │   └── settings.py
│   ├── llm/
│   │   ├── router.py
│   │   ├── providers/
│   │   └── fallback.py
│   ├── agents/
│   │   ├── base.py
│   │   ├── registry.py
│   │   ├── messages.py
│   │   └── implementations/          # 16 agents
│   ├── orchestration/
│   │   ├── orchestrator.py
│   │   ├── state_machine.py
│   │   └── consensus.py
│   ├── market/
│   │   ├── data.py
│   │   ├── indicators.py              # deterministic only
│   │   └── regime.py
│   ├── risk/
│   │   ├── engine.py
│   │   ├── limits.py
│   │   └── circuit_breakers.py
│   ├── portfolio/
│   │   ├── accounting.py
│   │   └── performance.py
│   ├── execution/
│   │   ├── planner.py
│   │   ├── policy.py
│   │   └── engine.py
│   ├── exchange/
│   │   ├── base.py
│   │   ├── mock.py
│   │   ├── paper.py
│   │   └── coinbase.py
│   ├── backtest/
│   │   ├── engine.py
│   │   └── walk_forward.py
│   ├── memory/
│   │   ├── db.py
│   │   └── vector.py
│   ├── learning/
│   │   ├── reflection.py
│   │   └── proposals.py
│   ├── monitoring/
│   │   └── positions.py
│   └── api/
│       └── app.py                     # dashboard backend
├── dashboard/                         # frontend (later phase)
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── e2e/
│   └── security/
├── Dockerfile
└── docker-compose.yml
```

---

## 19. Implementation Plan

| Phase | Focus | Outcome | Live trading? |
|-------|-------|---------|---------------|
| **1 — Architecture** | This audit; baseline docs; defaults locked to paper/disabled | Shared design | No |
| **2 — Agent framework** | Registry, message protocol, orchestrator, state machine, LLM client interface | Runnable agent skeleton with mock LLM | No |
| **3 — LLM / Ollama** | Router, Ollama detection, M4-friendly defaults, fallback → safe mode | Local reasoning works without cloud | No |
| **4 — Market intelligence** | OHLCV, deterministic indicators, regime, sentiment interfaces | Market tools + TA without LLM inventing numbers | No |
| **5 — Multi-agent consensus** | Strategy, Bull, Bear, Consensus | Structured BUY/SELL/HOLD signals | No |
| **6 — Risk engine** | Deterministic limits, circuit breakers, kill switch persistence | LLM cannot override limits | No |
| **7 — Backtesting** | Fees/slippage/accounting; no look-ahead; walk-forward | Objective strategy metrics | No |
| **8 — Paper trading** | Isolated PaperExchange + full autonomous loop | End-to-end without real money | No |
| **9 — Coinbase read-only** | Auth, balances, market, open orders | Validated read path | No |
| **10 — Autonomous live** | Dual flags + full safety suite green | Automatic execution under risk controls | Only if explicitly enabled |
| **11 — Learning** | Reflections, vector memory, proposals with validation gate | Improve without auto-deploying code | As configured |
| **12 — Dashboard** | Portfolio, agents, timeline, learning views | Operator visibility | As configured |

### Phase 1 recommended repo changes (minimal)

1. Add `docs/ARCHITECTURE_AUDIT.md` (this file).  
2. Keep application code unchanged except where required for docs packaging.  
3. Optionally add stub `.env.example` with `TRADING_MODE=paper` and `LIVE_TRADING_ENABLED=false` in a later micro-step after approval.  
4. Do **not** add live order code, Coinbase trading credentials wiring, or autonomous live loops yet.

---

## 20. Do Not Implement Live Trading Yet

Explicit Phase 1 controls:

```text
LIVE_TRADING_ENABLED=false   # default must remain false
TRADING_MODE=paper           # intended default once config exists
```

- Do not place real orders.  
- Do not modify production Coinbase credentials.  
- Do not create autonomous live execution in this phase.  
- Do not remove the current read-only MCP tools until replacements are ready and tested.

---

## Appendix A — Inventory of audited paths

```text
.gitignore
README.md
pyproject.toml
requirements/ai.txt
requirements/backtesting.txt
requirements/core.txt
requirements/rl.txt
requirements/trading.txt
src/crypto_trading_mcp/__init__.py
src/crypto_trading_mcp/__main__.py
src/crypto_trading_mcp/server.py
docs/ARCHITECTURE_AUDIT.md   # added by Phase 1
```

## Appendix B — Reuse vs replace summary

| Keep / reuse | Replace / redesign | Build new |
|--------------|--------------------|-----------|
| FastMCP stdio server pattern | Tool surface (expand + separate read/write) | Full agent platform |
| CCXT public ticker helper | Default-Kraken-centric API as sole market path | ExchangeAdapter hierarchy |
| Deterministic fee math idea | Standalone-only profit estimate as “trading” | Risk, portfolio, execution, memory |
| `.gitignore` `.env` rule | Hardcoded ngrok allowlist host | LLMRouter, Ollama, configs, tests, CLI, dashboard |
| Python ≥3.12 package layout | Stub requirements as implicit architecture | Paper + backtest + Coinbase |

---

## Appendix C — Stop condition

Phase 1 deliverable is this audit document and the architectural recommendations above. **Implementation of Phases 2–12 awaits explicit approval.**
