# Patch F1/4 — _write_manifest_guarded helper + save() routing

**Commit**: `eaa4b2f`
**Parent**: `3528162` (F-lite)
**Status**: COMMITTED, not deployed.

## Files changed

| File | +/- |
|---|---|
| `backend/organism/brain_persistence.py` | +204 / -44 |
| `tests/test_apr10_patch_f1_guarded_helper.py` | +265 (new) |

## What F1 introduces

1. **`_check_trained_overwrite_guard(target, signal_gen, learner, force) -> (bool, str)`** — shared pure-predicate check. Resolves existing state from self._manifest OR on-disk manifest.json OR empty default. Returns (should_block, reason). Caller decides action.

2. **`_write_manifest_guarded(target, signal_gen, learner, *, caller, force, allow_reset, reset_reason) -> bool`** — unified manifest write path. Computes total_runs from one source (in-memory > on-disk > 0). Calls `_apply_live_manifest_fields`. Applies defense-in-depth guard. Writes and syncs self._manifest. Returns True/False.

3. **Refactored save()'s inline Patch E guard** to use the shared check. Lock-release semantics preserved exactly (lock.release() stays in save(), not in the helper).

4. **_save_manifest() delegates** to the helper with force pass-through.

## What F1 does NOT change

- save_essential_state() — untouched (F2's scope)
- _apply_live_manifest_fields — unchanged (Patch B)
- Lock acquisition/release flow in save() — preserved
- Any strategy/trading behavior — none

## Tests — 158/158 passed

- 7 new F1 tests (helper write, guard block, delegation, early guard, total_runs, force pass-through, disk fallback)
- 8 Patch E regression — PASS
- 3 F-lite regression — PASS
- 33 Patch A/B/P0/P1 — PASS
- 107 organism regression subset — PASS

## Next: F2

Route save_essential_state() through _write_manifest_guarded. Remove the F-lite inline guard (relocated into the helper). Unify total_runs sourcing so both save paths use identical logic.
