# Data and RAG Architecture

**Audit only. Live trading remains disabled.**

```text
TRADING_MODE=paper
LIVE_TRADING_ENABLED=false
```

---

## 1. Principle

External information may enter the agent system **only** through typed providers that:

1. Tag **source classification**
2. Preserve **provenance** (URL/id/timestamp when available)
3. **Fail closed** when data is missing (no fabricated news/on-chain/macro)
4. Never grant LLMs direct exchange order credentials
5. Never let retrieved text override RiskEngine limits

Inviolable path:

```text
External/Internal Data → Typed Provider → Agent context → Consensus → Risk → Execution
```

Never:

```text
Raw web scrape → LLM → ExchangeAdapter.create_order
```

---

## 2. Source classification

| Class | Description | Current status |
|-------|-------------|----------------|
| `MARKET_DATA` | Trades, candles, books, funding, OI | REST/CCXT + gateway; WS hook off; funding/OI/liq missing |
| `FUNDAMENTAL_DATA` | Issuer/token fundamentals, filings-like facts | Not integrated |
| `NEWS` | Headlines, articles | Not integrated (Sentiment fails closed) |
| `SOCIAL` | Social sentiment streams | Not integrated (fail closed) |
| `ON_CHAIN` | Whale/flow/TVL metrics | Provider protocol exists; default UNAVAILABLE |
| `MACRO` | Economic calendar, rates, regime events | Provider protocol exists; default UNAVAILABLE |
| `RESEARCH` | Long-form research / PDFs | Not integrated |
| `INTERNAL_MEMORY` | Prior trades, post-mortems, embeddings | LearningEngine retrieval (deterministic vectors) |
| `PREDICTION_MARKET` | Polymarket/Kalshi-style contracts | Paper prediction book; live adapters stubbed |

---

## 3. Market-data architecture (as-is)

```text
PublicCCXTMarketData / MockMarketData
        ↓
RestMarketDataProvider
        ↓
MarketDataGateway (TTL cache, health, stale gate)
        ↓
WebSocketMarketFeed (disabled by default)
```

| Capability | Status |
|------------|--------|
| REST ticker / OHLCV / order book | Yes (public) |
| Candles → indicators | Yes (`market.indicators`) |
| Trades tape | Partial / via CCXT depending on venue |
| Funding rates | Missing |
| Open interest | Missing |
| Liquidation data | Missing |
| Volume analytics | Basic via candles |
| Exchange health | `ExchangeHealth` + `MarketDataHealth` |
| Stale-data handling | Yes (`max_age_seconds`, blocks new trades) |

Config: `config/market_data.yaml`.

---

## 4. How agents consume data today

| Agent | Data classes | Behavior if missing |
|-------|--------------|---------------------|
| MarketIntelligence | MARKET_DATA | Uses snapshot; errors surface |
| TechnicalAnalysis | MARKET_DATA | Deterministic indicators + LLM interpretation |
| Trend | MARKET_DATA | Multi-horizon structure |
| Sentiment | NEWS / SOCIAL | `UnavailableSentimentProvider` → UNAVAILABLE |
| OnChain | ON_CHAIN | Unavailable by default |
| MacroEvent | MACRO | Unavailable by default |
| Strategy / Bull / Bear / Consensus | Mix of above + INTERNAL_MEMORY (via learning context in dashboard/demo) | Contested → NEUTRAL bias |
| Learning retrieval | INTERNAL_MEMORY | Continues with champion if empty |

Providers live in `src/crypto_trading_mcp/providers/external.py`.

---

## 5. Internal memory / RAG (as-is)

| Piece | Implementation |
|-------|----------------|
| Trade memory records | `learning.models.TradeLearningRecord` |
| Feature embedding | Deterministic L2-normalized vectors (`embeddings.py`) |
| Similarity | Cosine similarity |
| Retrieval | `learning.retrieval.build_learning_context` |
| External vector DB | **None** |
| Document chunk RAG for news/PDFs | **None** |

This is **structured case retrieval**, not a general document RAG stack.

### Safe future RAG pattern

```text
Ingest (NEWS/RESEARCH/...)
  → classify + sanitize + store with provenance
  → embed (model versioned)
  → retrieve top-k with similarity + recency filters
  → wrap as ProviderResult(status=AVAILABLE|UNAVAILABLE)
  → agent prompt uses evidence bullets only
  → consensus may cite sources
  → RiskEngine ignores prose; uses numeric proposal fields only
```

---

## 6. LLM architecture (providers)

Implemented in `src/crypto_trading_mcp/llm/providers.py`:

| Provider | Class | Notes |
|----------|-------|-------|
| Mock | `MockLLMProvider` | Default; deterministic fixtures |
| Ollama | `OllamaProvider` | OpenAI-compatible local `/v1` |
| OpenAI | `OpenAICompatibleProvider` | Official API base |
| OpenAI-compatible | same | Custom `OPENAI_API_BASE` |
| Anthropic | `AnthropicProvider` | Messages API |
| Gemini | `GeminiProvider` | generateContent |
| Router | `LLMRouter` | Fail-closed with optional fallbacks |

Config: `config/llm.yaml` (all agents default to `mock`).

**Local fallback:** mock always present; Ollama usable when running. Router fails closed so discretionary trades should not open on total LLM outage (`fail_closed_on_llm_error`).

---

## 7. Gaps before live / cloud paper with real intel

1. No production news/social/on-chain connectors.
2. No source allowlist or content-safety filter for RAG.
3. No vector DB / retention policy for documents.
4. Continuous loop does not yet ingest learning context into a full debate each tick.
5. Prediction-market live data not wired.
6. Funding/OI needed before serious perp live trading on Delta.

---

## 8. Readiness

| Item | Status |
|------|--------|
| MARKET_DATA REST | Partial → Good for paper |
| Fail-closed alt data | Good pattern |
| INTERNAL_MEMORY retrieval | Good for paper learning |
| Document RAG | Missing |
| Live intel feeds | Missing |

**RAG/Data readiness: PARTIAL.**
