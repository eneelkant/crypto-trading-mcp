# Prediction Markets (Paper)

Phase 5 simulates `PREDICTION_CONTRACT` instruments locally.

## Contract model

- Outcomes: YES / NO
- Sides: BUY / SELL (including BUY_YES, SELL_YES, BUY_NO, SELL_NO)
- Price in `[0, 1]`
- Quantity, resolution date, resolution outcome, settlement value

## Settlement

```text
YES contract:
  resolved YES → settlement = 1
  resolved NO  → settlement = 0
```

Settlement is deterministic and driven only by the simulation dataset outcome.
No Polymarket or Kalshi APIs are called; adapters exist as future interfaces only.

## Ensemble attribution

Optional model weights (Grok / Claude / GPT / Gemini / DeepSeek) and edge vs market
probability are stored for later learning; they do not bypass risk controls.
