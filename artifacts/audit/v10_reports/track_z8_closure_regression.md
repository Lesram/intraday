# Track Z8 v10 — Closure Regression on Waves 41-49

**Repo**: `/Users/marselkei/VS/intra`
**Branch**: `rc-1.5-curated` @ `c048103` (HEAD); wave 41-49 closure commits `0e3f2a4 → 35a1fe9` all reachable from HEAD
**Baseline**: V9 synthesis `805c7e2`
**Audit date**: 2026-05-02
**Mode**: read-only (`pytest`/grep/read; no fixes, no commits, no push)

---

## 1. Per-marker presence table

Per-finding `grep -rn 'V9 <ID>' backend/ scripts/ tests/` results.
A "marker site" is the file where the canonical fix lives (see commit body); secondary citations are accepted as long as the primary site is present.

| Wave | Finding | Markers | Primary site | Status |
|---|---|---:|---|:---:|
| 41 | PP-1 | 4 | `backend/organism/brain_persistence.py` | OK |
| 41 | PP-2 | 2 | `backend/organism/brain_persistence.py` (lines 242, 274) | OK |
| 41 | PP-3 | 3 | `backend/infra/alerting.py` (lines 246, 300, 319) | OK |
| 41 | PP-4 | 1 | `backend/api/lifespan.py` (line 152) | OK |
| 41 | UU-1 | 1 | `backend/organism/live_engine.py` (line 2190) | OK |
| 41 | UU-2 | 1 | `backend/api/routes/auth.py` | OK |
| 41 | UU-3 | 2 | `backend/organism/brain_persistence.py` | OK |
| 42 | AA3-1 | 3 | `backend/infra/security.py`, `backend/api/routes/auth.py` | OK |
| 42 | AA3-2 | 2 | `backend/infra/security.py` | OK |
| 42 | AA3-3 | 1 | `backend/api/routes/auth.py` | OK |
| 43 | DD3-2 | 3 | `backend/integrations/alpaca_stream.py` | OK |
| 43 | DD3-3 | 1 | `backend/organism/live_engine.py` | OK |
| 44 | DD3-1 | 3 | `backend/organism/pyramider.py` | OK |
| 44 | DD3-4 | 1 | `backend/organism/live_engine.py` | OK |
| 44 | DD3-5 | 1 | `backend/organism/live_engine.py` | OK |
| 45 | PP-5 | 2 | `backend/organism/live_engine.py` | OK |
| 45 | PP-6 | 3 | `backend/organism/streaming_data_provider.py`, `backend/organism/live_engine.py` | OK |
| 46 | TT-2 | 2 | `backend/organism/live_engine.py` (lines 1553, 1560) | OK |
| 47 | TT-4 | 1 | `backend/data/alpaca_client.py` | OK |
| 47 | TT-5 | 2 | `backend/organism/continuous_learner.py` | OK |
| 47 | AA3-4 | 1 | `backend/infra/security.py` (lines 576, 595) | OK |
| 48 | Z7-1 | 1 | `backend/ml/__init__.py` | OK |
| 48 | W4-1 | 2 | `scripts/ci/check_wave_markers.py` | OK |
| 48 | W4-3 | 1 | `scripts/ci/check_wave_markers.py` | OK |
| 49 | UU-4 | 0 | docs (`docs/engineering/WAVE49_COSMETIC_AND_OBSERVATIONS.md`) | DEFERRED — expected |
| 49 | DD3-6 | 0 | docs (`docs/engineering/WAVE49_COSMETIC_AND_OBSERVATIONS.md`) | OBSERVE — expected |

**24 / 24 source-code markers present.** UU-4 and DD3-6 are intentionally docs-only (deferred / observation respectively); both referenced in `docs/engineering/WAVE49_COSMETIC_AND_OBSERVATIONS.md`. **Zero closure regressions in source.**

---

## 2. Behavioral test execution

```
./venv/bin/python -m pytest \
  tests/test_wave32_fixes.py … tests/test_wave48_fixes.py \
  tests/test_reachability_v8.py tests/test_organism_live_engine.py \
  tests/test_safety_invariants.py tests/test_multi_tick_state.py \
  -q --timeout=30
```

**Result: `190 passed, 2 warnings in 21.51s`** (≥190 expected — met).
- `test_wave40_fixes.py` does exist on disk despite earlier doubt; collection clean.
- Two warnings are pytest-hypothesis `norecursedirs` and passlib `crypt` deprecation — both pre-existing, unrelated to wave 41-49.

---

## 3. Same-class scan re-runs

