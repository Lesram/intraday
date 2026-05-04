# Patch F2/4 — save_essential_state routed through unified helper

**Commit**: `3a694ee`
**Parent**: `eaa4b2f` (F1)
**Status**: COMMITTED, not deployed.

## Files changed

| File | +/- |
|---|---|
| `backend/organism/brain_persistence.py` | +77 / -60 (net -17 lines: duplication removed) |
| `tests/test_apr10_patch_f2_unified_essential_save.py` | +218 (new) |

## What F2 does

1. `save_essential_state()` now delegates manifest writes to `_write_manifest_guarded(caller="save_essential_state", force=False)`.
2. F-lite's inline guard (44 lines) REMOVED — the unified helper provides the same protection via `_check_trained_overwrite_guard`.
3. total_runs divergence CLOSED — both save paths now compute total_runs via the helper's uniform source (in-memory > on-disk > 0).
4. Runtime-truth files (trade_history, learning_state, etc.) are still written before the manifest guard check — they're harmless without a matching manifest and are intentionally persisted regardless.

## What this closes structurally

- The Apr 8/9 wipe mechanism went through `save_essential_state` which read total_runs from DISK independently of `save()`'s in-memory path. The two counters drifted, making the wipe invisible to the in-memory guard. Now BOTH paths read from the same unified source via the helper.
- The F-lite inline guard is no longer duplicated code — it's the same `_check_trained_overwrite_guard` predicate used by both save paths.

## Tests — 162/162 passed

- 4 new F2 (total_runs consistency, guard block, fresh-instance both-paths, healthy save)
- 3 F-lite regression — PASS
- 7 F1 — PASS
- 8 Patch E — PASS
- 48 Patch A/B/P0/P1 — PASS
- 107 organism regression — PASS

## Next: F3

Break-glass reset semantics + suspicious-write stack-trace instrumentation + read-back invariant.
