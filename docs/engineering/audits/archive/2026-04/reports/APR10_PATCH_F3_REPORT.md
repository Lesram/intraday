# Patch F3/4 — Break-glass + suspicious-write instrumentation + read-back invariant

**Commit**: `9e7c9a9`
**Parent**: `3a694ee` (F2)
**Status**: COMMITTED, not deployed.

## Files changed

| File | +/- |
|---|---|
| `backend/organism/brain_persistence.py` | +214 / -10 |
| `tests/test_apr10_patch_f3_breakglass_instrumentation.py` | +275 (new) |
| `tests/test_apr10_patch_f1_guarded_helper.py` | +3 / -2 (break-glass triad update) |
| `tests/test_apr8_patch_e_trained_state_guard.py` | +3 (break-glass triad update) |

## What F3 adds

### Break-glass reset semantics
- `_check_trained_overwrite_guard` now requires the full triad: `force=True AND allow_reset=True AND reset_reason` (non-empty). `force=True` alone → BLOCKED.
- `save()` and `save_essential_state()` both support `allow_reset` / `reset_reason` pass-through.
- Logs `BRAIN BREAK-GLASS RESET (<caller>)` at WARNING when the triad permits an override.

### Suspicious-write instrumentation
- New `_log_suspicious_manifest_write()` helper captures: `traceback.format_stack()`, `os.getpid()`, `threading.current_thread().name`, existing/incoming manifest summary, `force`/`allow_reset`/`reset_reason` flags, caller name.
- Fires on EVERY regressive attempt — both in `save()`'s early guard and in `_write_manifest_guarded`'s defense-in-depth guard. Fires regardless of whether break-glass then allows.
- This is the **missing diagnostic** that identifies the unknown wipe caller on recurrence.

### Read-back invariant
- After every `_write_json(manifest.json)` inside `_write_manifest_guarded`, reads back from disk and compares: `generation`, `total_trades`, `best_sharpe` (finite contract), `ml_is_trained`, `feature_count`.
- On mismatch: logs `CRITICAL: BRAIN MANIFEST READ-BACK INVARIANT FAILED` and returns `False`.
- On exception during read-back: logs ERROR but does not fail the save (graceful degradation).

## Tests — 169/169 passed

- 7 new F3 tests (force-without-reset blocks, break-glass triad allows, suspicious-write fires with stack fields, read-back passes healthy, read-back fails on mismatch, normal save/essential-save succeed)
- 2 prior tests updated (F1 force-passes + Patch E force-bypasses → now use full triad)
- 62 total prior patch tests — PASS
- 107 organism regression — PASS

## What this enables

If the wipe recurs (through any of the three save paths), the container's application log will now contain:
- `SUSPICIOUS MANIFEST WRITE (<caller>): would regress trained brain. pid=... thread=... Stack:\n...`
- Either `BRAIN SAVE BLOCKED` (write prevented) or `BRAIN BREAK-GLASS RESET` (write allowed with triad)

The stack trace identifies the exact caller code path — no more guessing.

## Next: F4

LiveEngine forensic guard (stable id fingerprints + learner regression detection) + bypass audit of all `_write_json(MANIFEST_FILE)` callsites + final report.
