# Strategies

## Purpose

Phase 4 adds a **versioned strategy reference** used as structured domain knowledge.

```text
STRATEGY REFERENCE
        ↓
DETERMINISTIC FEATURE ENGINE
        ↓
AI ANALYSIS / INTERPRETATION
        ↓
CONSENSUS
        ↓
TRADE PLAN
        ↓
DETERMINISTIC RISK ENGINE
```

This is **not** a profitability claim and does **not** enable live trading.

Defaults remain:

```env
TRADING_MODE=paper
LIVE_TRADING_ENABLED=false
```

## Repository layout

| Path | Role |
|------|------|
| `strategies/multi_model_po3_vwap_strategy.json` | Reference strategy file |
| `src/crypto_trading_mcp/strategy/schema.py` | Pydantic schema + config hash |
| `src/crypto_trading_mcp/strategy/repository.py` | `StrategyRepository`, `StrategyKnowledgeService` |
| `src/crypto_trading_mcp/strategy/features.py` | Deterministic model features |
| `config/strategy_agent_map.yaml` | Model → agent mapping |

## Versioning

Each loaded strategy becomes a `StrategyRecord`:

- `strategy_id` (e.g. `multi_model_po3_vwap`)
- `version` (e.g. `1.0.0`)
- `config_hash` (SHA-256 of canonical JSON)
- `enabled_models`
- `created_at`
- `status` (`reference` / `candidate` / `paper` / `disabled`)

History is not overwritten when the same id/version already exists with a different hash.

## Multi-Model PO3 & VWAP strategy (v1.0.0)

Reference specification combining:

| Model | Name | Notes |
|-------|------|-------|
| M1 | PO3 Sweep & Rejection | Liquidity sweep vs PDH/PDL with ADX/EMA confirmation |
| M2 | VWAP Reclaim | Displacement reclaim aligned with 4H bias |
| M3 | Order Flow Absorption | Requires CVD; **UNAVAILABLE** without order-flow provider |
| M4 | ICT FVG | HTF sweep + LTF MSB + FVG confluence |

### Agent mapping

Configured in `config/strategy_agent_map.yaml`.

- M1 → market, technical, trend, strategy, bull, bear
- M2 → technical, trend, strategy
- M3 → market, technical, strategy
- M4 → market, technical, trend, strategy, bull, bear

## Knowledge layer

`StrategyKnowledgeService.knowledge_bundle()` exposes metadata, filters, risk blocks, and enabled models to agents.

**No LLM fine-tuning / weight updates in Phase 4.**

## Deterministic features

Calculated in Python (never by the LLM):

EMA 9/21/50/200, ADX 11, VWAP, ATR, volume multipliers, swing highs/lows, PDH/PDL/PMH/PML, Fibonacci, MSB, FVG.

Each feature is tagged:

`CALCULATED | UNAVAILABLE | INVALID | STALE`

CVD/order-flow uses `OrderFlowProvider`; default is `UNAVAILABLE` (M3 cannot confirm).

## Multi-timeframe + look-ahead

Execution 5m, model 15m, bias 240m.

Only **closed** candles are used (`only_closed_candles`). Incomplete HTF bars cannot influence earlier signals.
