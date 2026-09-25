# Analysis Agents (Phase 3)

This document describes the first ten analytical / decision-support agents.

**None of these agents can execute trades.** There is no order placement path in Phase 3.

Defaults:

```text
TRADING_MODE=paper
LIVE_TRADING_ENABLED=false
REAL MONEY=DISABLED
```

## Shared framework (Phase 2 foundation)

| Piece | Module |
|-------|--------|
| Message envelope | `agents/messages.py` (`AgentMessage`) |
| Base agent | `agents/base.py` |
| Registry | `agents/registry.py` |
| LLM router | `llm/` (`mock`, `ollama`, `openai`, `anthropic`, `gemini`, `openai_compatible`) |
| Execution context | `orchestration/context.py` |
| State machine | `orchestration/state_machine.py` |
| Orchestrator | `orchestration/__init__.py` |

Pipeline order:

```text
market_intelligence
 → technical_analysis
 → trend
 → sentiment
 → on_chain
 → macro_event
 → strategy
 → bull
 → bear
 → consensus
```

States used: `IDLE → SCANNING → ANALYZING → DEBATING → IDLE`  
No `WAITING_FOR_HUMAN_APPROVAL`. No execution states in this phase.

---

## Agent catalog

### 1. Market Intelligence (`market_intelligence`)

See `docs/MARKET_INTELLIGENCE.md`.

### 2. Technical Analysis (`technical_analysis`)

| | |
|--|--|
| **Inputs** | Deterministic indicator bundle + market snapshot |
| **LLM role** | Interpret signals; must not invent indicator numbers |
| **Outputs** | bullish/bearish/neutral signals, trend strength, momentum, volatility, confidence, reasoning |
| **Failure** | Missing/stale market → `NO_TRADE` |

### 3. Trend (`trend`)

| | |
|--|--|
| **Inputs** | EMA/SMA structure from indicators |
| **Deterministic** | short/medium/long direction + alignment + regime_change seed |
| **LLM role** | Narrative interpretation of provided structure |
| **Outputs** | short_term, medium_term, long_term, alignment, regime_change, confidence |

### 4. Sentiment (`sentiment`)

| | |
|--|--|
| **Provider** | `SentimentProvider` (default: `UnavailableSentimentProvider`) |
| **Behavior** | Returns `UNAVAILABLE` when no source is configured |
| **Rule** | Never fabricate news/social sentiment |

### 5. On-Chain (`on_chain`)

| | |
|--|--|
| **Provider** | `OnChainProvider` (default unavailable) |
| **Rule** | Never fabricate whale/flow/network metrics |

### 6. Macro / Event (`macro_event`)

| | |
|--|--|
| **Provider** | `MacroEventProvider` (default unavailable) |
| **Future inputs** | CPI/FOMC, regulatory, exchange incidents, protocol events |
| **Rule** | Unavailable must be explicit |

### 7. Strategy (`strategy`)

Consumes analysis agents and emits a **non-executable hypothesis**:

- market_regime, direction, strategy_type
- entry/exit/invalidation conditions
- time_horizon, confidence
- supporting / contradicting evidence

If market intelligence is stale/unavailable → `direction=NO_TRADE`.

### 8. Bull Analyst (`bull`)

Independent strongest LONG case.

Does **not** receive Bear agent output.

### 9. Bear Analyst (`bear`)

Independent strongest SHORT case.

Does **not** receive Bull agent output.

### 10. Debate / Consensus (`consensus`)

| | |
|--|--|
| **Inputs** | All prior agent payloads |
| **Decisions** | `LONG` \| `SHORT` \| `NEUTRAL` \| `NO_TRADE` |
| **Method** | Weighted evidence scores; contested debates become `NEUTRAL` |
| **Hard rule** | Stale/missing critical market data → `NO_TRADE` |
| **Output** | decision, confidence, supporting_agents, disagreement_summary, missing_information, invalidating_conditions |

Consensus preserves disagreement rather than blindly averaging.

---

## Failure matrix

| Failure | New trade hypothesis |
|---------|----------------------|
| Stale market data | `NO_TRADE` |
| Missing OHLCV/ticker | `NO_TRADE` |
| Sentiment unavailable | Continue; listed in `missing_information` |
| On-chain unavailable | Continue; listed in `missing_information` |
| Macro unavailable | Continue; listed in `missing_information` |
| LLM unavailable / malformed JSON | Agent error envelope; no execution |
| Live flags enabled | Orchestrator refuses (Phase 3 hard block) |

---

## CLI

```bash
trader status
trader agents
trader analyze BTC/USD
```

`trader analyze` runs the full analytical pipeline and never places orders.
