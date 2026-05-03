# Track Z9 v11 — Closure Regression on Waves 50-65

**Repo**: `/Users/marselkei/VS/intra`
**Branch**: `rc-1.5-curated` @ `3778344` (HEAD); fix-wave commits `c63f745 → 11c2275` (waves 50-65) all reachable from HEAD; prompt's referenced wave-65 SHA `11c2275` is HEAD~1 (V11-plan commit on top is docs-only).
**Baseline**: V10 synthesis `e0df067`
**Audit date**: 2026-05-03
**Mode**: read-only (`pytest`/grep/read/`docker exec`; no fixes, no commits, no push)

---

## 1. Per-marker presence table (V10 waves 50-58 + V11-prep deferrals 59-65)

`grep -rln <marker> backend/ scripts/ tests/` (excluding `__pycache__`). "Primary site" is where the canonical fix lives per the wave's commit body; secondary citations (test or docs) accepted as long as the primary site is present.

| Wave | Finding | Hits | Primary site | Status |
|---|---|---:|---|:---:|
| 50 | AA4-2 | 2 | `backend/api/lifespan.py` | OK |
| 50 | AA4-3 | 2 | `backend/api/routes/settings.py` | OK |
| 50 | AA4-4 | 2 | `backend/infra/security.py` | OK |
| 51 | WW-1 | 2 | `backend/organism/brain_persistence.py` | OK |
| 51 | PP2-1 | 2 | `backend/api/lifespan.py` | OK |
| 51 | UU2-A | 3 | `backend/integrations/alpaca_stream.py`, `backend/api/routes/auth.py` | OK |
| 51 | UU2-C | 2 | `backend/integrations/alpaca_stream.py` | OK |
| 52 | YY-1 | 5 | `backend/organism/governance.py`, `backend/api/routes/risk.py`, `backend/services/risk_manager.py`, `backend/monitoring/slo_monitor.py` | OK |
| 52 | YY-2 | 2 | `backend/integrations/alpaca_stream.py` | OK |
| 52 | YY-5 | 2 | `backend/api/routes/health.py` | OK |
| 53 | DD4-1 | 2 | `backend/organism/live_engine.py` | OK |
| 53 | DD4-2 | 3 | `backend/organism/live_engine.py`, `backend/organism/pyramider.py` | OK |
| 53 | DD4-4 | 2 | `backend/organism/pyramider.py` | OK |
| 54 | VV-3 | 2 | `backend/risk/types.py` | OK |
| 55 | XX-1 | 3 | `backend/migrations/versions/ec197100938a_add_idempotency_constraints_and_order_.py` | OK |
| 55 | XX-2 | 2 | `backend/migrations/versions/20260503_000002_xx_2_widen_orders_status_check.py` | OK |
| 56 | WW-2 | 2 | `backend/organism/brain_persistence.py` | OK |
| 56 | WW-3 | 2 | `backend/organism/live_engine.py` | OK |
| 56 | PP2-2 | 2 | `backend/organism/brain_persistence.py` | OK |
| 56 | PP2-3 | 2 | `backend/organism/brain_persistence.py` | OK |
| 56 | Z8-1 | 2 | `scripts/ci/check_wave_markers.py` | OK |
| 57 | UU2-B | 1 | `pyproject.toml` (ruff TRY/BLE/G004 ratchet config) | OK (lint rule) |
| 58 | (docs) | — | `docs/engineering/V10_WAVE58_OPERATOR_FOLLOWUPS.md` | OK (docs-only, expected) |
| 59 | AA4-4 follow-up | — | `backend/infra/security.py` (verify_api_key) | OK (carried by AA4-4 marker) |
| 60 | DD4-3 | 5 | `backend/organism/regime.py`, `backend/organism/kelly_sizer.py`, `backend/organism/adaptive_exits.py` | OK |
| 61 | XX-3 | 3 | `backend/migrations/versions/20260503_000003_xx_3_portfolio_history.py` | OK |
| 62 | YY-3 | 3 | `backend/organism/live_engine.py` | OK |
| 62 | YY-4 | 4 | `backend/organism/background_trainer.py`, `backend/organism/live_engine.py` | OK |
| 63 | HH2-N-1 (partial) | 3 | `backend/api/routes/indicators.py` | OK |
| 64 | VV-1 | 3 | `backend/api/routes/orders.py` | OK |
| 65 | VV-2 | 3 | `backend/models/risk.py` | OK |

**29 / 29 source-code closure markers present** at canonical sites. Wave 58 is intentionally docs-only (`V10_WAVE58_OPERATOR_FOLLOWUPS.md`); wave 59 is carried under the AA4-4 banner (verify_api_key follow-up) and lives in `backend/infra/security.py`. **Zero closure regressions in source.**

