# Order Lifecycle

Phase 5 paper orders follow a deterministic state machine.

## States

```text
CREATED (= NEW)
  → VALIDATED
  → SUBMITTED (= OPEN)
  → PARTIALLY_FILLED
  → FILLED

Any open state may also transition to:
  CANCELLED | REJECTED | EXPIRED
```

## Order types

- `MARKET` — fill immediately at market ± simulated slippage
- `LIMIT` — rest until market trades through the limit
- `STOP` / `STOP_LIMIT` — trigger only when stop condition is reached
- `TAKE_PROFIT` — protective profit exit; triggers when target is reached

## Deterministic IDs

Order and fill IDs are derived from `session_id`, sequence, symbol, side, and quantity so
repeated replay runs produce identical identifiers.

## Lifecycle events

```text
ORDER_SUBMITTED
ORDER_FILLED / ORDER_PARTIALLY_FILLED
ORDER_CANCELLED
ORDER_REJECTED
STOP_TRIGGERED
POSITION_UPDATED
POSITION_CLOSED
PAPER_PNL_UPDATED
```

Orders are never assumed filled merely because a strategy requested them.
