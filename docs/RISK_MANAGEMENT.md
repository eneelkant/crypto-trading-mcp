# Risk Management

## Principle

The Risk Engine is **deterministic Python**.

The LLM cannot override limits.

When strategy and global configs conflict, the **stricter (safer)** bound wins.

Example:

```text
GLOBAL max_daily_loss = 3%
STRATEGY max_daily_loss = 5%
EFFECTIVE = 3%
```

## Configuration

- Global: `config/risk.yaml`
- Strategy: `strategies/*.json` → `risk_management`

## Checks

Position size, trade size, exposure, daily loss, drawdown, trade count, cooldown, slippage, leverage, pair allowlist, liquidity, stale data, stop-loss presence/validity, minimum R:R, kill switch, confidence, model presence.

## Reason codes

See `RiskReasonCode` in `src/crypto_trading_mcp/risk/models.py` (`RISK_OK`, `POSITION_LIMIT_EXCEEDED`, … `NO_VALID_MODEL`).

## Circuit breakers

Daily loss, drawdown, trade frequency, stale data, provider outage flags, kill switch.

When tripped: `TRADING_HALTED` — no proposal can be approved for execution (and Phase 4 has no execution path).

## Kill switch

```python
activate_kill_switch(reason)
deactivate_kill_switch(operator_authorized=True)  # LLM cannot authorize
get_kill_switch_status()
```

## CLI

```bash
trader risk
```

Shows global, strategy, and effective limits.