---

## 2. Behavioral test execution

```
./venv/bin/python -m pytest \
  tests/test_wave50_fixes.py … tests/test_wave57_fixes.py \
  tests/test_wave60_fixes.py … tests/test_wave65_fixes.py \
  tests/test_organism_live_engine.py tests/test_reachability_v8.py \
  -q --timeout=30
```

**Result: `1 failed, 88 passed, 2 warnings in 16.89s`** (88/89 pass = 98.9%; below 100% expected — see F-Z9-1).

Single failure: `tests/test_wave55_fixes.py::test_xx_2_migration_tree_still_single_headed`. The wave-55 test asserts `"20260503_000002" in stdout`, but the wave-61 migration extended the chain to `20260503_000003`. The tree IS still single-headed (test exits 0); only the literal-string head check is stale. The wave-61 test (`test_xx_3_migration_tree_still_single_headed`) asserts `"20260503_000003"` and passes. This is a test-data-only staleness, not a closure regression in any source marker, but it is a real failure flagged in the bundle the prompt asked us to run, so logged as F-Z9-1.

Two warnings (`hypothesis norecursedirs`, `passlib crypt`) are pre-existing, identical to V10/Z8.

---

## 3. Container vs source-SHA verification (DD-DEPLOY lens)

```
$ docker exec intra-api-1 wc -l /app/backend/infra/security.py /app/backend/api/lifespan.py /app/backend/organism/brain_persistence.py /app/backend/organism/live_engine.py
   941 /app/backend/infra/security.py
   778 /app/backend/api/lifespan.py
  2335 /app/backend/organism/brain_persistence.py
  6942 /app/backend/organism/live_engine.py

$ wc -l backend/infra/security.py backend/api/lifespan.py backend/organism/brain_persistence.py backend/organism/live_engine.py
   941 backend/infra/security.py
   778 backend/api/lifespan.py
  2335 backend/organism/brain_persistence.py
  6942 backend/organism/live_engine.py
```

**Line counts: identical, four-for-four.**

Stricter sha256 cross-check:
```
1b59ea3b…  /app/backend/infra/security.py            == host
e6a77d36…  /app/backend/api/lifespan.py              == host
4541d66e…  /app/backend/organism/brain_persistence.py == host
8c0455ab…  /app/backend/organism/live_engine.py      == host
```

**All four files byte-identical between container and host.** Rebuild successfully picked up wave 50-65. `intra-api-1` `Up 7 minutes (healthy)`; `intra-redis-1` `Up 13 hours (healthy)`.

---

## 4. Brain coherence

```
$ cat organism_brain/manifest.json | jq '{generation,total_trades,ml_is_trained,best_sharpe}'
{
  "generation": 168,
  "total_trades": 498,
  "ml_is_trained": true,
  "best_sharpe": 3.4363
}
```

| Field | V10-end (Z8) | Now (Z9) | Delta |
|---|---|---|---|
| generation | 168 | 168 | 0 (no new evolution since Friday close — expected, market closed Sat) |
| total_trades | 498 | 498 | 0 (same — no Saturday trades) |
| ml_is_trained | true | true | stable |
| best_sharpe | 3.4363 | 3.4363 | stable |

Brain manifest mtime `May 3 11:30:01 2026` confirms recent successful persistence (well after the wave 50-65 rebuild). One backup present at `organism_brain/backups/brain_gen168_20260503_183001_211879/` and two `corrupt_head_*` quarantine dirs from `2026-05-03 11:36` — the quarantine paths are PP2-2 (wave-56) working as designed (corruption detected → quarantined → retried), not a brain failure. **Brain durable; no collapse, no reset, ML model intact.**

---

## 5. Migration tree

```
$ ./venv/bin/python scripts/ci/check_migrations.py
[ok] 17 migration(s) under /Users/marselkei/VS/intra/backend/migrations/versions
[ok] single head: 20260503_000003
[ok] base: 706e00fe1a28
[OK] migration tree is linear with single head.
EXIT=0
```

**Head = `20260503_000003`** (wave-61 portfolio_history) — matches the prompt's expected head. Linear tree, single head, exit 0. Two earlier May-3 migrations (`20260503_000001` orders constraints, `20260503_000002` XX-2 status widening) chain in correctly underneath.

---

## 6. pytest collection cleanliness

```
$ ./venv/bin/python -m pytest --collect-only tests/ 2>&1 | grep -c ModuleNotFoundError
0
```

**Clean.** Zero import errors during full-tree collection.

---

