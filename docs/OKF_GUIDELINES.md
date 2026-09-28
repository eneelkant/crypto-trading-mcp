# OKF Trading Guidelines

Canonical **Open Knowledge Format (OKF)** specification for this repository.

| Field | Value |
|-------|-------|
| Spec version | `0.2.0` |
| Bundle | `crypto-bot-trading-guidelines` |
| Path | `okf/okf_crypto_bot_guidelines.json` |
| Status | APPROVED |
| Executable | **No** — guideline specification only |

Compute the active hash:

```bash
python -c "from crypto_trading_mcp.okf import load_and_validate_okf; print(load_and_validate_okf()['hash'])"
```

Or via MCP tool: `get_okf_status`.

## Pipeline

```text
OKF JSON
   ↓
OKF Validator
   ↓
Configuration Resolver (stricter-wins vs system risk)
   ↓
Risk / Strategy Constraints
   ↓
Agent Proposal
   ↓
Deterministic Risk Engine
   ↓
Trade Intent
   ↓
Stage Gate
   ↓
Execution Policy
   ↓
Exchange Adapter
```

Authority hierarchy (LLM is lowest):

```text
HARD SYSTEM SAFETY
    ↓
LIVE TRADING / STAGE GATES
    ↓
KILL SWITCH
    ↓
EXCHANGE VALIDATION
    ↓
RECONCILIATION
    ↓
DETERMINISTIC RISK ENGINE
    ↓
OKF STRATEGY CONSTRAINTS
    ↓
AGENT/LLM PROPOSAL
    ↓
TRADE PLAN
    ↓
EXECUTION POLICY
```

An LLM must never override an OKF or RiskEngine constraint.

## Conflict resolution

When OKF and system settings differ, the **stricter** deterministic safety value wins.
Conflicts are emitted with reason codes such as `OKF_SYSTEM_CONFLICT_MAX_RISK_PER_TRADE_PCT`.
Nothing is silently overwritten.

Examples:

- OKF max risk/trade = 1%, system = 0.5% → effective **0.5%**
- OKF max drawdown = 10%, system = 8% → effective **8%**

## Risk constraints (OKF baseline)

| Control | OKF | Notes |
|---------|-----|-------|
| Max risk per trade | 1% | ATR/stop-distance sizing |
| Max daily loss | 5% | Circuit breaker |
| Max portfolio drawdown | 10% | Circuit breaker |
| Kill switch file | `STOP` | Halt + flatten path |
| Kelly | Quarter Kelly (0.25×) | Cannot bypass hard limits |
| Brier threshold | 0.25 | Degrades Kelly/confidence only |
| Memory block | > 80% failure match | Fail closed if memory unavailable |
| Low turnover | max 8 trades/day, 5-bar cooldown | Blocks uncontrolled scalping styles |

Position sizing:

```text
Position_Qty = (Account_Equity * Risk_Percent) / abs(Entry_Price - Stop_Loss_Price)
```

Stop loss required; zero denominator rejected; quantity still passes RiskEngine.

## Strategy registry (M1–M5)

| ID | Type | Notes |
|----|------|-------|
| `M1_PO3_SWEEP` | Liquidity reversal | PDH/PDL/PMH/PML + ADX>21 + vol>1.3× |
| `M2_VWAP_RECLAIM` | Trend continuation | VWAP reclaim, displacement >0.3 ATR, 4H bias |
| `M3_ICT_FVG_SWING` | Smart money | 4H sweep → 15m MSB → FVG → ≥0.5 Fib limit |
| `M4_PREDICTION_MARKET_AI` | Probability arb | Ensemble edge >0.04, VADER ≥0 (labels only) |
| `M5_MOMENTUM_BREAKOUT` | Momentum | Donchian 20, vol ≥1.5×, trail 2× ATR |

Signals produce decision objects only. **No strategy submits exchange orders.**

Strategy JSON: `strategies/okf/`. Runtime registry: `crypto_trading_mcp.okf.strategies.OKFStrategyRegistry`.

## Self-learning integration

- Post-mortem on trade close with OKF failure categories
- Pre-trade memory gate (cosine feature similarity; block if > 80%)
- Brier recalibration (below / equal / above 0.25)
- ML: XGBoost optional; Phase 8 fallback retained; never claim XGBoost active when unavailable
- Learning cannot modify hard risk limits, kill switch, or place orders

## TradingView webhook

Optional secure webhook (`crypto_trading_mcp.webhook.tradingview`):

- Secret from env `TRADINGVIEW_WEBHOOK_SECRET` only (never `YOUR_SECRET_KEY`)
- HTTPS (localhost HTTP allowed for local dev)
- Secret verification, timestamp skew, nonce replay protection
- Idempotency key, rate limit, schema / symbol / action / qty / price validation
- Audit logging with secret redaction
- Creates **trade intents only** — same RiskEngine / KillSwitch / Stage / LiveGate / Reconciliation / ExecutionPolicy path

## Delta Exchange India

OKF lists production API `https://api.india.delta.exchange` (HMAC-SHA256, 5s skew, 10k/5min) as **reference configuration**.

This repository keeps:

- Stage 2 Delta **testnet/sandbox** architecture
- `TRADING_MODE=paper`
- `LIVE_TRADING_ENABLED=false`
- Production credentials absent
- Production orders disabled

See `docs/DELTA_EXCHANGE_INDIA.md` and `docs/STAGE2_CLOUD_PAPER.md`.

## Tax / compliance disclaimer

India jurisdiction metadata (flat CGT 30%, TDS 1%, no loss offset) is stored as **OKF reference assumptions only**.

- Not personalized tax advice
- Must be reviewed against current applicable law before any production use
- Tax fields do **not** alter execution logic unless a separately tested business rule is implemented

## Validate OKF

```bash
python -c "from crypto_trading_mcp.okf import load_and_validate_okf, validate_okf; \
r=load_and_validate_okf(); print(r['version'], r['hash']); \
assert r['executable'] is False"
pytest tests/unit/okf tests/safety/okf -q
```

## Stage defaults vs Stage 2

Repository default stage remains `STAGE_1_LOCAL_PAPER` (`config/trading_stages.yaml`).
The Stage 2 cloud-paper / Delta sandbox stack is activated only through explicit
entrypoints (`cloud_paper`, sandbox runtime, or compose `TRADING_STAGE`).
OKF integration does not auto-promote stages. See `docs/STAGE2_CLOUD_PAPER.md`.

## Limitations

- OKF does not enable live trading
- OKF does not store production secrets
- Semantic similarity for memory is cosine-over-features, not claimed NLP accuracy
- XGBoost is optional
- External LLM provider names in M4 are configuration labels; local/mock providers are used for tests
- Real Delta testnet authentication/trading is NOT claimed by OKF or Stage 2 harness tests
