# Phase 3 ML Target Redesign Report

Generated: 2026-05-04
Branch: `codex/v13-phase2-expectancy`
Tool: `scripts/phase3_ml_target_redesign.py`

## Verdict

Do not change live ML influence.

The current one-bar target is very noisy on cached intraday bars: `73.0%` of
samples are inside the 5 bps noise band and only `1.5%` are tradeable by a 25
bps threshold. The best offline label screen is `close_return_h5`, which cuts
noise to `45.4%` and raises tradeable-move density to `7.2%`.

That makes a 5-bar target a research candidate for a future training/shadow
experiment, not a live promotion. ML remains disabled for main-book influence.

## Evidence Command

```bash
./venv/bin/python scripts/phase3_ml_target_redesign.py
```

Outputs:

- `artifacts/phase3_ml_target_redesign/summary_ml_target_redesign.json`
- `artifacts/phase3_ml_target_redesign/ml_target_aggregate.csv`
- `artifacts/phase3_ml_target_redesign/ml_target_per_symbol.csv`

## Aggregate Results

| Target | Samples | Positive Rate | Noise/Neutral | Tradeable Move | Momentum Lift | Score |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `close_return_h5` | `59,950` | `50.4%` | `45.4%` | `7.2%` | `-5.2%` | `0.027992` |
| `close_return_h10` | `59,840` | `51.4%` | `35.3%` | `13.0%` | `-3.9%` | `0.024929` |
| `mfe_mae_symmetric_h10` | `9,732` | `49.6%` | `77.7%` | `22.3%` | `-3.8%` | `0.009434` |
| `close_return_h1` | `60,038` | `47.9%` | `73.0%` | `1.5%` | `-2.5%` | `0.007678` |
| `mfe_mae_long_h10` | `59,840` | `8.1%` | `72.9%` | `27.1%` | `-0.7%` | `0.000647` |

## Interpretation

The current one-bar label is too close to microstructure noise for a main-book
ML signal. The 5-bar and 10-bar close-return labels are cleaner and more
balanced, but this script only measures label quality and simple momentum
separability; it does not train a replacement model.

MFE/MAE labels are conceptually closer to trade outcomes, but the current
thresholds produce either sparse symmetric samples or a highly imbalanced
long-success label. They need a separate target-design pass before training.

## Recommendation

Keep ML isolated. The next ML work should train a shadow-only candidate model
on `close_return_h5` and compare it against the current target on the same
holdout, replay, and live shadow telemetry. Do not let it affect ranking,
confidence, or sizing until it beats the existing production promotion gates.
