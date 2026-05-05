# Phase 4 Shadow Target Model Report

Generated: 2026-05-05 UTC
Branch: `codex/v13-phase2-expectancy`
Tool: `scripts/phase4_shadow_target_model.py`

## Verdict

Do not promote the `close_return_h5` target.

The Phase 3 label screen correctly identified `close_return_h5` as cleaner than
the current one-bar target, and the Phase 4 classifier screen shows a better
selected proxy return. However, the candidate fails the balanced-accuracy delta
gate: `+0.0189` versus the required `+0.0300`. That is enough to keep studying
the target, not enough to change live ML influence.

## Evidence Command

```bash
./venv/bin/python scripts/phase4_shadow_target_model.py
```

Outputs:

- `artifacts/phase4_shadow_target_model/summary_shadow_target_model.json`
- `artifacts/phase4_shadow_target_model/shadow_target_model_metrics.csv`

## Results

| Target | Model | Validation Samples | Balanced Accuracy | Selected Samples | Selected Proxy Mean Bps | Selected Win Rate |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `close_return_h1` | `logistic_regression_balanced` | `15,245` | `0.5141` | `5` | `-13.2101` | `0.4000` |
| `close_return_h5` | `logistic_regression_balanced` | `15,228` | `0.5330` | `17` | `17.6274` | `0.5294` |

## Gate Results

| Gate | Observed | Threshold | Passed |
| --- | ---: | ---: | --- |
| Validation sample floor | `15,228` | `200` | Yes |
| Balanced accuracy delta | `0.0189` | `0.0300` | No |
| Selected proxy bps delta | `30.8375` | `1.0000` | Yes |
| Live promotion blocked by Phase 4 scope | `shadow_only` | replay and live shadow required | No |

## Interpretation

The candidate is directionally interesting but still weak. The selected-sample
set is tiny (`17` rows), so the attractive proxy bps could disappear once fills,
slippage, exits, risk sizing, and opportunity cost are included. The model is
also trained on simple OHLCV features for auditability; it is a screen, not a
production model.

## Recommendation

Keep ML isolated from main-book ranking, confidence, and sizing. The next
acceptable step is a replay-backed shadow target experiment that uses the same
candidate target while preserving the current live target in production.