Each wave's commit body cited targeted greps that should remain at the post-fix count (typically 0 for "no remaining instances of the bad pattern", or N>0 where the pattern still legitimately appears in the fix's helper or its V9-marker comment). I re-ran each cited grep on HEAD and verified the result reflects fix-state, not regression:

| Wave | Cited grep | Count | Verdict |
|---|---|---:|:---:|
| 41 | `asyncio.create_task(send_alert(` in `live_engine.py` | 0 | clean |
| 41 | `except Exception:\s*$` in `brain_persistence.py` | 10 | **non-zero by design** — PP-2 only narrowed IO/atomic-write paths; remaining bare excepts cover unrelated guards. Not a regression. |
| 41 | `except Exception:\s*pass$` in `auth.py` | 0 | clean |
| 41 | `Database init failed.*continuing` warning | 0 | clean |
| 41 | `df.to_csv(target /` in `brain_persistence.py` | 0 | clean |
| 42 | `blacklist_token\|is_token_blacklisted` in `auth.py` | 7 | expected — these are the new wave-42 helper calls + docstring; not regressions |
| 42 | `"token_type"\|token_type !=` in `security.py` | 5 | expected — wave-42 added the type discrimination |
| 42 | `is_token_blacklisted` in `security.py` | 2 | expected — checker is invoked in `verify_token` |
| 43 | `qty=Decimal(str(filled_qty))` in `alpaca_stream.py` | 2 | expected — both partial-fill paths use the cast (DD3-2 fix) |
| 43 | `_exit_cooldown[sym]` in `live_engine.py` | 10+ | expected — DD3-3 added cooldown set sites at exit branches; cited grep counts were always >0 in the fix commit |
| 44 | `position.layer_count == [12]` in `pyramider.py` | 1 | expected — DD3-1 retains the layer-1 cut path |
| 44 | `_pending_entry_order_ids\|cancel_order` in `live_engine.py` | 0 | clean (DD3-4) |
| 44 | `symbol_fitness.get(symbol, 0\.5)` in `live_engine.py` | 0 | clean (DD3-5) |
| 45 | `last_update_time` in `live_engine.py` | 2 | expected — both occurrences are PP-5 commentary + the canonical use site |
| 45 | `Market scan failed` warning in `live_engine.py` | 1 | expected — PP-6 still logs the warning, but now also alerts/raises |
| 46 | `asyncio.wait_for` in `live_engine.py` | 2 | expected — TT-2 added the wait_for wrap |
| 47 | `self._rate_limit()` in `alpaca_client.py` | 3 | expected — TT-4 retains sync path call sites + docstring |
| 47 | `leeway=` in `security.py` | 2 | expected — AA3-4 added `leeway=JWT_CLOCK_SKEW` |
| 47 | `record_trade\|trade_history.append` in `continuous_learner.py` | 2 | expected — TT-5 deduplication still calls the method |
| 48 | `WAVE_COMMIT_RE = re.compile` in `check_wave_markers.py` | 1 | expected — W4-1 added it |
| 48 | `from .staleness_detector` in `backend/ml/__init__.py` | 0 | clean (Z7-1) |

**0 same-class scans indicate a true regression.** All non-zero counts reflect the fix code itself (helper calls, marker comments, intentional retained behavior). The mechanical wave-marker checker reports them as `[FAIL]` because its assertion is "count must equal 0" but the original commit bodies cited the greps as observability scans, not zero-tolerance gates. See finding F-Z8-1.

---

## 4. Brain coherence + container health

```
$ cat organism_brain/manifest.json | jq '{generation,total_trades,ml_is_trained,best_sharpe}'
{
  "generation": 168,
  "total_trades": 498,
  "ml_is_trained": true,
  "best_sharpe": 3.4363
}
```

**Delta vs V9-end snapshot (MEMORY @ 2026-05-01)**:
| Field | V9-end | Now | Delta |
|---|---|---|---|
| generation | 161 | 168 | +7 (continued evolution) |
| total_trades | 482 | 498 | +16 (Friday session trades) |
| ml_is_trained | true | true | stable |
| best_sharpe | 3.44 | 3.4363 | stable |

Brain is durable and growing monotonically; manifest mtime `May 2 23:11` confirms recent successful persistence. No collapse, no reset, ML model intact.

```
$ docker ps | grep intra
intra-api-1     Up 11 hours (healthy)   0.0.0.0:8000->8000/tcp
intra-redis-1   Up 12 hours (healthy)   0.0.0.0:6379->6379/tcp
```

API + Redis healthy. (No `intra-postgres` row visible — operator runs PG outside the compose stack on this branch; not in scope for Z8.)

---

## 5. Wave-28 marker checker on HEAD~10..HEAD

