# Track Z6 v8 — Closure Regression (Waves 23-31)

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `79b38fb`.

## Scope

| Wave | Findings | Commit |
|---|---|---|
| 23 | AA-C-1, AA-C-2, AA-H-2, AA-M-1, EE-3 | 73f96e7 |
| 24 | DD-1..4, AA-H-1/H-4, AA-M-3..5, EE-7 | 7ed1aa6 |
| 25 | BB-1/2/3, FF-1/2/3, EE-2/8 | 413cf9e |
| 26 | W2-1, T2-pin, GG-6/7/9 | 614f0a3 |
| 27 | HH R-5 | f7d8df8 |
| 28 | CI rules required-mode | 76e8df3 |
| 29 | HH R-1 Stage 0a (`_stage_expire_cooldowns`) | 79b38fb |
| 30 | BB-8 (LotTracker), BB-10 (audit_logs), AA-H-3 (login audit) | acebe08 |
| 31 | Reachability tests (12 new) | 7532f0d |

## Method

1. **Per-finding verification**: grep markers for each closed ID.
2. **Same-bug-class scan**: clean across organism/services/integrations.
3. **Tests pass**: 179 expected (167 prior + 12 reachability).
4. **Brain coherent**: gen=168, trades=498.
5. **NEW (V8 lens)**: re-run `tests/test_reachability_v8.py`. All 12 pass = reachability invariants hold.
6. **NEW (V8 lens)**: live verify in container — `audit_logs` row count > 0; LotTracker call site reachable from `_process_trade_update` source.
7. **CI enforcement smoke**: `./venv/bin/python scripts/ci/check_wave_markers.py --base HEAD~10 --head HEAD --warn-only` should pass; `--base HEAD~10 --head HEAD` (required-mode) may flag earlier waves' missing grep+zero declarations (acceptable as documentation gap, not regression).

## Output

`artifacts/audit/v8_reports/track_z6_closure_regression.md` with verification table + same-class deltas + "Regressions: N" + TL;DR.

Quality bar: 0-2 regressions. End with one-paragraph summary.