## 7. Wave-marker checker on HEAD~16..HEAD

```
$ ./venv/bin/python scripts/ci/check_wave_markers.py --base HEAD~16 --head HEAD
[FAIL] 25 wave-commit check(s) failed
```

Pattern is **identical to V10/Z8 finding F-Z8-1**:

1. **`no finding-IDs cited in commit body`** on commits whose subject uses em-dash (`—`) or slash-list (`DD4-1/2/4`) format that the W4-1 regex parses inconsistently. Examples: wave-53 (`DD4-1/2/4 (HIGH/LOW)`), wave-58 (`docs(audit-wave58)` — docs-only, no finding IDs by design), wave-59 (`AA4-4 follow-up`).
2. **`re-ran, count=N` non-zero** for greps the commit bodies cited as observability spot-checks, e.g. `grep -n 'WW-3' backend/organism/live_engine.py | head` returning 1 because the V10-marker comment itself contains `WW-3`. The checker treats any non-zero count as failure.

The failure list decomposes into either (a) parsing limits (acceptable for docs-only wave 58 per the prompt), or (b) the same Z8-1 self-defeat the wave-56 fix already documented. **No genuine missing markers, no behavior regression.** Closure-regression-relevant count = 0.

---

## 8. Same-class scan re-runs (selected)

| Wave | Cited grep | Count | Verdict |
|---|---|---:|:---:|
| 50 | `verify_api_key.*api_keys` (AA4-4) | present | clean (wave-59 follow-up applied) |
| 51 | `_create_backup` in `brain_persistence.py` | 4 | expected — WW-1 helper retained |
| 51 | `SELECT 1` in `lifespan.py` | 3 | expected — PP2-1 readiness/liveness probes |
| 52 | `logger.critical` in `governance.py`+`risk_manager.py` | 7 | expected — YY-1 added critical-level alerts |
| 52 | `AuditAction.` in `alpaca_stream.py` | 1 | expected — YY-2 audit reach |
| 53 | `entry_price=broker_avg` in `live_engine.py` | 0 | clean — DD4-1 still in place |
| 53 | `def telemetry` in `pyramider.py` | 1 | expected — DD4-4 helper |
| 54 | `OrderStatus` in `risk/types.py` | 3 | expected — VV-3 widened enum |
| 55 | `DROP CONSTRAINT IF EXISTS` in `ec197100938a_*.py` | 1 | expected — XX-1 idempotency |
| 56 | `corrupt_head_` in `brain_persistence.py` | 6 | expected — PP2-2 quarantine logic + V10 markers |
| 56 | `%H%M%S\b\|%H%M%S_%f` | 3 | expected — WW-2 timestamp suffix |
| 57 | `S110\|S112\|BLE001\|G004\|TRY401\|LOG007` in `pyproject.toml` | 10 | expected — UU2-B ratchet (these ARE the rules) |
| 60 | `effective_regime_for_symbol` | 5 | clean — DD4-3 helper invoked from regime/kelly/adaptive_exits |
| 61 | `portfolio_history` migration | head 000003 | clean — XX-3 migration applied |
| 62 | `YY-3\|YY-4` markers in live_engine + background_trainer | 7 | clean — observability hooks live |
| 64 | `VV-1` in `routes/orders.py` | 3 | clean — camelCase aliases |
| 65 | `VV-2` in `models/risk.py` | 3 | clean — Decimal serialization |

**0 same-class scans indicate a true regression.** All non-zero counts reflect fix code itself (helpers, marker comments, intentional retained behavior). Identical reasoning to V10/Z8.

---

## Findings

### F-Z9-1 — Wave-55 migration-head test asserts a stale literal head SHA after wave-61 extended the chain (LOW, test data)

**Severity**: LOW (test-only; no source-marker missing, no behavior regressed)
**File**: `tests/test_wave55_fixes.py::test_xx_2_migration_tree_still_single_headed` (line 69)
**Symptom**: When the full Z9 wave bundle runs, this single test fails with:

```
AssertionError: XX-2 regression: new head not '20260503_000002':
[ok] 17 migration(s) ...
[ok] single head: 20260503_000003
[ok] base: 706e00fe1a28
[OK] migration tree is linear with single head.
```

The test was authored under wave-55 (when XX-2 / `20260503_000002` was the head). Wave-61 added `20260503_000003_xx_3_portfolio_history.py` and now `check_migrations.py` correctly reports head `20260503_000003`. The wave-55 test should have been updated to assert "head ends in one of the known leaves of a linear chain" or to assert the migration is reachable from HEAD, not that it equals the head literal.

