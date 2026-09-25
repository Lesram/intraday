# Approved composite correction — September 25, 2026

The scalar numerator repair restores seven computed strategy inputs that the prior helper silently caused the ML feature path to replace with zeros. The production change is `abs(a)` with truthful typing/documentation. Series alignment, zero/zero NaN masking, epsilon behavior, formulas, weights, thresholds, sizing and feed settings are preserved. This deliberately changes decision inputs and is not a claim of profitable strategy improvement.

Source commit: `029f1c37f71f03ff1acff46fd0fa6be92a99c9c0`. The user approved this correction and paired replay after the defect was explained. Candidate freeze generation never activates a forward cutoff. The installed paper deployment is unchanged.

## Evidence map

- `plan.json`: approved scope, affected files, acceptance and authority limits.
- `implementation.json`: 35 failures on the old helper; final 41 new contracts pass plus 30 adjacent regressions. Superseded red/green attempts are preserved, excluded from final passing counts.
- `replay/implementation_report.json` and `replay/paired_summary.json`: 16 paired-method tests; five scenarios, two arms, two repeats, 1,100 actual engine ticks; 90 direct-prefix checks and 30 future-tail checks. Same current engine/configuration in both arms, only the pinned old helper differs. Full ordered decisions, fills, gates, exits and equity are retained.
- `operational.*`: 1,902 passes, zero failures, one skipped installed-history test because production history is not supplied to isolated execution.
- `nightly.*`: 207 passes. `freeze_snapshot.*`: 132 passes. `workflow_contract.*`: 29 passes. These selections overlap; do not add them as unique cases.
- `full_final.*` and the root `artifacts/` pack: mandatory safety/regression/replay results for the source commit; `local_acceptance.json` summarizes final gate status.
- `candidate_freeze_receipt.json`: corrected candidate validates; comparison to the old active surface intentionally fails. `artifacts/phase2/param_freeze.json` stays the exact active reference, separate from `candidate_param_freeze.json`.
- `active_runtime_preservation.json`: installed source and immutable container identity, healthy state, zero restarts, freeze/cutoff/binding preservation and installed freeze verification.
- `independent_review.json`: separate source/method/evidence review.
- `source_security/` and `public_security/`: source and evidence scanning with explicit disposition rather than hidden allowlisting.

## Trading replay interpretation

All scenarios use the existing synthetic fixture with $1,000,000 initial cash, 5bp slippage, class-dependent spread and zero per-share commission. They do not reproduce the deployed account or September 24. Dollar values below are equity changes including any open marked positions.

| Scenario | Entries: old → corrected | Equity change: old → corrected | Maximum drawdown: old → corrected |
|---|---:|---:|---:|
| Rising | 5 → 6 | $571.13 → $2,361.90 | 0.0893% → 0.0910% |
| Falling | 2 → 4 | $1,064.20 → −$836.13 | 0.0467% → 0.1232% |
| Sideways | 5 → 5 | −$280.74 → $1,497.00 | 0.1579% → 0.1206% |
| Crash | 4 → 5 | −$3,293.52 → −$1,476.12 | 0.4014% → 0.7720% |
| Market close | 1 → 1 | $99.06 → $99.06 | 0.0506% → 0.0506% |

Falling-market results deteriorate, and crash drawdown increases despite a smaller final loss. The corrected rising scenario retains one open position. Both market-close arms finish flat; protective exits, final admission receipts and accounting are checked. No order/exit decision is mocked. Precomputed fixture features are limited to exact causal prefixes with direct and adversarial checks. Synthetic receipts are explicitly unverified for real runtime/feed identity and cannot qualify as forward trades.

## Limits and next release gates

The legacy zero fallback for other possible feature exceptions remains. Global sparse-feed admission policy remains. The withdrawn ML cache is not included, and no feature-speedup claim is made. Historical feature/model evidence needs provenance and recomputation before reuse; raw market data and broker fills are not invalidated merely by this defect.

The later paper release must use accepted hosted checks, the exact validated image/configuration, current broker/state preflight and an explicitly approved new forward boundary. This evidence does not authorize live-money trading or demonstrate a positive edge. The current paper process was not restarted or deployed by this task.
