# Patch F-lite — Essential-save trained-state guard

**Date**: 2026-04-09 UTC (post-Patch-E deploy window)
**Commit**: `3528162`
**Parent**: `62256d7` (Patch E)
**Status**: COMMITTED, not deployed

## Root cause addressed

Two brain wipe incidents observed:
- 2026-04-08 02:08:47 UTC
- 2026-04-09 02:58:52 UTC

Both wipes wrote a manifest with `generation=0, total_trades=0, ml_is_trained=false, feature_count=0` while preserving `best_sharpe` (via Patch B's `np.isfinite(-inf)` fallback) and incrementing `total_runs`.

The second wipe occurred ~90 minutes AFTER the Patch A/B/C deploy at `01:25 UTC`, proving that deploy did not close the failure mode. Investigation traced the writer to `BrainPersistence.save_essential_state()` rather than `BrainPersistence.save()`. Evidence:

1. **Grep audit**: Only `backend/organism/brain_persistence.py` and `backend/organism/live_engine.py` reference `OrganismBrain` / `manifest.json` / `save_essential_state` / `_save_manifest` in the entire backend. No second instance of `OrganismBrain` exists.
2. **All 3 save callsites are on `LiveEngine`**: `force_save_brain()`, `_save_brain()` full-save path, `_save_brain()` gated essential-save fallback. Background trainer uses pickle IPC only — does not touch disk.
3. **Code divergence**: `save_essential_state()` reads `manifest["total_runs"]` from DISK before incrementing; `_save_manifest()` reads from `self._manifest` in memory. They track `total_runs` independently. The 01:27 UTC post-deploy force-save wrote `total_runs=105` via `self._manifest`; the 02:58 UTC wipe wrote `total_runs=109` via disk — 4 saves apart — while `self._manifest` on the live engine stayed at 105.
4. **Patch E's guard is only in `save()`** (lines 267–300 of pre-Patch-F-lite `brain_persistence.py`). `save_essential_state()` had no guard. This is the proven gap Patch F-lite closes.

The **trigger** (what caller passed a fresh learner/signal_gen to `save_essential_state`) remains unproven. Patch F-lite blocks the write regardless of trigger; the full Patch F (with stack-trace instrumentation) is required to identify the caller on the next recurrence.

## Files changed

| File | Lines added | Lines removed |
|---|---:|---:|
| `backend/organism/brain_persistence.py` | 44 | 0 |
| `tests/test_apr9_patch_f_lite_essential_state_guard.py` | 204 | 0 (new file) |

## Exact change in `brain_persistence.py`

Added a defensive guard at the top of `save_essential_state()`, immediately after `self.brain_dir.mkdir(...)` and before the main `try:` block. The guard:

1. **Resolves existing state** from the best available source:
   - If `self._manifest` is populated (normal case for a loaded `OrganismBrain`) → use it.
   - Else if `manifest.json` exists on disk → read it via `_read_json` (fallback).
   - Else → `None` (no guard, safe first-save path).

2. **Blocks the write** if both conditions hold:
   - `existing_trades > 0 OR existing_trained == True` (the on-disk brain was previously trained), and
   - `incoming_trades == 0 AND incoming_trained == False` (the caller passed a fresh learner/signal_gen).

3. **Logs `ERROR` level** `"BRAIN SAVE BLOCKED (save_essential_state): ..."` with the existing vs. incoming summary. Returns early without writing any file.

4. **Does NOT have a force flag**. Unlike `save()`, `save_essential_state()` is protected unconditionally. Rationale: the essential-save path is called ONLY from `live_engine._save_brain()` gated fallback, and the live engine's learner/signal_gen are never intentionally fresh during a normal tick. The force-save admin path (`POST /api/v1/organism/save?force=true`) routes through `save()`, not `save_essential_state()`, so the force flag isn't needed here.

5. **Does NOT alter `save()` behavior** in any way. Patch E's guard in `save()` is unchanged.

6. **Does NOT change** helper consolidation, break-glass semantics, read-back invariants, suspicious-write instrumentation, or `LiveEngine` forensic guards. Those remain queued for full Patch F.

## Tests — all green (151/151)

### New F-lite tests — `tests/test_apr9_patch_f_lite_essential_state_guard.py` (3 tests)

1. `test_essential_state_guard_blocks_trained_overwrite` — seeds a trained brain via `save(force=True)`, calls `save_essential_state` with fresh mocks, asserts manifest unchanged and `BRAIN SAVE BLOCKED (save_essential_state)` log fires. **PASS**
2. `test_essential_state_guard_allows_healthy_save` — seeds a trained brain, calls `save_essential_state` with a healthy live learner (gen=28, trades=200, pnl=-480) and trained signal_gen, asserts the manifest updates to reflect the new live state. **PASS**
3. `test_essential_state_guard_reads_disk_when_memory_empty` — creates a trained brain, then instantiates a FRESH `OrganismBrain` at the same dir (so `self._manifest` is empty), calls `save_essential_state` with fresh mocks, asserts the guard still fires via the on-disk fallback and the manifest is preserved. **PASS**

### Prior patch tests — all green

| Test file | Tests | Result |
|---|---:|---|
| `test_apr8_patch_e_trained_state_guard.py` (Patch E) | 8 | **8/8 PASS** |
| `test_apr8_patch_b_manifest_sync.py` (Patch B) | 8 | **8/8 PASS** |
| `test_apr8_patch_a_force_save.py` (Patch A) | 13 | **13/13 PASS** |
| `test_apr7_p0_p1_fixes.py` (Apr-7 P0/P1) | 12 | **12/12 PASS** |
| `test_apr9_patch_f_lite_essential_state_guard.py` (F-lite) | 3 | **3/3 PASS** |
| **Total patch tests** | **44** | **44/44 PASS** |

### Organism regression subset — all green

```
tests/test_organism_live_engine.py
tests/test_organism_engine_scenarios.py
tests/test_multi_tick_state.py
tests/test_safety_invariants.py
tests/test_self_evolution.py
→ 107 passed, 2 pre-existing numpy warnings (unrelated), 60.49s
```

**Grand total**: 151/151 tests pass. Zero regressions.

## What this CLOSES structurally

- **The proven save_essential_state gap**: any call to `BrainPersistence.save_essential_state()` with `existing_trained AND incoming_fresh` now logs ERROR and returns early without writing `manifest.json` or any of the runtime-truth files.
- **Fresh-instance disk fallback**: a new `OrganismBrain()` pointing at an existing trained brain dir cannot silently wipe the manifest via `save_essential_state`, even before `load()` has been called.
- **Covers both wipe incidents' fingerprint**: the `existing_trades>0, existing_trained=true, incoming_trades=0, incoming_trained=false` pattern is now blocked on both save paths (Patch E covers `save()`, F-lite covers `save_essential_state()`).

## What remains for full Patch F

The full structural closure work queued for a dedicated maintenance window (originally scoped as 4 slices F1-F4):

1. **Helper consolidation** — route both save paths through a single `_write_manifest_guarded()` method so total_runs sourcing is unified and the guard logic isn't duplicated.
2. **Break-glass reset semantics** — require `force=True AND allow_reset=True AND reset_reason=...` (not just `force=True`) to permit an intentional trained→fresh overwrite. F-lite still allows `save(force=True)` to bypass the save() guard, which is a smaller surface than save_essential_state's unconditional block but not fully locked down.
3. **Suspicious-write instrumentation** — log WARNING with `traceback.format_stack()`, pid, thread, and existing/incoming summary on any regressive attempt, even one that the break-glass path then allows. This is the **missing diagnostic** that would identify the unknown caller on the next wipe attempt. F-lite blocks the write but does not capture the caller's stack trace, so if the wipe recurs we'll see only `BRAIN SAVE BLOCKED (save_essential_state)` without knowing who called.
4. **Read-back invariant check** — after every manifest write, read back from disk and assert consistency with `learner.state` / `signal_gen`. CRITICAL log and False return on mismatch.
5. **LiveEngine forensic guard** — capture stable `id()` fingerprints of `self.signal_gen` and `self.learner` at `LiveEngine.__init__`, log CRITICAL in `_save_brain()` if the identity changes unexpectedly.
6. **Bypass audit** — comprehensive grep + reroute/justify every direct `_write_json(... MANIFEST_FILE ...)` callsite in the backend.
7. **Extend tests** from the 3 tactical F-lite tests to the 12 full-coverage tests in the original Patch F spec.

None of these are session-blocking. F-lite closes the specific gap proven by the recurrence; full Patch F upgrades that into a structural guarantee.

## Deploy risk

**Very low.** The patch adds 44 lines of pure defensive code at the top of one method. Behavior is:
- Normal healthy save → unchanged (guard does not fire)
- Trained→trained save → unchanged (guard does not fire)
- Trained→fresh save → previously silent wipe, now blocked with ERROR log (explicit fail-closed)

No strategy logic, thresholds, sizing, exit rules, walk-forward math, scheduler behavior, or trading decisions touched.

## Rollback steps

```bash
git revert 3528162
# or
git reset --hard 62256d7  # DESTRUCTIVE — only if 3528162 is the tip and no further work has landed
```

Rollback restores Patch E as the top commit. `save_essential_state` returns to its pre-F-lite state (no guard). The recurring wipe failure mode returns until full Patch F ships.

## Git state

**Before**:
```
HEAD: 62256d7  fix(brain): refuse to overwrite trained manifest with untrained state
worktree: clean in backend/organism/ and tests/
```

**After**:
```
HEAD: 3528162  fix(brain): extend trained-state overwrite guard to save_essential_state [F-lite]
worktree: clean in backend/organism/ and tests/
```

Full commit chain on main:
```
3528162 fix(brain): extend trained-state overwrite guard to save_essential_state [F-lite]
62256d7 fix(brain): refuse to overwrite trained manifest with untrained state
c5fb0ed fix(scripts): default standalone scripts to organism_brain_sandbox/
be2eee8 feat(brain): force-save admin route for ML artifact recovery
50b2513 fix(brain): save manifest from live learner.state and signal_gen
93593a2 fix(brain): walk_forward_gate reads authoritative learner.state.best_sharpe
2018999 fix(H5): preserve pyramid level on broker sync collapse
```

## Does this close the proven gap?

**YES, for the specific proven path.** The wipe writer provably uses `save_essential_state()` (per the `total_runs` divergence evidence between disk and memory). F-lite's guard now blocks that exact path. If the wipe recurs after F-lite is deployed, one of three things is true:

1. **The guard blocked it** → ERROR log `BRAIN SAVE BLOCKED (save_essential_state): ...` appears in the application log. This is the expected outcome and proves F-lite works.
2. **The writer uses a different path** → either `save()` with a bypass we haven't identified, or a direct `_write_json(manifest.json, ...)` call. In that case, full Patch F's bypass audit and forensic guard would be required to close it.
3. **The writer uses `save(force=True)` with fresh learner/signal_gen** → Patch E's `not force` clause lets this through. Full Patch F's break-glass tightening would close this. F-lite does NOT address this gap.

Patch F-lite is **sufficient for the observed failure mode** and **insufficient for hypothetical variant failures**. This is an acceptable trade-off for a tactical commit.

## Deploy recommendation

Do NOT deploy tonight. The running container at `62256d7` is healthy, the disk state is fully recovered via the 03:53 UTC force-save, and F-lite would require a rebuild + restart which this task explicitly forbids. Deploy F-lite bundled with full Patch F in the next post-market maintenance window (2026-04-09 20:00 UTC onwards).

If the wipe recurs before that window, the container's in-memory state remains authoritative and a manual force-save via `POST /api/v1/organism/save?force=true` restores disk. No urgency tonight.
