# Phase 3 Candidate-Filter Fill-Path Replay Report

Generated: 2026-05-04
Branch: `codex/v13-phase2-expectancy`
Tool: `scripts/phase3_candidate_filter_fill_replay.py`

## Verdict

Do not promote either candidate filter.

The closed-trade counterfactual made `confidence [0.45,0.55)` and
`alpha+breakout|chop` worth investigating, but the fill-path replay cannot
validate either one with the current cached bars. The bar cache only matches
`106 / 352` fill-valid rows, and it matches `0` trades in the last-100,
last-50, and last-25 windows. That means the most decision-relevant recent
trades have no fill-path evidence here.

The useful result is negative but important: the platform does not currently
retain enough recent bar context to promote a candidate no-entry gate from
offline fill replay. The next safe step is fresh live shadow telemetry or a
new same-day bar capture bundle, not a live filter.

## Evidence Command

```bash
./venv/bin/python scripts/phase3_candidate_filter_fill_replay.py
```

Outputs:

- `artifacts/phase3_candidate_filter_fill_replay/summary_candidate_filter_fill_replay.json`
- `artifacts/phase3_candidate_filter_fill_replay/candidate_filter_fill_results.csv`
- `artifacts/phase3_candidate_filter_fill_replay/matched_trades_candidate_filter_fill_replay.csv`

## Method

The tool reads `organism_brain/trade_history.csv`, excludes reconciliation
artifacts, reconstructs entry timestamps from `closed_at -
time_in_trade_seconds`, joins matching trades to cached minute bars from
`artifacts/backtest_rc_1_5/bars*.pkl`, then recomputes:

- price-path PnL from entry and exit fills,
- fill PnL error versus reported PnL,
- MFE, MAE, giveback, and capture ratio,
- entry/exit fill plausibility against nearby high-low ranges,
- match rates and unmatched reasons by candidate slice.

This is still not a replacement-trade simulator. It cannot model freed capital,
changed learner state, or trades that would have been selected after a skipped
entry.

## Coverage

| Metric | Value |
| --- | ---: |
| CSV rows | `508` |
| Reconciliation artifacts excluded | `7` |
| Rows missing exit timestamp | `142` |
| Rows missing entry timestamp | `7` |
| Fill-valid rows | `352` |
| Cached bar files | `bars.pkl`, `bars_alt.pkl` |
| Cached symbols | `22` |

Baseline fill-path match rate:

| Window | Input trades | Matched | Match rate | Input PnL | Matched PnL |
| --- | ---: | ---: | ---: | ---: | ---: |
| all | `352` | `106` | `30.1%` | `$191.18` | `-$69.72` |
| last-200 | `200` | `33` | `16.5%` | `$9.48` | `-$6.29` |
| last-100 | `100` | `0` | `0.0%` | `$37.04` | `$0.00` |
| last-50 | `50` | `0` | `0.0%` | `$48.73` | `$0.00` |
| last-25 | `25` | `0` | `0.0%` | `$63.07` | `$0.00` |

The all-window baseline is coverage-biased: the matched subset is negative even
though the fill-valid input rows are positive. That is not an edge signal; it
is a warning that the cached bars cover an older, different slice of the brain.

## Candidate Results

### `confidence [0.45,0.55)`

| Window | Input | Matched | Match rate | Input PnL | Matched PnL | Verdict |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| all | `36` | `5` | `13.9%` | `-$25.83` | `$17.56` | Insufficient sample. |
| last-200 | `27` | `3` | `11.1%` | `$5.64` | `$8.69` | Insufficient sample. |
| last-100 | `21` | `0` | `0.0%` | `-$4.86` | `$0.00` | No recent fill coverage. |
| last-50 | `10` | `0` | `0.0%` | `-$4.21` | `$0.00` | No recent fill coverage. |
| last-25 | `4` | `0` | `0.0%` | `$7.24` | `$0.00` | No recent fill coverage. |

The matched subset is not negative. Combined with the tiny sample, this blocks
promotion and weakens the closed-trade counterfactual as standalone evidence.

### `alpha+breakout|chop`

| Window | Input | Matched | Match rate | Input PnL | Matched PnL | Verdict |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| all | `107` | `10` | `9.4%` | `-$52.28` | `-$9.71` | Insufficient sample. |
| last-200 | `107` | `10` | `9.4%` | `-$52.28` | `-$9.71` | Coverage too sparse. |
| last-100 | `66` | `0` | `0.0%` | `-$32.04` | `$0.00` | No recent fill coverage. |
| last-50 | `23` | `0` | `0.0%` | `-$14.60` | `$0.00` | No recent fill coverage. |
| last-25 | `6` | `0` | `0.0%` | `-$3.29` | `$0.00` | No recent fill coverage. |

This slice remains suspicious, but the evidence is not strong enough for a
gate. If it becomes a live change later, the first step should be shadow-only
telemetry: log whether the proposed gate would have blocked an entry and track
the eventual outcome without affecting orders.

## Recommendation

Keep both candidate filters out of production.

Before any live gate is considered, add a runtime shadow telemetry channel or
generate a fresh bar bundle that covers the current brain's recent trades. The
telemetry should record candidate-gate decisions, symbol, confidence,
entry_source, regime, current features, whether the normal engine entered, and
subsequent MFE/MAE/outcome. Without that, Phase 3 can rank hypotheses but cannot
prove a no-entry filter.
