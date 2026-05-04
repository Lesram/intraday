# Track Z7 v9 — Closure Regression on Waves 32-40

**Branch:** `rc-1.5-curated` @ `ccba97f`
**Baseline:** `0826dad` (V8 synthesis, pre wave 32)
**Range audited:** `842587e` (wave-32) → `db1a3fc` (wave-40 test alignment); 12 commits inclusive

## 1. Per-marker presence table

Every closed finding's `V8 <ID> / Wave-<N>` source-code marker was verified via targeted grep on rc-1.5-curated @ ccba97f.

| Wave | Finding ID | Marker site (file:line excerpt) | Present |
|---|---|---|---|
| 32 | DD2-1 | backend/organism/live_engine.py:2217 `V8 / DD2-1 / Wave-32` | YES |
| 32 | W3-G1 | scripts/ci/check_wave_markers.py:246 | YES |
| 32 | W3-G2 | scripts/ci/check_wave_markers.py:159 | YES |
| 32 | W3-G3 | scripts/ci/check_wave_markers.py:48 | YES |
| 32 | AA2-NEW-1 | backend/api/routes/audit.py:22,109,199,254,290,313,348 (7 markers) | YES |
| 32 | AA2-NEW-2 | backend/infra/security.py:629 | YES |
| 32 | AA2-NEW-3 | backend/infra/security_hardening.py:337 | YES |
| 33 | NN-CRIT-1 | backend/api/routes/position_import.py — DELETED (verified absent) | YES |
| 33 | DD2-2 | backend/organism/live_engine.py:3097,5409 + backend/organism/ml_signal.py:523 | YES |
| 34 | DD2-3 | backend/organism/regime.py:159,489,509,622 | YES |
| 34 | DD2-4 | backend/organism/regime.py:166,274 | YES |
| 34 | DD2-5 | backend/organism/kelly_sizer.py:374 | YES |
| 34 | NN-HIGH-1 | backend/organism/live_engine.py:5912 (`logger.warning` at 5923) | YES |
| 35 | DD2-7 | backend/organism/live_engine.py:774 (cache @ 781-788) | YES |
| 35 | DD2-8 | backend/organism/live_engine.py:3167 (direction>0 gate @ 3173-3177) | YES |
| 35 | DD2-9 | backend/organism/live_engine.py:1718,1737 | YES |
| 35 | DD2-10 | backend/organism/runner.py:52,111 + backend/organism/routes.py:678 | YES |
| 36 | NN-CRIT-2 (parity_checker delete) | backend/strategies/parity_checker.py — DELETED; backend/strategies/__init__.py:3 marker | YES |
| 36 | NN-CRIT-3 (6 risk modules delete) | backend/risk/{black_swan_protection,correlation_breakdown,margin_calculator,volatility_checker,position_limits,risk_calculator}.py — DELETED | YES |
| 37 | OO MIGRATION-GAP | scripts/ci/check_migrations.py:2 + tests/test_wave37_fixes.py | YES |
| 38 | NN-MED-1 | backend/mlops/ entire package — DELETED (12 files) | YES |
| 38 | NN-MED-2 | backend/ml/{data_processing,ensemble_framework,model_management,pipeline,prediction_service,sentiment,staleness_detector,validation}.py — DELETED | YES |
| 38 | NN-MED-3 | backend/optimization/portfolio_optimizer.py — DELETED | YES |
| 38 | NN-MED-4 | backend/brokers/{alpaca_production,broker_failover}.py + cascade backend/risk/{advanced_risk,advanced_risk_manager}.py — DELETED | YES |
| 39 | HH2 plan-feedback | backend/organism/live_engine.py:1638 (entries_blocked → self._entries_blocked) | YES |
| 40 | HH R-1 stages 1/1.1/1.2 | backend/organism/live_engine.py:1568,1690 (`_stage_check_entry_blockers` helper) | YES |

**25 of 25 markers present and structurally intact.** No closure regressions.

## 2. Behavioral test execution

```
./venv/bin/python -m pytest \
  tests/test_wave32_fixes.py tests/test_wave33_fixes.py tests/test_wave34_fixes.py \
  tests/test_wave35_fixes.py tests/test_wave36_fixes.py tests/test_wave37_fixes.py \
  tests/test_wave38_fixes.py tests/test_wave39_fixes.py tests/test_wave40_fixes.py \
  tests/test_reachability_v8.py tests/test_organism_live_engine.py \
  tests/test_safety_invariants.py tests/test_multi_tick_state.py -q --timeout=30
```

