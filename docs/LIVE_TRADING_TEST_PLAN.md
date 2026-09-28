# Live Trading Test Plan

**Audit / plan only. Do not enable live trading to execute this plan yet.**

```text
TRADING_MODE=paper
LIVE_TRADING_ENABLED=false
Live Execution=DISABLED
```

Tests must proceed **stage by stage**. Do not skip.

---

## 1. Test environments

| Environment | Purpose | Real money |
|-------------|---------|------------|
| Mock exchange | Unit / deterministic logic | No |
| Paper exchange | Integration of risk→fill→learn | No |
| Exchange sandbox / testnet | Signed requests, fills without prod capital | No (venue fake funds) |
| Production API read-only | Balances/positions/market auth | No orders |
| Production API zero-size / min-notional dry validation | Payload correctness | Prefer **no submit**; if venue requires, use absolute minimum under Stage 5 controls |
| Controlled live | Tiny size, timeboxed | Yes (Stage 5) |

Coinbase and Delta sandbox availability differs by product/region — verify per venue
before Stage 4. If sandbox is unavailable, extend Stage 3–4 dry-run mocks and delay Stage 5.

---

## 2. Mapping stages → tests

### STAGE 0 — Backtest

| Test | Pass criteria |
|------|---------------|
| Unit backtest engine | Existing Phase 6 tests pass |
| Walk-forward | No look-ahead; metrics reproducible |
| Deterministic replay | Same inputs → same structural hash |
| Strategy regression | Champion not silently replaced |

**Command baseline:** `pytest tests/unit/test_phase6_backtest.py -q`

### STAGE 1 — Paper trading (local)

| Test | Pass criteria |
|------|---------------|
| Phase 5 safety matrix | Live adapters blocked; kill switch; stale; circuit breaker |
| RiskEngine limits | LLM cannot override |
| Paper demo cycle | Dashboard/CLI cycle executes paper only |
| AutonomousPaperLoop | Paper-only assert; idempotency; stale skip |
| Phase 8 learning safety | No live deploy; no hard-limit mutation |
| Phase 9 safety | `LIVE_TRADING_ENABLED=false` assertions |
| Full suite | 162+ passed, 0 failed (baseline at audit) |

**Command baseline:** `pytest -q`

### STAGE 2 — Cloud paper 24/7

| Test | Pass criteria |
|------|---------------|
| Container boot | Worker healthy; loop heartbeat |
| Restart recovery | State reload; no duplicate floods (idempotency) |
| Remote kill switch | Halts new paper orders within SLO |
| Log/metric pipeline | Heartbeat + errors visible |
| Soak | ≥72h paper soak without crash loops |
| Dashboard exposure | Not public unauthenticated |

### STAGE 3 — Production exchange read-only

| Test | Pass criteria |
|------|---------------|
| Secret injection | Keys never in image/logs |
| Balance/position read | Schema normalized; redacted logs |
| Permission negative test | Trade endpoint denied or unused |
| IP allowlist | Only NAT IP works |
| Failure injection | Revoked key → fail closed, no crash |

**Forbidden:** any `create_order` call in this stage.

### STAGE 4 — Order validation without submission

| Test | Pass criteria |
|------|---------------|
| Payload builder unit tests | Exact venue schema |
| Signature fixtures | HMAC/JWT match vendor vectors |
| Dry-run / preview | If venue supports; else offline validation |
| Idempotency key stability | Same intent → same client order id |
| Risk gate on live-shaped proposals | Reject oversized / disallowed |
| Shadow mode | Compare would-be orders vs paper for N days |

**Forbidden:** submitting live orders unless using an official sandbox labeled non-prod.

### STAGE 5 — Controlled live execution

| Test | Pass criteria |
|------|---------------|
| Dual control enablement | Two-person or break-glass procedure |
| Min size order | Fill or cancel path observed |
| Cancel path | Works under timeout |
| Kill switch cancels opens | Verified on venue |
| Daily loss halt | Triggered in drill (paper first, then live drill carefully) |
| Reconciliation | Internal vs exchange positions match |
| Timebox | Auto-disable after window |

### STAGE 6 — Autonomous live

| Test | Pass criteria |
|------|---------------|
| Multi-week Stage 5 metrics | Within risk envelopes |
| Chaos drills | Exchange 500s, WS drops, clock skew |
| DR restore | Backup restore tested |
| Post-incident learning | No automatic limit loosening |

---

## 3. Mandatory safety regressions (every stage)

Run on every deploy candidate:

```bash
pytest -q \
  tests/unit/test_phase5_safety.py \
  tests/safety \
  tests/unit/phase9 \
  tests/integration/phase9 \
  tests/safety/phase9 \
  tests/safety/learning \
  tests/safety/dashboard
```

Assert config:

```text
TRADING_MODE=paper          # until Stage 5 intentionally overridden in isolated env
LIVE_TRADING_ENABLED=false  # default images always false
```

Production Stage 5+ images may set live flags **only** via secret manager in a
dedicated project/account — never in default `main` config files.

---

## 4. What each harness proves

| Harness | Proves | Does not prove |
|---------|--------|----------------|
| Mock | Branching, errors, determinism | Venue quirks |
| Paper | Risk→fill→portfolio→learn | Real latency/liquidity |
| Sandbox | Auth + order state machine | Prod fee schedule / queue |
| Prod read-only | Auth + account schema | Order path |
| Zero-size / min live | Real accept/reject codes | Strategy expectancy |
| Full live | Real PnL path | Future regime stability |

---

## 5. Exit checklist before first Stage 5 order

- [ ] P0 backlog items from `LIVE_TRADING_READINESS.md` complete
- [ ] Stage 2 soak passed
- [ ] Stage 3 read-only passed for target venue
- [ ] Stage 4 shadow/dry-run passed
- [ ] Withdrawals disabled on API key
- [ ] IP allowlist active
- [ ] Kill switch drill passed
- [ ] On-call alerting verified
- [ ] Legal/compliance OK for venue/jurisdiction
- [ ] Max notional cap configured far below paper fantasy sizes

---

## 6. Baseline at audit time

Recorded after Phase 9 merge on `main` @ `29652f5`:

```text
Full suite: 162 passed / 0 failed
Live Execution: DISABLED
TRADING_MODE: paper
LIVE_TRADING_ENABLED: false
```

Re-run and update this section when the suite count changes.

## Production readiness suite

```bash
pytest -q tests/unit/production tests/safety/production
```
