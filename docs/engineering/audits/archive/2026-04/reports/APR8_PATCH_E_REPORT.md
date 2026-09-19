# Apr-8 Patch E — Trained-state overwrite guard in BrainPersistence.save()

## Status: COMMITTED
- Commit SHA: `62256d7`
- Base: `c5fb0ed` (Patch D)

## Source state (pre-edit)
`BrainPersistence.save()` at `backend/organism/brain_persistence.py:231` already
had a `force` parameter (Patch A, audit-only). No defensive guard existed
between lock acquisition (line 262) and `_create_backup()` (line 269).

## Change
Inserted a defensive guard immediately after lock acquisition and before
backup. Guard fires only when ALL of the following hold:
- `self._manifest` non-empty
- `force` is False
- existing manifest shows `total_trades > 0` OR `ml_is_trained == True`
- incoming `learner.state.total_trades == 0` AND incoming `signal_gen._is_trained == False`

On block: logs ERROR, releases lock, returns. Does not raise.

## Tests
- New file `tests/test_apr8_patch_e_trained_state_guard.py` with 8 cases:
  1. Guard blocks zero-overwrite of trained manifest
  2. Guard allows save with incoming trained state
  3. Guard allows save when existing manifest is untrained
  4. `force=True` bypasses guard
  5. Existing trades>0 + incoming trained models -> allowed
  6. Existing ml_is_trained=True + incoming trades>0 -> allowed
  7. Empty `self._manifest` -> fresh save proceeds
  8. `learner=None` handled gracefully (blocks without crash)
- Patch A/B + P0/P1 regression: 41 passed.
- Organism regression subset (5 files): 107 passed in 60.84s.

## Files changed
- `backend/organism/brain_persistence.py`
- `tests/test_apr8_patch_e_trained_state_guard.py` (new)