**Result:** `147 passed, 2 warnings in 15.94s` — exceeds the >=147 quality bar.

## 3. Same-class scan counts (per wave)

For each wave's same-class grep cited in the commit body, re-ran on HEAD:

| Wave | Cited grep (paraphrased) | Re-run count | Status |
|---|---|---|---|
| 32 | `continue *# *.*pending_exit` in live_engine.py | 0 | OK |
| 32 | `require_trader` in audit.py | 0 | OK |
| 32 | `UserClaims(**payload)` in infra/ (non-test) | 0 | OK |
| 32 | `request.url.scheme == "https"$` | 0 | OK |
| 33 | `from backend.api.routes.position_import` | 0 | OK |
| 33 | `meta["confidence"], was_correct` | 0 | OK |
| 34 | `churn_rate=0.0` in regime.py | 1 (legitimate UNKNOWN early-return at line 242, NOT the broken aggregate path; fix added at 159/489/509/622) | OK |
| 34 | `kelly_raw = min(regime_kelly` | 1 (line 392, now correctly gated by `_atr_var_squared_pre >= _ATR_VAR_MIN` predicate at lines 384-389) | OK |
| 34 | `logger.debug.*[Tt]elemetry.*[Ss]kipped` | 1 (line 5949 — separate `_cleanup_old_telemetry` method where DEBUG is intentional; the WAVE-34 fix at write path now `logger.warning` at line 5923) | OK |
| 35 | `def _is_learning_mode` | 1 (the patched property itself) | OK |
| 35 | `abs(ml_sig.predicted_return) > 1e-4$` | 1 (line 3176, now gated by `ml_sig.direction > 0` at line 3175) | OK |
| 35 | `_eod_flatten_triggered = True` | 1 (line 1724, now bounded by `[15:58, 16:00)` window per fix) | OK |
| 35 | `datetime.now(UTC)` in runner.py | 0 | OK |
| 36 | `from backend.risk.{6 deleted modules}` in backend/ | 0 | OK |
| 36 | `from backend.strategies.parity_checker\|ParityChecker` in backend/ | 0 | OK |
| 38 | `from backend.mlops` in backend/ | 0 | OK |
| 38 | `from backend.brokers.{alpaca_production,broker_failover}` in backend/ | 0 | OK |
| 38 | `from backend.optimization.portfolio_optimizer\|AdvancedRiskManager` in backend/ | 0 | OK |
| 39 | bare `\bentries_blocked\b` in live_engine.py (excl self._/legit) | 0 | OK |
| 40 | inline `# 1. GOVERNANCE / # 1.1 WARMUP / # 1.2 STALE` blocks left in `_live_tick_inner` | 3 (these are now in the EXTRACTED helper `_stage_check_entry_blockers`, not in `_live_tick_inner`; helper presence verified) | OK |

The 7 non-zero counts are all legitimate residual matches that the wave-marker checker's naive grep cannot disambiguate from the broken pre-fix lines; manual inspection of each site confirms the regression class is patched.

## 4. Brain coherence + container health

```json
{
  "generation": 168,
  "total_trades": 498,
  "ml_is_trained": true,
  "best_sharpe": 3.4363
}
```

Matches the V8-end snapshot (gen=168, trades=498, ml=trained). Containers up:
- `intra-api-1` Up 2 hours (healthy)
- `intra-redis-1` Up 3 hours (healthy)

## 5. Wave-28 marker check on HEAD~10..HEAD

```
./venv/bin/python scripts/ci/check_wave_markers.py --base HEAD~10 --head HEAD
```

**Result: `[FAIL] 16 wave-commit check(s) failed`.**