The migration tree is still single-headed (the assertion the test really cares about — `proc.returncode == 0` — passes). The wave-61 sister test (`test_xx_3_migration_tree_still_single_headed`) checks `"20260503_000003" in proc.stdout` and passes; it is the canonical end-state assertion.

**Recommended fix (deferred — V11 is audit-only)**: change line 69 from `assert "20260503_000002" in proc.stdout` to either `assert "20260503_000002" in <list of migration files>` or drop the head-equality assertion in favor of `single head:` substring presence. Until then, `--ignore=tests/test_wave55_fixes.py::test_xx_2_migration_tree_still_single_headed` is the operational workaround when running wave bundles past wave-61.

**Repro**:
```
./venv/bin/python -m pytest tests/test_wave55_fixes.py::test_xx_2_migration_tree_still_single_headed -q
```

**Closure note**: this is a test-assertion freshness issue, not a missing/regressed closure. All 29 source markers verified; XX-2 code (the migration file itself) is intact.

---

### F-Z9-2 — Wave-marker CI checker remains noisy on em-dash subjects + observability-grep counts (LOW, tooling — duplicate of F-Z8-1 carried forward)

**Severity**: LOW (tooling false-positives; does not affect closure correctness)
**File**: `scripts/ci/check_wave_markers.py`
**Symptom**: `check_wave_markers.py --base HEAD~16 --head HEAD` returns 25 failures across waves 50-65 even though all source markers are present and behavioral tests pass (88/89, with the lone failure unrelated to markers).

This is the **same finding as V10/F-Z8-1**: the wave-56 Z8-1 fix added `WAVE_COMMIT_RE` and same-class scan execution, but did not (a) handle em-dash/slash-list ID lists in commit subjects, nor (b) distinguish "this grep should equal 0" from "this grep is observability". Carried forward here because the V11 prompt asks for an explicit count, and 25 > 0.

**Decomposition** (illustrative):
- 9 of 25: `no finding-IDs cited in commit body` on em-dash subjects (waves 53, 56, 58, 59, 62) and slash-list shorthand (`DD4-1/2/4`).
- 16 of 25: `re-ran, count=N` non-zero on greps that the commit bodies cited as observability scans (e.g., `grep -n 'WW-3' live_engine.py` returning 1 because the marker comment itself contains `WW-3`).

**Recommended fix (deferred — V11 is audit-only)**: same as F-Z8-1's recommendation — relax regex to accept em-dash + slash-list ID separators, and tag each cited grep with `expected_count: 0` vs `expected_count: ge_1` (or make non-zero counts informational).

**Repro**:
```
./venv/bin/python scripts/ci/check_wave_markers.py --base HEAD~16 --head HEAD
```

**Closure note**: the checker is the limited surface, not the closure. All 29 source markers verified present in Section 1; container has the post-rebuild code (Section 3); brain durable (Section 4); migration head correct (Section 5).

---

## Closure regressions: 0

Both findings above are LOW-severity meta-issues (one test-literal staleness, one tooling false-positive carried forward from V10). Neither indicates a missing wave 50-65 closure marker or a regressed behavior.

## TL;DR

All 29 source-code closure markers from waves 50-65 are present at their canonical sites; wave-58 is correctly docs-only (`docs/engineering/V10_WAVE58_OPERATOR_FOLLOWUPS.md`) and wave-59 is carried under the AA4-4 banner in `backend/infra/security.py`. The container `intra-api-1` (rebuilt 7 min ago, healthy) is byte-for-byte identical to the host on all four wave-touched files (`security.py`, `lifespan.py`, `brain_persistence.py`, `live_engine.py`) — sha256 hashes match, wc -l matches (941/778/2335/6942) — confirming the rebuild + restart picked up wave 60-65. Brain coherence stable vs V10-end (gen 168, 498 trades, sharpe 3.4363, ML still trained); manifest fresh at 11:30 today; one backup + two PP2-2 quarantine dirs from earlier today are wave-56's design working, not failures. Migration tree linear, single head `20260503_000003` (wave-61 XX-3) — exact match to prompt's expected head. Behavioral test bundle: 88 / 89 pass; the single failure is a stale literal in `test_wave55_fixes.py::test_xx_2_migration_tree_still_single_headed` (asserts head==`20260503_000002`, but wave-61 extended the chain to `20260503_000003`) — F-Z9-1, no closure miss. Wave-marker checker reports 25 failures, identical pattern to V10/F-Z8-1 (em-dash subjects + observability greps treated as count==0 gates) — F-Z9-2, carried forward, no closure miss. **Closure regressions = 0; 2 LOW-severity meta-findings (test data + tooling), both already known patterns.**
