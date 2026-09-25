# Operations (Paper)

## Mode

Always label outputs as **PAPER**. Live execution is disabled in this phase.

## CLI

```bash
trader status
trader paper start
trader paper stop
trader paper status
trader paper reset
trader paper restart
trader paper run BTC/USD --price 50000
trader paper trades
trader paper orders
trader paper portfolio
trader paper performance
trader paper replay --symbol BTC/USD --price 100
trader portfolio
trader risk
trader trades
trader performance
```

## Kill switch

Create `STOP` in the repository root to halt new paper orders. Remove it and run
`trader paper restart` for a safe restart.

## Persistence

Paper state can be held in-memory (`InMemoryPaperStore`) or SQLite (`SqlitePaperStore`).
The store interface is intentionally abstract for a later PostgreSQL backend.

## Sessions

Each run is attributable to a `PaperSession` (e.g. `PAPER_SESSION_2026_001`) with
starting capital, config hash, strategy versions, and status.

## Observability

Structured events include `MARKET_DATA_RECEIVED`, `RISK_VALIDATED`, `ORDER_SUBMITTED`,
`ORDER_FILLED`, `POSITION_CLOSED`, `CIRCUIT_BREAKER_TRIGGERED`, `KILL_SWITCH_TRIGGERED`.
Secrets and credentials are never logged.

## Limitations

- No authenticated exchange execution
- No real wallet transactions
- Prediction markets are local simulations only
- Tax/TDS figures are simulations, not legal advice
