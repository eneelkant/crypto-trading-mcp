# Walk-Forward Validation

```text
Historical Dataset
 → Training Window
 → Validation Window
 → Out-of-Sample Test Window
 → Step forward
 → Repeat
```

## Configuration

```yaml
walk_forward:
  enabled: true
  training_days: 180
  validation_days: 60
  test_days: 60
  step_days: 30
```

Short fixtures may use bar-based windows automatically.

## Partitions

Every result is labeled:

- `TRAIN`
- `VALIDATION`
- `OUT_OF_SAMPLE`

Do not report validation performance as out-of-sample.
Do not optimize parameters using the final OOS window.

## Purpose

Measure stability across time. Phase 6 does **not** auto-select parameters or deploy.
