# Self-Learning Engine (Phase 8)

Paper-mode self-learning subordinate to the deterministic RiskEngine.

## Lifecycle

```text
Trade close → post-mortem → classify → memory → Brier/calibration
→ drift → reflection → (optional) retrain → walk-forward / OOS
→ champion/challenger → proposal → explicit deployment gate
```

No automatic live deployment. `LIVE_TRADING_ENABLED` remains false.

## Config

`config/self_learning.yaml`

## CLI

```bash
trader learning status
trader learning calibration
trader learning memory
trader learning models
trader learning proposals
trader learning retrain
trader learning rollback
```

## Safety

Learning may reduce Kelly/confidence multipliers. It cannot disable kill switch,
raise hard risk limits, place exchange orders, or enable live trading.
