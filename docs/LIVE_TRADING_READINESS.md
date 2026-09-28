# Live Trading Readiness

**Audit date:** 2026-09-28  
**Repository:** `eneelkant/crypto-trading-mcp`  
**Commit audited:** `29652f5` (`main`, Phase 9 merged)  
**Scope:** Architecture audit and staged readiness plan only.

```text
TRADING_MODE=paper
LIVE_TRADING_ENABLED=false
Live Execution=DISABLED
```

**This document does not enable live trading.** No real orders, credentials, or
Phase 10 implementation are authorized by this audit.

---

## 1. Executive verdict

| Area | Status | Notes |
|------|--------|-------|
| Exchange adapters | Partial | Paper/Mock complete; Coinbase/Delta public+read stubs; live `create_order` hard-blocked |
| Credentials / secrets | Not ready | Env-only; no secret manager, rotation, or permission policy enforcement |
| Wallet / account | Partial | CEX account balances via API intended; no private keys required for spot CEX |
| Market data | Partial | REST/CCXT + gateway/cache/stale gates; WebSocket disabled; no funding/OI/liq |
| RAG / external data | Partial | Fail-closed providers; internal learning retrieval only |
| LLM providers | Good (paper) | Mock/Ollama/OpenAI/Anthropic/Gemini/compatible present |
| Agents | Partial | 10 analysis agents registered; risk/portfolio/execution are deterministic services |
| Risk | Strong (paper) | Deterministic RiskEngine + kill switch; must remain authoritative for live |
| Live execution path | Blocked | No code path places real exchange orders today |
| Cloud / 24×7 | Not ready | Local process + file/memory persistence; no deploy stack |
| Monitoring | Partial | EventBus/dashboard; no prod alerting/SLO/pager |

**Overall readiness for controlled live trading: FAIL (expected).**  
Platform is ready for **paper / staged preparation**, not Stage 5+.

---

## 2. Current end-to-end path (as implemented)

```text
Market Data (MarketDataGateway / PublicCCXT / Mock)
  → Agents (10 analysis agents via TradingOrchestrator) OR deterministic paper path
  → Consensus (ConsensusAgent or synthetic consensus in AutonomousPaperLoop)
  → Strategy selection / TradePlan
  → CompliancePolicy
  → RiskEngine (+ CorrelationFilter, KillSwitch, stale-data gates)
  → Portfolio / sizing checks
  → Trade Planner (TradePlan)
  → PaperTradingEngine.execute_approved_plan
  → PaperExchange.create_order
  → Fill → Portfolio update → LearningEngine
```

**AutonomousPaperLoop note:** Phase 9 continuous loop uses a **deterministic paper
path** and does **not** run the full 16-agent LLM debate on every tick. Full debate
remains available via `TradingOrchestrator.analyze` / `propose` and dashboard demo
cycles.

---

## 3. Where live execution can currently occur

| Location | Can place real orders today? |
|----------|------------------------------|
| `PaperExchange.create_order` | No — simulated fills only |
| `MockExchange` | No |
| `CoinbaseAdapter.create_order` | No — requires live flags **and** still raises `LiveExecutionBlocked` |
| `DeltaExchangeIndiaAdapter.create_order` | No — same hard block |
| `PolymarketAdapter` / `KalshiAdapter` | No — stub raises `LiveExecutionBlocked` |
| `create_exchange("coinbase"\|…)` in paper | No — factory raises unless `allow_read_adapters` / stub |
| MCP `execute_trade` / paper tools | Paper only; live gated by settings |
| CLI `trader` cycle/paper commands | Paper only |
| Dashboard demo cycle | Paper only |
| Learning engine | Cannot place orders or raise hard risk limits |
| AutonomousPaperLoop | Asserts `TRADING_MODE=paper` and `LIVE_TRADING_ENABLED=false` |

**Conclusion:** There is **no accidental live order path** under default settings.
Enabling live later requires **new implementation**, not flipping a flag alone
(Phase 9 `create_order` still refuses even if flags were true).

---

## 4. Agent architecture (target 16 vs implemented)

Target architecture (Phase 1 audit) names **16 specialized agents/subsystems**.

