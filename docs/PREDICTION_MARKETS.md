# Prediction Markets (Paper)

Simulation only. No Polymarket/Kalshi connectivity.

## Contract

`PREDICT/{market_id}/{YES|NO}` with price/probability in `[0, 1]`.

## Settlement model

- Dataset supplies `winning_outcome` (`YES`/`NO`).
- Winning contract settles to `1.0`; losing to `0.0`.
- Outcomes are never invented by the LLM.

## Edge / ensemble attribution

Trades may record:

`market_probability`, `model_probability`, `edge`, provider weights, individual predictions, Brier history.

This is instrumentation — **not** a claim of accuracy.
