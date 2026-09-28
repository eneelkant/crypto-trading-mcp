# Live Kill Switch

`LiveKillSwitch` wraps `KillSwitch`:

1. Block new orders
2. Attempt cancel-all when live_mode + canceller provided
3. Persist/emit event (redacted)
4. Alert
5. Remain active until operator-authorized clear

LLM cannot deactivate. Cancel failures → `OPEN_ORDER_CANCELLATION_FAILURE` while still blocking new orders.