### Registered LLM / analysis agents (10)

| Agent | Role | Influences trade? |
|-------|------|-------------------|
| MarketIntelligence | Snapshot interpretation | Information → consensus |
| TechnicalAnalysis | Indicator interpretation | Information → consensus |
| Trend | Multi-horizon trend | Information → consensus |
| Sentiment | External sentiment | Information (fail-closed if unavailable) |
| OnChain | On-chain metrics | Information (fail-closed) |
| MacroEvent | Macro/events | Information (fail-closed) |
| Strategy | Direction / regime / plan hints | Influences proposal inputs |
| BullAnalyst | Bull case | Influences consensus |
| BearAnalyst | Bear case | Influences consensus |
| Consensus | BUY/SELL/HOLD decision | **Direct trade influence** (signal only) |

### Deterministic subsystems (counted in the “16” target)

| Subsystem | Implementation | Influences trade? |
|-----------|----------------|-------------------|
| Risk Manager | `RiskEngine` + `KillSwitch` | **Hard gate** (approve/reject) |
| Portfolio Manager | `PortfolioManager` | Exposure / cash constraints |
| Trade Planner | `execution.planner.TradePlan` | Sizing / stops / structure |
| Execution | `PaperTradingEngine` / future live adapter | Order submission |
| Reflection / Learning | `LearningEngine` | Post-trade; cannot override risk |
| Performance / Judge | `performance.metrics` + learning calibration | Evaluation only |

**Consensus** occurs in `ConsensusAgent` (orchestrator) or synthetic consensus in the
paper loop. **Deterministic risk** always runs before paper execution. **Execution**
today is paper-only.

---

## 5. Risk invariants that must hold for live

LLM / agent output **must never override**:

- max risk per trade / position / portfolio exposure
- max daily loss / max drawdown
- max trade size / leverage / slippage
- allowed instruments
- correlation limits (`CorrelationFilter`)
- cooldown / trade-count limits
- kill switch (`STOP` file + `KillSwitch`)
- stale market data protection
- exchange / API failure circuit breakers

Current `RiskEngine` enforces these for paper proposals. Live readiness requires the
**same engine** on the live path with exchange-truth portfolio snapshots.

---

## 6. Staged deployment model (do not skip)

| Stage | Name | Goal | Exit criteria |
|-------|------|------|---------------|
| **0** | Backtest | Historical validation, walk-forward | Metrics pass thresholds; no live keys |
| **1** | Paper trading (local) | Full risk+execution on PaperExchange | Safety tests green; replay deterministic |
| **2** | Cloud paper 24/7 | Continuous AutonomousPaperLoop in cloud | Health, restarts, alerts, durable state |
| **3** | Production read-only | Authenticated balance/position/order **reads** | Credentials in secret manager; no submit |
| **4** | Order validation w/o submit | Build signed payloads; dry-run / exchange preview | Idempotency + schema parity proven |
| **5** | Controlled live | Tiny size, allowlist, human kill, timeboxed | Loss limits; dual control; rollback plan |
| **6** | Autonomous live | Continuous live under hard gates | Multi-week Stage 5 evidence |

Current production code supports **Stage 0–1** well, Stage 2 partially (loop exists,
cloud packaging missing), Stage 3+ **not implemented**.

---

## 7. What must change before live trading

1. Implement real Coinbase/Delta `create_order` / `cancel_order` / `get_order` behind
   multi-gate policy (mode + flag + allowlist + kill switch + risk + human/stage gate).
2. Secret manager integration; never env files on disk in cloud.
3. Exchange-truth portfolio reconciliation (not paper ledger alone).
4. Durable order idempotency store (not process-local set).
5. WebSocket (or equivalent) market data with reconnect + stale gates under load.
6. Full-agent cycle option for live (or explicit policy that deterministic path is OK).
7. Cloud deploy, monitoring, alerting, backups, DR kill-switch procedure.
8. Sandbox/testnet + staged promotion gates in CI/CD.
9. Compliance / jurisdiction review for Delta India and Coinbase.
10. Remove or re-gate any “allow_read_adapters” misuse that could confuse operators.

## 8. What can remain unchanged

