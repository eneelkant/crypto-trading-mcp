# Order Intent Ledger

`OrderIntent` persisted to durable store **before** submission.

Collections: `order_intents`, `order_idempotency`.

Restart-safe duplicate prevention via `OrderIntentLedger`.

Related models: OrderSubmission, OrderStatusRecord, FillRecord, CancelRequest, CancelResult.
