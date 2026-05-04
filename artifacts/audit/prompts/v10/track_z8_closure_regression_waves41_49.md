# Track Z8 v10 — Closure Regression on Waves 41-49

V9 closed 25 of 32 actionable findings via waves 41-49 (commits `0e3f2a4` → `35a1fe9`). **Z8 verifies every closure marker is still in place** and no later commit silently dropped them.

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `35a1fe9`. Baseline: `805c7e2` (V9 synthesis commit, before wave 41).

## Method

### 1. Per-finding marker check

For each closed finding, verify the source-code marker (`V9 <FINDING-ID> / Wave-<N>`) is present at the expected file site.

| Wave | Markers expected |
|---|---|
| 41 | PP-1, PP-2, PP-3, PP-4, UU-1, UU-2, UU-3 |
| 42 | AA3-1, AA3-2, AA3-3 |
| 43 | DD3-2, DD3-3 |
| 44 | DD3-1, DD3-4, DD3-5 |
| 45 | PP-5, PP-6 |
| 46 | TT-2 |
| 47 | TT-4, TT-5, AA3-4 |
| 48 | Z7-1, W4-1, W4-3 |
| 49 | (docs only) UU-4 deferred, DD3-6 observe |

For each marker, run a targeted `grep -rn 'V9 <ID>' backend/ scripts/ tests/` and confirm presence.

### 2. Behavioral test execution

```
./venv/bin/python -m pytest \
  tests/test_wave32_fixes.py tests/test_wave33_fixes.py \
  tests/test_wave34_fixes.py tests/test_wave35_fixes.py \
  tests/test_wave36_fixes.py tests/test_wave37_fixes.py \
  tests/test_wave38_fixes.py tests/test_wave39_fixes.py \
  tests/test_wave40_fixes.py tests/test_wave41_fixes.py \
  tests/test_wave42_fixes.py tests/test_wave43_fixes.py \
  tests/test_wave44_fixes.py tests/test_wave45_fixes.py \
  tests/test_wave46_fixes.py tests/test_wave47_fixes.py \
  tests/test_wave48_fixes.py tests/test_reachability_v8.py \
  tests/test_organism_live_engine.py tests/test_safety_invariants.py \
  tests/test_multi_tick_state.py -q --timeout=30
```

Expected: ≥190 passed.

### 3. Same-class scans

For each wave's same-class grep (cited in commit body), re-run on rc-1.5-curated @ HEAD; assert count = 0.

### 4. Brain coherence + container health

```
cat organism_brain/manifest.json | jq '{generation, total_trades, ml_is_trained, best_sharpe}'
docker ps | grep intra
```

Compare against the V9-end snapshot.

### 5. Wave-28 marker check on HEAD~10..HEAD

```
./venv/bin/python scripts/ci/check_wave_markers.py --base HEAD~10 --head HEAD
```

Expected: 0 fails on the wave 41-49 commits. Note that wave-49 is docs-only and may show as needing markers — that's acceptable.

### 6. pytest --collect-only must succeed

```
./venv/bin/python -m pytest --collect-only tests/ 2>&1 | grep -c ModuleNotFoundError
```

Expected: 0.

### 7. Migration smoke check still green

```
./venv/bin/python scripts/ci/check_migrations.py
```

Expected: 0 exit, single head.

## Output

`artifacts/audit/v10_reports/track_z8_closure_regression.md` with:
- Per-marker presence table (~25 markers)
- Test pass count
- Same-class scan counts (per wave)
- Brain coherence delta
- Wave-28 marker check result
- pytest collection cleanliness
- Migration smoke check result
- "Closure regressions: N" + TL;DR

Quality bar: 0-2 findings expected.