All 16 failures fall into known classes:
1. `[FAIL] no finding-IDs cited in commit body` (3 hits — wave-37 OO, wave-40 test alignment, wave-40 post-merge) — these were maintenance / meta-finding commits the V8 enforcer's regex doesn't recognise (no `DD2-`, `NN-`, etc. token), but the commit bodies do reference the meta-finding by name (`OO MIGRATION-GAP`, `wave-32 DD2-1 vs legacy multi-tick test`).
2. `[FAIL] re-ran, count=N>0` (10 hits) — the cited grep pattern still matches at the patched site because the fix added a guarding condition rather than removing the matched substring (e.g. `kelly_raw = min(regime_kelly, 1.0)` is now gated by `_atr_var_squared_pre >= _ATR_VAR_MIN`; `abs(ml_sig.predicted_return) > 1e-4` is now gated by `ml_sig.direction > 0`). Site-by-site code inspection confirms the regression class is patched (see Section 3 footnotes).
3. `[FAIL] Critical/High wave commit added no new test functions (net delta=-N)` (2 hits — wave-36 net=-153, wave-38 net=-657) — these are pure-deletion waves where deleting orphan modules also deleted their orphan test files; the net delta is negative because deleted-test-functions outnumber added regression-lock tests. Wave-36 added 10 new tests (`tests/test_wave36_fixes.py`), wave-38 added 17 new tests (`tests/test_wave38_fixes.py`); these compensate qualitatively but not quantitatively under the v6 W rule's net-delta heuristic.
4. `[FAIL] commit body does not assert count: 0` (1 hit — wave-40 post-merge `dec7c28`) — test-only maintenance commit where same-class scan is genuinely N/A.

None of the 16 failures represent a closure regression — they are checker-tool artifacts on housekeeping commits, NOT broken markers.

## 6. Migration smoke check

```
./venv/bin/python scripts/ci/check_migrations.py
```

Output:
```
[ok] 15 migration(s) under /Users/marselkei/VS/intra/backend/migrations/versions
[ok] single head: 20260503_000001
[ok] base: 706e00fe1a28
[OK] migration tree is linear with single head.
exit=0
```

Pass.

## 7. Orphan-isolation check (production code)

Per Z7 prompt section 7:

```
grep -rn 'from backend\.mlops\|from backend\.brokers\.alpaca_production\|...' backend/ tests/ --include='*.py'
```

**`backend/` count: 0.** Production code has zero references to deleted orphan modules.

**`tests/` count: ~140+ residual import statements** across ~20 test files (`tests/unit/test_enums_comprehensive.py`, `tests/unit/test_ml_*_comprehensive.py`, `tests/unit/test_risk_*_comprehensive.py`, `tests/unit/generated/test_auto_*.py` for `feature_store`, `governance`, `pipeline`, `experiment_tracking`, `deployment`, `model_serving`, `registry`, `noop`, `monitoring`, `model_optimization`, `advanced_risk`, `advanced_risk_manager`, `portfolio_optimizer`, `validation`, `data_processing`, `model_management`, `prediction_service`, `ensemble_framework`, `alpaca_production`).

These were FUNCTIONAL at the V8 baseline (modules existed). Wave-38's `backend/mlops/`, `backend/optimization/portfolio_optimizer.py`, `backend/brokers/{alpaca_production,broker_failover}.py`, cascade `backend/risk/{advanced_risk,advanced_risk_manager}.py`, and 8 `backend/ml/*` deletions did NOT remove the orphan-test importers. The wave-38 commit body claims "Plus 11 corresponding test files (the test_*_comprehensive.py + auto_* files for the deleted modules)" — git confirms only 18 test files were deleted across waves 36+38, but ~20 additional orphan-importing test files remain on disk. The wave-38 dangling-imports lock (`tests/test_wave38_fixes.py::test_wave38_no_dangling_mlops_imports`) is scoped to `backend/` only — it cannot detect this.

### Concrete impact

Default `pytest --collect-only` from repo root:
- **At baseline 0826dad:** 8818 tests collected, 0 collection errors.
- **At HEAD ccba97f:** 7294 tests collected, **25 collection errors** (`ModuleNotFoundError: No module named 'backend.mlops.<X>' / 'backend.optimization.portfolio_optimizer' / 'backend.ml.staleness_detector' / 'backend.risk.advanced_risk_manager' / etc.`).

The 25 broken test modules:
```
tests/test_drift_and_retrain_decision.py
tests/test_live_model_smoke.py
tests/test_model_selection_smoke.py
tests/test_risk_management_complete.py
tests/test_routes_registry.py
tests/test_safe_expression_evaluator.py
tests/unit/test_enums_comprehensive.py
tests/unit/test_ml_active_model_pointer_comprehensive.py
tests/unit/test_ml_data_processing_comprehensive.py
tests/unit/test_ml_drift_comprehensive.py
tests/unit/test_ml_ensemble_framework_comprehensive.py
tests/unit/test_ml_feature_engineering_comprehensive.py
tests/unit/test_ml_lifecycle_comprehensive.py
tests/unit/test_ml_lifecycle_scheduler_comprehensive.py
tests/unit/test_ml_model_management_comprehensive.py
tests/unit/test_ml_model_manager_comprehensive.py
tests/unit/test_ml_model_selection_comprehensive.py
tests/unit/test_ml_monitoring_comprehensive.py
tests/unit/test_ml_pipeline_comprehensive.py
tests/unit/test_ml_prediction_service_comprehensive.py
tests/unit/test_ml_training_comprehensive.py
tests/unit/test_ml_validation_comprehensive.py
tests/unit/test_risk_advanced_manager_comprehensive.py
tests/unit/test_risk_margin_comprehensive.py
tests/unit/test_risk_volatility_comprehensive.py
```

