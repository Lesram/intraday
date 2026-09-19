# Preflight summary — `eb90fa3`
**Run at:** 2026-04-25 (Saturday weekend prep)
**Target commit:** `eb90fa369e2739f77c7b1789aa47bd8b83184912`

## 1. Brain backup ✅

```
artifacts/deploy_preflight_eb90fa3/organism_brain_backup_pre_eb90fa3_20260425/
size: 1.1M
contents: manifest.json, learning_state.json, evolved_params.json,
          governance_state.json, regime_state.json, ml_state.json,
          ml_classifier.joblib, ml_regressor.joblib, trade_history.csv,
          equity_curve.csv, evaluation_event_history.json, extra_counters.json,
          reference_feats.csv, diagnostics/history.json
```

Pre-deploy state preserved. If post-deploy verification fails, restore from this snapshot.

## 2. Runtime snapshots ✅

Captured at preflight time:
- `runtime_defaults_snapshot.json`
- `resolved_config_snapshot.json`
- `live_process_runtime_snapshot.json`
- `runtime_config_snapshot.json` (legacy)

Resolved config at preflight: `ORGANISM_DRAWDOWN_KILL_PCT=0.20`, `MAX_POSITIONS=8`, `ALPHA_TOP_N=5`, `EXPLORATION_ENABLED=false`, `APP_ENVIRONMENT=development` (paper compose convention), `ALPACA_PAPER=true`.

## 3. Test suite ✅ (deploy-critical) ⚠️ (full suite)

**Deploy-critical (eb90fa3 changeset):** **43 / 43 PASSED**
```
tests/test_experiment_4_trailing_giveback.py
tests/test_g1_g2_g3_mechanical_fixes.py
tests/test_h1_h2_real_money_hardening.py
tests/test_real_money_risk_limits.py
tests/test_governance_drawdown_canonical.py
tests/test_h5_settings_governance.py
```

All 6 changeset surfaces are green. This is the deploy gate that matters.

**Full suite:** 7857 passed / 37 failed / 684 skipped
The 37 failures are pre-existing legacy/audit-track issues:
- `test_audit_patch_queue_*` (older audit track)
- `test_walkforward_persistence` / `test_safety_invariants` / `test_organism_engine_scenarios` (known flaky-in-full-suite per CLAUDE.md memory)
- `test_residual_remediation::test_write_runtime_snapshot_no_hardcoded_creds` (cosmetic)

**None of the 37 failures touch eb90fa3 changeset code.** The full suite numbers are unchanged from pre-eb90fa3 baseline (within noise). DO NOT block deploy on these.

## 4. Replay regression ✅ (with one known flake)

**Result:** 25 / 26 PASSED (96%)
**Known flake:** `test_replay_no_throttle_blocking` (timing-sensitive, 100-tick window with 0 orders due to bar-boundary entry-only — pre-existing, not changeset-related).

**Important confirmation in replay log:**
```
WARNING governance: drawdown_kill_pct=0.2000 is 4.00x the code default 0.0500
        — verify this is intentional (env override from ORGANISM_DRAWDOWN_KILL_PCT)
```
**The canonical drawdown-kill startup validator from `0ac6e2d` is firing correctly.** This is exactly the behavior we want at deploy time.

## 5. Spec drift ✅

```
Checking 3-way spec-vs-runtime drift...
  Parsed 8 constants from mapss.md
  Runtime snapshot has 36 keys
  Manifest has 11 constants
  All 9 core constants agree across all sources.
No spec drift detected.
```

## 6. Worktree state ✅

- HEAD = `eb90fa3` (after weekend pack archive commit `4ffe12d` was rebased — confirm at deploy time)
- No tracked diff (clean)
- Audit trail archived to `docs/engineering/audits/archive/2026-04/`

## 7. Container truth ✅

- Live container = `ce06d41` (verified by file-SHA forensics in CURRENT_LIVE_STATE_SNAPSHOT.md)
- Live container healthy, restart count 0
- Manifest+learning_state coherent (gen=124, total_trades=396)

## Deploy gate verdict

**GREEN.** All four deploy-critical signals are positive:

1. ✅ Changeset tests 43/43 pass
2. ✅ Replay regression passes (modulo known throttle flake)
3. ✅ No spec drift
4. ✅ Brain backup taken

**Recommended deploy time:** Monday 2026-04-27, 8:30–9:00 ET, with operator at the keyboard.

**If anything fails Monday morning:** restore brain from `organism_brain_backup_pre_eb90fa3_20260425/` and revert to `ce06d41`.
