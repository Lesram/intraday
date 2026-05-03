# Track Z7 v9 — Closure Regression on Waves 32-40

V8 closed 27 of 37 actionable findings via waves 32-40 (commits `842587e` → `dec7c28`). **Z7 verifies every closure marker is still in place** and no later commit silently dropped them. Standard closure-regression pattern.

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `db1a3fc`. Baseline: `0826dad` (V8 synthesis commit, before wave 32).

## Method

### 1. Per-finding marker check

For each closed finding, verify the source-code marker (`V8 <FINDING-ID> / Wave-<N>`) is present at the expected file site. Walk waves 32-40 commit messages to extract the closure list.

| Wave | Markers expected |
|---|---|
| 32 | DD2-1, W3-G1, W3-G2, W3-G3, AA2-NEW-1, AA2-NEW-2, AA2-NEW-3 |
| 33 | NN-CRIT-1 (deletion), DD2-2 |
| 34 | DD2-3, DD2-4, DD2-5, NN-HIGH-1 |
| 35 | DD2-7, DD2-8, DD2-9, DD2-10 |
| 36 | NN-CRIT-2 (parity_checker delete), NN-CRIT-3 (6 risk modules delete) |
| 37 | OO MIGRATION-GAP (smoke check) |
| 38 | NN-MED-1, NN-MED-2, NN-MED-3, NN-MED-4 (deletions) |
| 39 | HH2 plan-feedback (entries_blocked uplift) |
| 40 | HH R-1 stages 1/1.1/1.2 (extracted) |

For each marker, run a targeted `grep -rn 'V8 <ID>' backend/ scripts/ tests/` and confirm presence.

### 2. Behavioral test execution

```
./venv/bin/python -m pytest tests/test_wave32_fixes.py tests/test_wave33_fixes.py tests/test_wave34_fixes.py tests/test_wave35_fixes.py tests/test_wave36_fixes.py tests/test_wave37_fixes.py tests/test_wave38_fixes.py tests/test_wave39_fixes.py tests/test_wave40_fixes.py tests/test_reachability_v8.py tests/test_organism_live_engine.py tests/test_safety_invariants.py tests/test_multi_tick_state.py -q --timeout=30
```

Expected: ≥147 passed.

### 3. Same-class scans

For each wave's same-class grep (cited in the commit body), re-run on rc-1.5-curated @ db1a3fc and assert count = 0.

### 4. Brain coherence + container health

```
cat organism_brain/manifest.json | jq '{generation, total_trades, ml_is_trained, best_sharpe}'
docker ps | grep intra
```

Compare against the V8-end snapshot (gen=168, trades=498, ml_is_trained=true).

### 5. Wave-28 marker check — REQUIRED MODE on HEAD~10..HEAD

```
./venv/bin/python scripts/ci/check_wave_markers.py --base HEAD~10 --head HEAD
```

Expected: 0 fails on the wave 32-40 commits. (They were authored under wave-28 rules so should pass.)

### 6. Migration tree integrity

```
./venv/bin/python scripts/ci/check_migrations.py
```

Expected: 0 exit, single head.

### 7. Deleted-orphan-module isolation

```
grep -rn 'from backend\.mlops\|from backend\.brokers\.alpaca_production\|from backend\.brokers\.broker_failover\|from backend\.optimization\.portfolio_optimizer\|from backend\.risk\.advanced_risk\|from backend\.risk\.advanced_risk_manager\|from backend\.ml\.\(data_processing\|ensemble_framework\|model_management\|pipeline\|prediction_service\|sentiment\|staleness_detector\|validation\)' backend/ tests/ --include='*.py'
```

Expected: 0 hits (all deletes are clean).

## Output

`artifacts/audit/v9_reports/track_z7_closure_regression.md` with:
- Per-marker presence table (~25 markers)
- Test pass count
- Same-class scan counts (per wave)
- Brain coherence delta
- Wave-28 marker check result
- Migration smoke check result
- Orphan-isolation check result
- "Closure regressions: N" + TL;DR

Quality bar: 0-2 findings expected. Anything > 2 = a wave's marker got dropped. End with one-paragraph TL;DR.