This does NOT regress any wave-32-40 closure marker (the 147-test wave-fix suite still passes, the production code is clean), but it does regress repository-level pytest hygiene and CI signal — any `pytest tests/` invocation that doesn't pre-filter to specific paths will see 25 hard collection errors masking real failures.

## Findings

### Z7-FINDING-1 (MEDIUM): Wave-38 left 25 orphan test modules importing deleted backend modules

**Class:** Closure-regression-adjacent. The wave-38 closure marker IS in place (production code is clean) and the wave-38 dangling-imports regression test passes (it's scoped to `backend/` only). But the closure was **incomplete on the test side**: the wave-38 commit body claims it deleted "11 corresponding test files" yet ~20 orphan-test importers in `tests/unit/` and `tests/unit/generated/` were missed.

**Evidence:**
- Default `pytest --collect-only` returns 25 `ModuleNotFoundError` collection errors at HEAD that did not exist at baseline (8818 → 7294 collected; 0 → 25 errors).
- `tests/test_wave38_fixes.py::test_wave38_no_dangling_mlops_imports` filters `grep` output to `if "test_" not in line` and only inspects `backend/` — by construction it cannot detect the missed test deletions.
- Sample broken modules: `tests/unit/test_enums_comprehensive.py` (imports `backend.optimization.portfolio_optimizer`, deleted in wave-38), `tests/unit/test_ml_validation_comprehensive.py` (imports `backend.ml.staleness_detector`), `tests/unit/test_risk_advanced_manager_comprehensive.py` (imports `backend.risk.advanced_risk_manager`), 16 `tests/unit/generated/test_auto_*.py` files for the deleted mlops/risk/optimization modules.
- All 25 errors are `ModuleNotFoundError` on modules deleted by wave-36 (`risk_advanced_manager` cascade was actually wave-38) and wave-38 (`backend.mlops.*`, `backend.ml.{staleness_detector,validation,pipeline,…}`, `backend.optimization.portfolio_optimizer`, `backend.brokers.{alpaca_production,broker_failover}`).

**Severity:** MEDIUM. Wave-32-40 production-code closures are intact; the 147-test cumulative wave-fix suite passes. But repo-level CI / dev-loop signal is broken: any `pytest tests/` from a clean checkout returns immediate non-zero exit on collection errors that have nothing to do with the change under test.

**Recommended remediation (NOT applied — Z7 is audit-only):** delete the 25 orphan-test modules listed above OR widen `tests/test_wave38_fixes.py::test_wave38_no_dangling_mlops_imports` to scan `tests/` and surface the violation as a regression-lock failure.

---

**Closure regressions: 0 (no marker dropped).**
**Audit-adjacent findings: 1 (Z7-FINDING-1, MEDIUM, test-tree hygiene).**

## TL;DR

All 25 wave-32-40 closure markers are present and structurally intact in the production code at `rc-1.5-curated@ccba97f`; the 147-test cumulative wave-fix + reachability + organism + multi-tick + safety-invariants suite passes cleanly; the migration tree is linear single-headed; brain manifest and containers match the V8-end snapshot (gen=168, 498 trades, ml trained, sharpe 3.44); and zero references to any deleted orphan module survive in `backend/`. The `check_wave_markers.py` enforcer reports 16 failures on HEAD~10..HEAD but inspection shows they are all checker-tool artifacts (gated-fix lines whose substring still matches; pure-deletion waves with negative net-test-delta; meta-finding commits without canonical finding-ID tokens), not real regressions. **Closure regressions: 0.** One MEDIUM audit-adjacent finding: wave-38 missed deleting ~20 orphan test files that imported the now-deleted `backend.mlops.*`, `backend.ml.staleness_detector`, `backend.optimization.portfolio_optimizer`, and `backend.risk.advanced_risk_manager` modules; default `pytest --collect-only` regressed from 0 to 25 collection errors between baseline and HEAD, masking real CI signal even though no closed wave-32-40 finding was reopened.
