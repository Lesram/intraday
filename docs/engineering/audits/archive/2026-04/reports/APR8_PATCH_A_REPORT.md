# Apr-8 Patch A — Force-save admin route

## Verdict
COMMITTED as `be2eee8` on top of `50b2513` (Patch B). All tests green.

## Source state before edit
- HEAD: `50b2513` (Patch B — manifest sync via `_apply_live_manifest_fields`)
- Patch A-adjacent files clean before edit: `brain_persistence.py`,
  `live_engine.py`, `routes.py`, tests (only unrelated
  `monitoring/memory_monitoring.json` and untracked docs dirty).

## Root cause (recovery gap)
Every path to `BrainPersistence.save()` in the live process funnels
through `OrganismLiveEngine._save_brain()`, which enforces the
walk-forward gate at `live_engine.py:4296-4301`. When the gate
blocks, only `save_essential_state` runs — ML joblibs + reference
features + evolved params never hit disk. There was no existing
admin path to persist a full save from the live process. A redeploy
would wipe in-memory ML state. Patch A closes that gap.

## Files changed
- `backend/organism/brain_persistence.py` — `save()` accepts
  `force: bool = False` (audit-only). Default behavior unchanged.
  Log line appends " (forced)" when `force=True`.
- `backend/organism/live_engine.py` — new public method
  `OrganismLiveEngine.force_save_brain()`. Logs WARNING at entry,
  persists exit_levels + entry_metadata, calls `brain.save(force=True, ...)`
  with the exact kwargs block from `_save_brain()`, updates
  `_watchdog_last_brain_save_tick`, returns verification dict
  (`success`, `forced`, `tick`, `generation`, `total_trades`,
  `cumulative_pnl`, `best_sharpe`, `ml_is_trained`, `feature_count`,
  `timestamp`). Exceptions are caught and returned as
  `{"success": False, "error": ...}` — does not raise.
- `backend/organism/routes.py` — new route
  `POST /api/v1/organism/save` (handler: `force_save`). Requires
  `?force=true` query param (HTTP 400 otherwise). Uses existing
  `_get_engine(request)` helper against `request.app.state.organism_scheduler._engine`.
  Admin-gated via `Depends(require_admin)`. Calls
  `engine.force_save_brain()` via `asyncio.to_thread`. Added
  `import asyncio` at the top of the file.
- `tests/test_apr8_patch_a_force_save.py` — new file, 13 tests.

## Safety constraints respected
- `save_essential_state` untouched (Patch B scope).
- `walk_forward_gate` untouched (Patch C scope).
- `_last_sharpe_decay_date` not reintroduced.
- No scheduler changes.
- No existing route touched.
- No strategy/threshold/sizing/exit/phase logic changed.
- `_save_brain` still calls `walk_forward_gate` + `save_essential_state`
  — verified by a static sanity regression test.

## Tests
### New (Patch A): 13 passed
1. `test_save_force_false_default_behavior`
2. `test_save_force_true_still_full_save`
3. `test_force_save_brain_calls_brain_save_force_true`
4. `test_force_save_brain_bypasses_walk_forward_gate`
5. `test_force_save_brain_updates_watchdog_tick`
6. `test_force_save_brain_persists_exit_levels`
7. `test_force_save_brain_graceful_exception`
8. `test_force_save_brain_nonfinite_sharpe_returns_none`
9. `test_route_rejects_without_force_query` (HTTP 400)
10. `test_route_calls_force_save_brain_when_forced`
11. `test_route_returns_409_when_engine_inactive`
12. `test_route_has_require_admin_dependency` (FastAPI DI tree walk)
13. `test_save_brain_still_calls_walk_forward_gate` (regression)

### Regression (Patch B + Apr-7 P0/P1): 20 passed
`tests/test_apr7_p0_p1_fixes.py` + `tests/test_apr8_patch_b_manifest_sync.py`

### Organism subset: 107 passed
`test_organism_live_engine.py`, `test_organism_engine_scenarios.py`,
`test_multi_tick_state.py`, `test_safety_invariants.py`,
`test_self_evolution.py` — 107/107 pass in 65s.

### Totals
- Patch A + Patch B + Apr7: **33 passed, 0 failed**
- Organism regression: **107 passed, 0 failed**

## Commit
- SHA: `be2eee8`
- Parent: `50b2513`
- 4 files changed, 454 insertions(+), 1 deletion(-)

## Route summary
- Path: `POST /api/v1/organism/save`
- Query param: `force=true` (mandatory; HTTP 400 otherwise)
- Auth: `Depends(require_admin)` — verified via FastAPI dependant
  tree walk in test #12
- Engine binding: `_get_engine(request)` reads
  `request.app.state.organism_scheduler._engine` — live instance,
  NOT a new persistence object
- Call shape: `await asyncio.to_thread(engine.force_save_brain)`
- HTTP 409 when engine is not active

## End-to-end implementation status
Force-save path is implemented end-to-end:
1. `BrainPersistence.save(force=...)` — audit flag accepted
2. `OrganismLiveEngine.force_save_brain()` — gate-bypass wrapper
3. `POST /api/v1/organism/save?force=true` — admin entry point

## Worktree status after commit
Clean w.r.t. Patch A. Pre-existing unrelated files (monitoring JSON,
many untracked docs/bundles/zips) remain untouched.

## Remaining pre-open steps
Deploy + verify is now the only remaining pre-open step for Patch A.
No other blockers. The container `intra-api-1` currently runs older
pre-Patch-A code; a single rebuild+restart cycle is required before
the `/organism/save` route and `force_save_brain()` method are
reachable from the live process.

## Bundle
- `APR8_PATCH_A_REPORT.md` — this file
- `apr8_patch_a_bundle/` — changed source files, new test file,
  `test_output.txt`, `commit_stat.txt`