```
$ ./venv/bin/python scripts/ci/check_wave_markers.py --base HEAD~10 --head HEAD
[FAIL] 17 wave-commit check(s) failed
```

The reported failures break into two classes, **both spurious** for closure-regression purposes:

1. **`no finding-IDs cited in commit body`** on waves 42, 43, 48 — the commit subjects/bodies use em-dash (`—`) and slash-list formats (`PP-1/2/3/4`) that the W4-1 regex parses inconsistently. Source markers are present (Section 1); the checker is the limited surface, not the closure.
2. **`re-ran, count=N` non-zero** — see Section 3. The checker treats *any* non-zero result as a fail, but the commit bodies cited those greps as observability spot-checks, often with intentional non-zero post-fix counts (e.g., the V9 marker comment itself contains the searched literal).

The prompt explicitly anticipated wave-49 may show as needing markers (acceptable). What we see additionally is wave 41-48 also flagged — but only via the checker's own over-strict semantics, not via missing closure markers. **Net closure regressions = 0.**

This generates one finding (F-Z8-1) for tooling improvement, not for the closure work itself.

---

## 6. pytest collection cleanliness

```
$ ./venv/bin/python -m pytest --collect-only tests/ 2>&1 | grep -c ModuleNotFoundError
0
```

**Clean.** No import errors during collection across the entire `tests/` tree.

---

## 7. Migration smoke check

```
$ ./venv/bin/python scripts/ci/check_migrations.py
[ok] 15 migration(s) under /Users/marselkei/VS/intra/backend/migrations/versions
[ok] single head: 20260503_000001
[ok] base: 706e00fe1a28
[OK] migration tree is linear with single head.
EXIT=0
```

**Green.** Single head, linear tree, exit 0.

---

## Findings

### F-Z8-1 — Wave-marker CI checker is overly strict on commit-body grep counts and em-dash subjects (LOW, tooling)

**Severity**: LOW (tooling false-positives; does not affect closure correctness)
**File**: `scripts/ci/check_wave_markers.py`
**Symptom**: `check_wave_markers.py --base HEAD~10 --head HEAD` returns 17 failures across waves 41-48 even though all source markers are present and behavioral tests pass (190/190).

Two distinct issues compound:

1. The `WAVE_COMMIT_RE`/finding-ID extractor fails on commit subjects that use em-dash (`fix(audit-wave42): JWT lifecycle holes — AA3-1, AA3-2, AA3-3 (HIGH/MEDIUM)`) or slash-list shorthand (`PP-1/2/3/4`). Wave 41 (which uses comma-separated IDs) parses correctly; waves 42, 43, 48 don't.
2. The same-class grep verifier asserts "count = 0" for every cited grep, but commit bodies frequently cite greps as observability checks where the post-fix count is intentionally >0 (the V9-marker comment line itself often contains the searched pattern; refactored helpers retain literal call sites; new wave-46 `asyncio.wait_for` use is the *fix*, not a regression).

This is wave-48 W4-1's own enforcer turning into a noise generator. No closure marker is missing; no behavior is regressed. Recommend either (a) loosening the regex to accept em-dash and slash-list ID lists, and (b) making same-class grep counts informational (printed but not status-flagged) — or having the commit body explicitly tag each grep with `expected_count: 0` vs `expected_count: ge_1`.

**Repro**:
```
./venv/bin/python scripts/ci/check_wave_markers.py --base HEAD~10 --head HEAD
```

**Closure note**: this is a meta-finding about the checker, not about the wave 41-49 closures themselves. All 24 source markers verified present in Section 1; all 190 behavioral tests pass (Section 2).

---

## Closure regressions: 0

## TL;DR

All 24 source-code closure markers from waves 41-48 are present at their canonical sites; UU-4 (deferred) and DD3-6 (observe) are correctly docs-only in `docs/engineering/WAVE49_COSMETIC_AND_OBSERVATIONS.md`. The 190-test wave behavioral suite passes cleanly (`190 passed in 21.51s`); pytest collection has zero ModuleNotFoundError; `check_migrations.py` returns exit 0 with a single linear head. Brain coherence is intact (gen 161→168, trades 482→498, sharpe ~3.44 stable, ML still trained); `intra-api` + `intra-redis` containers are healthy. The wave-marker CI checker reports 17 failures, but every one decomposes into either (a) em-dash/slash-list parsing limits in the W4-1 regex on waves 42/43/48 commit subjects, or (b) the verifier asserting `count==0` on greps that the commit bodies cited as observability scans whose post-fix count is intentionally >0 — none indicate a missing marker or regressed behavior. Net closure regressions = 0; one LOW tooling finding (F-Z8-1) recommends relaxing the W4-1 enforcer to eliminate this category of false-positive in future audits.