- `RiskEngine` limit semantics (extend, do not weaken)
- PaperExchange for Stage 0–2
- Learning safety: no auto live deployment, no hard-limit mutation
- Fail-closed external data providers
- EventBus redaction patterns
- Default `TRADING_MODE=paper` / `LIVE_TRADING_ENABLED=false`
- MCP/CLI separation of read vs write tools (expand carefully)

## 9. Dangerous assumptions

1. “Setting `LIVE_TRADING_ENABLED=true` is enough” — **false**; order APIs unfinished.
2. “Paper PnL ≈ live PnL” — fees, latency, partial fills, liquidations differ.
3. “Autonomous loop runs full debate” — **false** today (deterministic paper path).
4. “16 agents all registered as BaseAgent” — **false**; six are services.
5. “CEX trading needs wallet private keys” — **false** for custodial CEX spot/perp API.
6. “In-memory / `.runtime` JSON is durable enough for live” — **false**.
7. “Dashboard bind to 0.0.0.0 is fine” — dangerous without auth.
8. “Read credentials imply safe” — read keys can still leak balances/PII; trade keys worse.
9. “Mock LLM readiness equals production LLM readiness” — latency/cost/failure differ.
10. “Correlation filter always runs with enough history” — may no-op if series short.

---

## 10. Implementation backlog

### P0 BLOCKER (must complete before any Stage 5 capital)

1. Multi-gate live execution policy object (mode, flag, stage, kill switch, allowlist).
2. Real authenticated order submit/cancel/status for one venue (prefer sandbox first).
3. Secret manager + no secrets in git/env files in prod.
4. Durable idempotency + order intent ledger (crash-safe).
5. Exchange balance/position reconciliation before each live order.
6. Hard kill switch that cancels open live orders (procedure + API).
7. Staged promotion controls preventing Stage skip in config/deploy.
8. Alerting on kill switch, stale data, API errors, daily loss.

### P1 REQUIRED (Stage 2–4)

1. Cloud packaging (container + process supervisor + health endpoints).
2. Durable DB for sessions, orders, fills, learning memory.
3. Coinbase Advanced Trade signing for authenticated reads.
4. Delta India position/order history completeness.
5. WebSocket market feed with reconnect/backoff.
6. Read-only production credential runbook (Stage 3).
7. Dry-run order validation pipeline (Stage 4).
8. Wire full orchestrator debate into continuous loop **or** document/enforce deterministic-only policy.
9. CI gates: safety tests must pass before any live-config deploy.
10. Operator runbooks: halt, restart, credential rotation.

### P2 IMPORTANT

1. Funding / open interest / liquidation feeds for perps.
2. External news/macro/on-chain providers with provenance tagging.
3. Vector DB option for learning retrieval at scale.
4. IP allowlisting automation + key permission lint.
5. Dashboard auth when exposed beyond localhost.
6. Chaos tests: exchange timeout, partial fill, duplicate ack.
7. Jurisdiction/compliance automation hooks.
8. Multi-venue failover for market data.

### P3 OPTIONAL

1. Additional venues (Polymarket/Kalshi beyond stubs).
2. Advanced portfolio optimization.
3. Multi-region active-active.
4. Hardware key / HSM for signing (if required by policy).
5. Fully agentized Risk/Execution as BaseAgent wrappers (thin; keep deterministic core).

---

## 11. Related documents

- `docs/PRODUCTION_CREDENTIALS.md`
- `docs/WALLET_AND_ACCOUNT_ARCHITECTURE.md`
- `docs/DATA_AND_RAG_ARCHITECTURE.md`
- `docs/CLOUD_24X7_ARCHITECTURE.md`
- `docs/LIVE_TRADING_TEST_PLAN.md`
- `docs/SECURITY.md`
- `docs/PAPER_TRADING_SAFETY.md`
- `docs/EXCHANGE_ARCHITECTURE.md`
- `docs/PHASE9.md`

---

## 12. Explicit non-goals of this audit

- Do **not** start Phase 10 implementation from this document alone.
- Do **not** enable `LIVE_TRADING_ENABLED`.
- Do **not** create or request production API keys in-repo.
- Do **not** store credentials in Git.
