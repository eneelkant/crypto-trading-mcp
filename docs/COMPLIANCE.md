# Compliance

Pre-trade gate before Risk Engine / PaperExchange.

```text
Trade Plan → Compliance Policy → Risk Engine → PaperExchange
```

Rejection reason: `COMPLIANCE_BLOCKED` (and specific codes).

## Tax simulation

Configurable parameters in `config/compliance.yaml` (VDA/TDS/transaction tax).

**This is a simulation model, not tax advice, and not immutable legal truth.**

VDA-style rules apply only to configured asset classes (default: CRYPTO).
