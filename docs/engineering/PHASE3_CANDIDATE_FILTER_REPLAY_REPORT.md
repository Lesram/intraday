# Phase 3 Candidate-Filter Counterfactual Report

Generated: 2026-05-04
Branch: `codex/v13-phase2-expectancy`
Tool: `scripts/phase3_candidate_filter_replay.py`

## Verdict

Do not promote any live gate from this slice.

This run is a closed-trade counterfactual, not a fill-level market replay. It
answers: "If we had skipped trades matching this slice, what would the realized
closed-trade PnL stream have looked like?" It does not model freed capital,
replacement trades, changed learner state, or intraday execution differences.

The cleanest next candidate is a shadow/fill-level replay of `skip_conf_45_55`.
It improved the last-100 and last-50 windows with reasonable trade reduction and
better drawdown. `skip_alpha_breakout_chop` is also worth replaying, but it
removes too much of the last-100 stream unless refined. `skip_conf_55_65` looks
excellent all-time but weakens in the last-50 and flips negative in the last-25,
so it should stay observation-only.

## Evidence Command

```bash
./venv/bin/python scripts/phase3_candidate_filter_replay.py --out-dir artifacts/phase3_candidate_filter_replay
```

Outputs:

- `artifacts/phase3_candidate_filter_replay/summary_candidate_filter_replay.json`
- `artifacts/phase3_candidate_filter_replay/candidate_filter_results.csv`

## Baseline

| Metric | Value |
| --- | ---: |
| Strategy trades | `501` |
| Total PnL | `-$778.90` |
| Mean PnL | `-$1.55` |
| Win rate | `32.9%` |
| Profit factor | `0.6923` |
| Max drawdown | `-$985.93` |
| Gross profit | `$1,752.10` |
| Gross loss | `$2,531.00` |

## Scenario Results

### All-Time

All-time results are legacy-polluted. They are useful for ranking hypotheses,
not for live decisions.

| Scenario | Skipped | PnL delta | Trade reduction | DD delta | Verdict |
| --- | ---: | ---: | ---: | ---: | --- |
| `skip_conf_45_65` | `196` | `+$525.47` | `39.1%` | `+$444.20` | Hypothesis only; too broad. |
| `skip_conf_55_65` | `140` | `+$487.51` | `27.9%` | `+$445.09` | Legacy-heavy; recent evidence weakens. |
| `skip_avgo` | `24` | `+$201.39` | `4.8%` | `+$173.42` | Symbol hypothesis, not a ban. |
| `skip_alpha_breakout_chop` | `107` | `+$52.28` | `21.4%` | `$0.00` | Plausible but needs fill-level replay. |
| `skip_conf_45_55` | `56` | `+$37.96` | `11.2%` | `-$9.98` | All-time drawdown regression; recent better. |

### Last 200

| Scenario | Skipped | PnL delta | Trade reduction | DD delta | Verdict |
| --- | ---: | ---: | ---: | ---: | --- |
| `skip_alpha_breakout_chop` | `107` | `+$52.28` | `53.5%` | `+$48.99` | Shadow candidate, but large removal. |
| `skip_conf_45_65` | `119` | `+$37.48` | `59.5%` | `+$53.42` | Too broad; near the removal ceiling. |
| `skip_avgo` | `17` | `+$27.97` | `8.5%` | `+$24.57` | Watchlist candidate only. |
| `skip_conf_55_65` | `87` | `+$26.81` | `43.5%` | `+$27.46` | Watch; recent windows are mixed. |
| `skip_conf_45_55` | `32` | `+$10.67` | `16.0%` | `+$25.96` | Modest but clean. |

### Last 100

| Scenario | Skipped | PnL delta | Trade reduction | DD delta | Verdict |
| --- | ---: | ---: | ---: | ---: | --- |
| `skip_alpha_breakout_chop` | `64` | `+$35.12` | `64.0%` | `+$30.11` | Positive but removes too many trades. |
| `skip_conf_45_65` | `78` | `+$33.09` | `78.0%` | `+$42.37` | Too broad. |
| `skip_conf_45_55` | `23` | `+$20.73` | `23.0%` | `+$28.90` | Best clean recent candidate. |
| `skip_conf_55_65` | `55` | `+$12.36` | `55.0%` | `+$14.40` | Positive but large removal. |
| `skip_avgo` | `9` | `+$15.09` | `9.0%` | `+$12.33` | Insufficient sample. |

### Last 50

| Scenario | Skipped | PnL delta | Trade reduction | DD delta | Verdict |
| --- | ---: | ---: | ---: | ---: | --- |
| `skip_conf_45_55` | `11` | `+$21.06` | `22.0%` | `+$18.98` | Best clean recent candidate. |
| `skip_alpha_breakout_chop` | `22` | `+$12.45` | `44.0%` | `+$9.16` | Worth fill-level replay. |
| `skip_conf_55_65` | `24` | `+$3.67` | `48.0%` | `+$4.32` | Too weak recently. |
| `skip_avgo` | `4` | `+$8.66` | `8.0%` | `+$5.26` | Insufficient sample. |

### Last 25

The last-25 window argues against immediate promotion:

- `skip_conf_55_65` is negative: `-$1.34` delta.
- `skip_conf_45_55` is negative: `-$7.24` delta with only `4` skipped trades.
- `skip_alpha_breakout_chop` is positive `+$3.29`, but only `6` skipped trades.
- `skip_avgo` is positive `+$8.28`, but only `1` skipped trade.

## Recommendation

Next Phase 3 work should be fill-level replay/shadow instrumentation for:

1. `confidence >= 0.45 and confidence < 0.55` as a no-entry candidate.
2. `entry_source == "alpha+breakout" and regime_at_entry == "chop"` as either
   a no-entry candidate or a lower-priority ranking candidate.

Do not test a broad `[0.45,0.65)` gate live. It removes `70%` of the last-50
trades and `78%` of the last-100 trades. That is too blunt for an autonomous
system that still needs enough clean observations to learn.

Do not ban `AVGO` yet. The all-time drag is real, but recent windows have too
few AVGO trades to justify a symbol-level live restriction.
