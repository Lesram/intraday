# Deploy Verification — Exp2 + Exp3 Prep

**Date**: 2026-04-16 02:41–02:43 UTC
**Target**: `ce06d41` (Exp2 + Exp3 prep on top of Exp1A)
**Verdict**: DEPLOYED AND VERIFIED

## Summary

All signature checks pass. Exp2 (inverse ETF suppression in chop) is now live. Exp3 prep (confidence side-by-side logging) is now live. Exp1A (10-bar min-hold) preserved. Full Patch F preserved. Exp4 and G1/G2/G3 confirmed absent. Force-save succeeded. Manifest fully synced. All 13 brain artifacts present.

## Hard-stop checks: 9/9 PASS

1. Target ce06d41 deployed: PASS
2. Exp2 signatures present: PASS (4 line matches)
3. Exp3 signatures present and read-only: PASS (6 line matches, no gate changes)
4. Exp4 absent: PASS (0 matches)
5. Exp1A preserved: PASS (2 line matches)
6. Full Patch F preserved: PASS (12 total matches across 2 files)
7. Force-save succeeded: PASS (HTTP 200, success=true, gen=70, trades=258)
8. Manifest sync correct: PASS (all 6 fields match)
9. No blocker before next session: PASS

## Live branch readiness

- Exp2 now live? **YES**
- Exp3 prep now live? **YES**
- Exp4 still offline? **YES** (absent from container)
- Exp1A still live? **YES** (signatures preserved)
- Structural persistence still intact? **YES** (Full Patch F signatures preserved)

## Boot

- Brain loaded: gen=70, runs=606, trades=258
- Trading phase: production_frozen (258/300, freeze_exit=42)
- PREFLIGHT: 16/18, 0 critical
- Scheduler started
- Zero errors in boot log

## Next-session observation plan (3-5 sessions)

| Metric | Baseline (Exp1A only) | Target (Exp1A + Exp2) |
|---|---|---|
| PSQ/SH trades in chop | ~1-2/session | **0** |
| PSQ/SH PnL | ~-$2 to -$4/session | **$0** |
| `Exp2: inverse ETF entry suppressed` count | 0 | >0 |
| Pyramid_cut % | 43% (Exp1A cumulative) | ≤43% |
| Win rate | 25.0% (Exp1A cumulative) | ≥25% |
| Expectancy | -$1.11 (Exp1A cumulative) | ≥-$1.11 |
| Exp3 confidence_bt_only in candidate dicts | absent | present |
| Exp3 gate_pass_bt_only | absent | present |
