# APR-8 Patch B Report — Manifest Sync Fix

## Verdict
COMMITTED — `50b2513` on branch `main` (local, not pushed). Base was `93593a2` (Patch C).

## Root Cause
`save_essential_state()` only updated `total_trades` and `cumulative_pnl` in
`manifest.json`, inheriting all other fields (`generation`, `best_sharpe`,
`ml_is_trained`, `feature_count`) from whatever `self._manifest` happened to
contain at the time. When the in-memory `_manifest` dict held stale or wiped
values, the on-disk manifest diverged from `learning_state.json` (which
*was* written from live `learner.state`). This is exactly the recovery
incident observed 2026-04-08 at 02:08 UTC: `learning_state.json` healthy
(gen=18, total_trades=195, best_sharpe=2.8956) while `manifest.json` was
zeroed out (gen=0, best_sharpe=0, ml_is_trained=false, feature_count=0).

`_save_manifest()` (the full-save path) was partially OK — it did read
`learner.state.generation`, `total_trades`, `cumulative_pnl`, `best_sharpe`
— but still took `total_runs` and the `!= -np.inf` guard wasn't parity
with the Patch C `np.isfinite` contract, and it never updated `self._manifest`
in-place, so any subsequent call to `save_essential_state` in the same
process would fall back to pre-save values.

## Files Changed
- `backend/organism/brain_persistence.py`
- `tests/test_apr8_patch_b_manifest_sync.py` (new)

## Diff Summary
1. New helper `OrganismBrain._apply_live_manifest_fields(manifest, signal_gen, learner)`:
   - Writes `generation`, `total_trades`, `cumulative_pnl` from `learner.state`.
   - Writes `best_sharpe` from `learner.state.best_sharpe` guarded by `np.isfinite`
     (matches Patch C contract); falls back to `self._manifest["best_sharpe"]`.
   - Writes `ml_is_trained` from `signal_gen._is_trained`, `feature_count` from
     `len(signal_gen._feature_cols)`.
   - Fallback-safe when either is None: falls back to `self._manifest` values.
2. `_save_manifest()` rewritten to use the helper and then update
   `self._manifest = dict(manifest)` after writing to disk.
3. `save_essential_state()`: replaced the narrow 4-line block (only
   total_trades + cumulative_pnl) with a call to `_apply_live_manifest_fields`
   followed by the same in-memory `self._manifest` sync.

No other behavior changed. Patch C gate untouched. `_last_sharpe_decay_date`
still absent. Trade history, ML binaries, evolved params, governance/regime
state writes unchanged.

## Tests
New file: `tests/test_apr8_patch_b_manifest_sync.py` — 8 tests covering:
1. essential-save writes learner.state fields (gen=18, trades=195, pnl=-656.67, sharpe=2.8956)
2. essential-save writes signal_gen fields (ml_is_trained=True, feature_count=79)
3. full save() path writes the same authoritative values
4. fallback helper path when learner=None (unit tests helper directly — save
   helpers like `_save_learning_state` themselves require non-None learner,
   which matches live callsite reality; `_apply_live_manifest_fields` is the
   unit responsible for fallback)
5. fallback helper path when signal_gen=None
6. Patch C compat: finite best_sharpe written
7. Patch C compat: `-inf` best_sharpe falls back (not `-inf`, not silent 0 when
   fallback is present)
8. Regression for recovery incident: stale `_manifest` overridden by live state

### Results
```
tests/test_apr8_patch_b_manifest_sync.py   8 passed
tests/test_apr7_p0_p1_fixes.py            12 passed  (Patch C regression)
--------------------------------------------------------
Total                                     20 passed

Organism regression subset:
tests/test_organism_live_engine.py
tests/test_organism_engine_scenarios.py
tests/test_multi_tick_state.py
tests/test_safety_invariants.py
tests/test_self_evolution.py             107 passed  (2 numpy div-by-0 warnings, pre-existing)
```

Zero failures, zero regressions.

## Commit
- SHA: `50b2513`
- Parent: `93593a2` (Patch C)
- Files: `backend/organism/brain_persistence.py`, `tests/test_apr8_patch_b_manifest_sync.py`
- Not pushed.

## Is Manifest Sync Fixed?
Yes. Evidence:
- Both save paths call the same `_apply_live_manifest_fields` helper.
- Helper reads exclusively from `learner.state` and `signal_gen` for the
  six previously-drift-prone fields.
- `self._manifest` is overwritten post-write so in-process drift cannot
  recur across back-to-back saves.
- Regression test `test_stale_manifest_overridden_by_live_state` reproduces
  the incident (zeroed `_manifest` + healthy learner) and asserts the written
  manifest matches the live objects.

## Worktree
Clean for Patch B concerns. After commit, worktree has only pre-existing
unrelated dirt (`monitoring/memory_monitoring.json` modification and many
untracked docs/artifacts predating this task). No unrelated edits were
included in the Patch B commit.

## Remaining Pre-Deploy Work
With Patch B committed, Patch A is now the only remaining pre-deploy task.
No deploy, rebuild, or restart was performed by this task.

## Safety Note
Forensic snapshot preserved at
`/Users/marselkei/VS/intra/organism_brain_forensic_snapshot_20260408T065456Z/`
— untouched.
