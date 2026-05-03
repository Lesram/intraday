# Track WW v10 — Multi-Day Operational Soak

**Branch**: `rc-1.5-curated` @ `c048103` (working tree)
**Date run**: 2026-05-03 (Saturday, paper market closed)
**Scratch**: `/tmp/ww_soak_brain/` (copy of `organism_brain/`, prod read-only)
**Runner**: `/tmp/ww_soak_run.py`, `./venv/bin/python`
**Raw results**: `/tmp/ww_soak_results.json`

This track exercises the platform's persistence layer through repeated
restarts, hunting for state-loss bugs. V4 H-* findings ("brain manifest
gets reset on restart") motivated the lens; previous waves only tested
single-restart.

---

## Method recap

10 sub-tests, executed sequentially against scratch brain copy:

| # | Test                                   | Pass criterion                                         |
|---|----------------------------------------|--------------------------------------------------------|
| 1 | 5x sequential restart soak             | Manifest fields invariant across cycles                |
| 2 | Backup rotation                        | `backups/` keeps ≤ MAX_BACKUPS=5; oldest pruned        |
| 3 | Concurrent-restart lock                | Exactly one of two subprocesses acquires the lock      |
| 4 | SIGTERM atomicity                      | No `.tmp_save` / `.brain_old` stranded; manifest loadable |
| 5 | Pending-entry rehydration              | `pending_entry_order_ids` round-trips through extra_counters |
| 6 | Symbol-banned + session rollover       | `symbol_banned` round-trips; `daily_session_date` preserved |
| 7 | ML state continuity (5x)               | `is_trained`, `feature_count`, calibration map invariant |
| 8 | Evolution + fitness state              | `evolved_params.json` keys + count invariant           |
| 9 | best_sharpe `-inf` round-trip          | Saved as `null`, restored as `-inf`                    |
| 10 | (Test 1 also covers 5-cycle delta)    | total_trades increments by exactly +1 per cycle        |

---

## Results

### 1. Five-cycle restart invariant table

Initial snapshot (HEAD prod brain, copied to scratch):

| Field                | Cycle 0 | Cycle 1 | Cycle 2 | Cycle 3 | Cycle 4 | Cycle 5 |
|----------------------|---------|---------|---------|---------|---------|---------|
| generation           | 168     | 168     | 168     | 168     | 168     | 168     |
| total_trades         | 498     | 499     | 500     | 501     | 502     | 503     |
| cumulative_pnl       | -634.92 | -634.92 | -634.92 | -634.92 | -634.92 | -634.92 |
| best_sharpe          | 3.4363  | 3.4363  | 3.4363  | 3.4363  | 3.4363  | 3.4363  |
| ml_is_trained        | true    | true    | true    | true    | true    | true    |
| feature_count        | 79      | 79      | 79      | 79      | 79      | 79      |
| total_runs           | 1938    | 1939    | 1940    | 1941    | 1942    | 1943    |
| brain_format_version | 2       | 2       | 2       | 2       | 2       | 2       |

**Outcome: PASS.** Every protected field (generation, cumulative_pnl,
best_sharpe, ml_is_trained, feature_count, brain_format_version) stayed
exactly invariant across 5 cycles. `total_trades` increased by exactly
+1/cycle (the deliberate trivial mutation). `total_runs` increased by
+1/cycle as expected. No field reset to `0`, `NaN`, or default.

### 2. Backup rotation

Two sub-tests:

- **Distinct-second loop** (8 saves, 1.05s spacing): grew `backups/`
  monotonically until 5; further saves correctly pruned the oldest. Final
  count = 5. **Rotation works.**
- **Sub-second loop** (5 saves, no sleep): `final_count = 1`. All 5
  backups collapsed onto the same directory because `_create_backup` mints
  the path as `f"brain_gen{gen}_{YYYYMMDD_HHMMSS}"` and uses
  `mkdir(exist_ok=True)`. Same-second + same-gen ⇒ name collision ⇒
  silent overwrite of the prior snapshot. **No exception, no log warning.**

This is benign in steady-state (saves are minutes apart) but matters for:
- a tight-loop crash-recovery scenario (e.g. startup retry storm)
- the `force_save_brain` admin path called twice in succession
- automated tests / soaks

### 3. Concurrent-restart lock

```
p1: ACQUIRED
p2: BLOCKED: Brain lock already held: /tmp/ww_soak_brain/.brain.lock
```

Exactly one acquired (`fcntl.flock(EX|NB)`); the other failed fast with
`RuntimeError`. **PASS.**

### 4. SIGTERM atomicity (3 cycles)

| Cycle | `.tmp_save` stranded | `.brain_old` stranded | Manifest loadable | Exit code |
|-------|----------------------|------------------------|-------------------|-----------|
| 1     | False                | False                  | True              | -15 (SIGTERM) |
| 2     | False                | False                  | True              | -15 |
| 3     | False                | False                  | True              | -15 |

The harness loads the brain (no save in flight) before SIGTERM, so this
cycle confirms the *idle* state is clean. The save-in-flight scenario is
handled by `save()`'s try/except/finally that rmtree's the tmp dir; not
exercised here because this harness mocks rather than drives a live save.
**PASS for the tested scenario.**

### 5. Pending-entry / pending-exit / exit-cooldown rehydration

Injected `pending_entry_order_ids = {"AAPL_TEST": "abc-123-test"}`,
`pending_exit = {"MSFT_TEST": 9999}`, `exit_cooldown = {"NVDA_TEST": 9999}`,
`pending_entry = {"TSLA_TEST": 9999}` directly into
`extra_counters.json`. Re-loaded brain, confirmed every key is present in
`brain.extra_counters`. **PASS.** (live_engine's
`_restore_organism_state` then resets the tick clocks to `_tick_count`
so cooldown windows expire correctly post-restart — that logic was
audited at lines 1161-1212 and is sound.)

### 6. Same-day vs date-roll for `symbol_banned`

Same-day case: stamped `daily_session_date = today`,
`symbol_banned = ["AAPL_BANTEST", "MSFT_BANTEST"]`. Brain returned both
verbatim; live_engine's date-equality check would rehydrate them.

Stale-day case: stamped `daily_session_date = yesterday`. Brain still
returned the bans (raw storage) — the date-roll *clear* is implemented
in `live_engine._restore_organism_state` (lines 1186-1211), not in
`brain_persistence`. Reviewed that code; it is correct.

**PASS.** Storage round-trips exactly; consumer-side date-equality logic
guards against stale bans.

### 7. ML state continuity (5x)

5 reload cycles, each verifying:
- `is_trained = True` (initial)
- `feature_count = 79` (initial)
- `calibration_map` first element preserved

All 5 cycles matched. `is_trained_invariant_held = True`,
`feature_count_invariant_held = True`. **PASS.**

### 8. Evolution + fitness state

`evolved_params.json` had 39 keys at cycle 0 (initial). Across 5 cycles,
`n_keys = 39` and the full key set matched exactly. **PASS.**

Note: `save_essential_state` is *deliberately* gated on `evolved_params`
— it does NOT overwrite the file. The full `save()` is the only path
that writes `evolved_params.json`. This is a feature, not a bug.

### 9. best_sharpe `-inf` round-trip

Forced `learning_state.json["best_sharpe"] = null`. Reload returned
`raw = None`; `apply_to_learner` correctly maps `None → -inf`
(brain_persistence.py L625). **PASS.**

---

## Findings

### F-WW-1 (HIGH): Production brain has zero on-disk backups; PP-2 fallback safety net is empty

**Path**: `backend/organism/brain_persistence.py`, `_create_backup` L1993, called only from `save()` L436. `save_essential_state` does NOT call `_create_backup`.

**Path**: `backend/organism/live_engine.py::_save_brain` L6291-6420 routes through `walk_forward_gate` first; on regression/insufficient-trade-window the path drops to `save_essential_state` (L6395), which skips the backup mint.

**Observed**: Live container `intra-api-1`, host `organism_brain/`, paper compose mount — all show **no `backups/` directory** despite manifest reporting 1938 total runs and ML being trained. `find /app/organism_brain -maxdepth 2 -type d` returns only the brain root.

**Why it matters**: V9 PP-2 / Wave-41 added a corrupt-HEAD-load fallback in `OrganismBrain.load()` (L242-271): on `_load_manifest` exception, walk `backups/` newest-first, restore the first usable snapshot, otherwise fall through to "starting fresh" (which is then re-blocked by the trained-overwrite guard, but that just means *no brain loads*, not graceful degradation). With zero backups, PP-2's fallback is a no-op. The "single-OOM-kill bomb" the comment at L243-247 was meant to prevent is still loaded.

**Likely root cause**: walk-forward gate has been keeping `_save_brain` on the essential-save path for an extended window (the gate fires on Sharpe regression on the last 100 strategy trades; with cumulative PnL = -$634.92 and small recent samples, the gate is probably blocking the full save path most of the time). Each blocked save calls `save_essential_state`, which writes runtime truth but **does not snapshot to `backups/`**.

**Suggested fix**: snapshot to `backups/` from `save_essential_state` as well — at minimum on a coarser cadence (every Nth essential save, or once per session). Alternatively, mint a backup unconditionally on engine shutdown.

### F-WW-2 (MEDIUM): Backup directory naming has 1-second resolution; same-second saves silently collapse

**Path**: `brain_persistence.py::_create_backup` L1995-1997: `ts = datetime.now().strftime("%Y%m%d_%H%M%S")`, `backup_name = f"brain_gen{gen}_{ts}"`, `backup_path.mkdir(parents=True, exist_ok=True)`.

**Observed**: 5 successive `_create_backup()` calls within a single second produced a single backup directory (others collapsed onto the same name due to `exist_ok=True`). No exception or log warning was emitted. Verified in test 2 fast-loop: `final_count = 1` after 5 saves.

**Why it matters**:
- A startup retry storm (e.g. after a crash, the supervisor restarts the engine 3-4× rapidly while still in the same second) ends with one backup, not 4.
- The admin `force_save_brain` path can be called twice in succession from the UI — the second call overwrites the first backup.
- Concurrent saves from different processes or threads on the same brain are blocked by the lock, so this isn't a race per se — it's a same-process rapid-call hazard.

**Suggested fix**: append microseconds (`%Y%m%d_%H%M%S_%f`) to the timestamp, or include a monotonic counter, or fall through to `mkdir(exist_ok=False)` and retry with `_n` suffix on collision.

### F-WW-3 (LOW): `save_essential_state` skips evolved_params persistence by design — verified, but document the implication

**Path**: `brain_persistence.py::save_essential_state` L780-870. The docstring at L797-801 ("NOT written … evolved_params.json") is explicit: only the full `save()` writes evolved_params, intentionally gated on the walk-forward promotion check.

**Observed**: 5 essential-save cycles left `evolved_params.json` unchanged (39 keys, same set). This is correct behaviour per the design.

**Edge case**: when full `save()` is gated for an extended window (see F-WW-1), the `evolved_params.json` on disk drifts further behind the in-memory `self.evolved_params`. On a hard restart, the engine loads stale evolved params. This is a feature (promotion gating) but the lag should be observable — emit a metric or log for "ticks since last full save".

### F-WW-4 (INFORMATIONAL): All other invariants hold

5x restart soak: every protected manifest field invariant. ML state, evolution state, pending-entry rehydration, symbol-banned round-trip, best_sharpe `-inf` handling, concurrent-lock semantics, SIGTERM cleanup — all PASS. The H1-H7 hardening from prior waves and the V9 PP-2 backup-fallback design are doing their job at the algorithm level. The gap is at the **operational / artifact** level (F-WW-1, F-WW-2).

---

## TL;DR

The brain layer's *load/save round-trip invariants* survive the 5x restart soak cleanly: every protected manifest field (generation, cumulative_pnl, best_sharpe, ml_is_trained, feature_count) stays exactly invariant, ML calibration round-trips, pending-entry / exit-cooldown / symbol-banned all rehydrate, the lock prevents concurrent writers, and SIGTERM does not strand `.tmp_save` artifacts. The two real findings are operational: production has **zero on-disk backups** because the walk-forward gate keeps `_save_brain` on the essential-save path, which by design skips `_create_backup` — leaving V9's PP-2 corrupt-HEAD-load fallback with nothing to restore from (F-WW-1, HIGH); and the backup-directory naming uses 1-second resolution with `mkdir(exist_ok=True)`, so same-second saves silently collapse onto a single snapshot (F-WW-2, MEDIUM). Recommend: emit at least one backup per session from the essential-save path (or on shutdown), and bump backup-name resolution to microseconds.
