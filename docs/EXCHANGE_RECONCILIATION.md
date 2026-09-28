# Exchange Reconciliation

`ExchangeReconciliationService` compares local vs exchange snapshots.

States: RECONCILED, DRIFT_DETECTED, RECONCILIATION_FAILED, EXCHANGE_UNAVAILABLE.

Unhealthy reconciliation → `allows_new_live_orders=false`.
