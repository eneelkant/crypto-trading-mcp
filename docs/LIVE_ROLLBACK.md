# Live Rollback

1. Activate kill switch (cancels opens)
2. Set LIVE_TRADING_ENABLED=false in secret manager
3. Demote stage to STAGE_4 or STAGE_2
4. Preserve ledger + logs for post-mortem
5. Do not delete evidence
