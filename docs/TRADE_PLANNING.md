# Trade Planning

## Flow

```text
Strategy Reference
 → Deterministic Features / Model Evaluation
 → Analysis Agents
 → Consensus
 → TradePlanner
 → RiskEngine
 → APPROVED / REJECTED
```

No `execute_trade` in Phase 4.

## TradePlanner

Consumes consensus + feature bundle + equity.

Produces:

- strategy id/version
- model_ids
- side, entry, quantity, notional
- stop / take-profit
- risk amount, fees, slippage estimate
- risk/reward
- confidence / invalidation conditions

Position sizing is risk-based:

```text
risk_amount = equity × effective_risk_percent
quantity = risk_amount / |entry - stop|
```

then capped by global trade/position limits.

## CLI

```bash
trader propose BTC-USD
trader propose BTC-USD --json
```

Output includes model statuses, confluence, consensus, plan, and risk decision.
