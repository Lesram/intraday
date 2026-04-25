# Apr-7 P0/P1 Fix Report

## Verdict
Narrow correctness + observability fixes for three bugs observed on 2026-04-07.
All three root causes were proven from source reading and patched.
Deploy-safe: no strategy logic, thresholds, or state contracts changed.

## Files Changed
- `/Users/marselkei/VS/intra/backend/organism/live_engine.py`
- `/Users/marselkei/VS/intra/backend/organism/brain_persistence.py`
- `/Users/marselkei/VS/intra/tests/test_apr7_p0_p1_fixes.py` (new)

## P0.1 — LiveTickResult exit counters drifted from reality
**Root cause (proven):** Every exit submission path in `_live_tick_inner`
(safety-net-no-features at L~1484, safety-net-no-exit-levels at L~1564,
normal exit at L~1636, EOD flatten at L~1680) bumped a local
`exits_submitted` variable but **never** `result.orders_submitted`. Only
entry paths incremented `result.orders_submitted`. Result: a tick that
only processed exits always logged `orders=0` in the scheduler line 341
"Organism tick: regime=... orders=... exits=..." output.

**Fix:** Added `result.orders_submitted += 1` at all four exit submission
sites, alongside the existing `exits_submitted += 1`.

## P0.2 — Watchdog truth sources (C1 no-trade, C4 brain-save)
**Root cause (proven):**
1. `_update_watchdog_state` read `result.orders_submitted` — which was
   the broken counter from P0.1 — so C1 thought the engine was idle
   whenever it was only exiting positions.
2. `_watchdog_last_order_tick` and `_watchdog_last_brain_save_tick` were
   initialized to `0` in `__init__` and never seeded at `initialize()`.
   A fresh engine boot with `tick_count = 5000` showed "last save at
   tick 0" in C4 log output — matching the Apr 7 evidence exactly.
3. There was no monotonic authoritative counter the watchdog could
   anchor on independent of the per-tick result object.

**Fix:**
- Added `self._total_orders_submitted` and `self._total_exits_submitted`
  monotonic counters, bumped inside `_submit_entry_order` and
  `_submit_exit_order` right after `order_service.submit_symbol_order`
  returns (past the LONG_ONLY guard for exits).
- `_update_watchdog_state` now advances `_watchdog_last_order_tick`
  whenever `_total_orders_submitted` grows, with a belt-and-suspenders
  fallback to the result field.
- `initialize()` seeds `_watchdog_last_order_tick`,
  `_watchdog_last_brain_save_tick`, and `_watchdog_last_total_orders`
  to the current engine state at the moment of boot.
- The existing `_save_brain()` watchdog updates at L~4287 and L~4316
  were left unchanged (they already work); the seed in `initialize()`
  closes the "last save at tick 0" noise window.

## P1 — walk_forward_gate best_sharpe collapse (PROVEN + PATCHED)
**Root cause (proven from source):** In
`backend/organism/brain_persistence.py` `walk_forward_gate` (previously
lines ~1222–1225):

```python
decayed = best_sharpe * 0.95
self._manifest["best_sharpe"] = decayed
```

This mutation ran on EVERY gated save attempt. `_save_brain` is invoked
every 20 ticks (~3.3 min). On a day with persistently negative current
Sharpe, that fires ~100–120 times per session. `0.95^120 ≈ 0.0021`, so a
morning `best_sharpe = 2.776` collapses to ~0.006 by end of session —
which matches the Apr 7 evening value of 0.011 almost exactly (the
mismatch is explained by fewer than 120 gated-save attempts, e.g.
~100 gives 2.776 * 0.95^100 ≈ 0.017).

The decay was intended to prevent a lucky historical session from
permanently blocking saves, but the cadence was keyed to tick frequency
rather than calendar days / sessions.

**Note on persistence:** `save_essential_state` re-reads the manifest
from disk before writing (it does not dump `self._manifest` directly),
so the decay was in-memory only and did NOT ratchet through restart.
But within a running session it still dominated the gate ratio all day.

**Fix (narrow):** Rate-limit the decay to at most once per calendar
day (UTC) via `self._last_sharpe_decay_date`. Behavior preserved on
first gated regression per day; subsequent gated regressions log
without mutating `self._manifest["best_sharpe"]`.

## Diff summary
- `live_engine.py`: +54 lines, −3 lines. Added monotonic counters,
  seeded watchdog baselines on `initialize()`, wired C1 watchdog to the
  authoritative counter, and added `result.orders_submitted += 1` at
  four exit submit call-sites. No control flow changed, no gates
  relaxed.
- `brain_persistence.py`: +23 lines, −9 lines. Added
  `_last_sharpe_decay_date` attribute and wrapped the decay block in a
  once-per-UTC-day guard with a non-decay warning log branch.

## Tests — new file `tests/test_apr7_p0_p1_fixes.py`
All 9 tests pass (1.15s):
- `test_walk_forward_gate_decays_best_sharpe_at_most_once_per_day`
- `test_walk_forward_gate_passes_when_current_beats_baseline`
- `test_walk_forward_gate_no_baseline_always_saves`
- `test_live_tick_result_exit_callsites_bump_orders_submitted`
- `test_update_watchdog_reads_authoritative_total_counter`
- `test_update_watchdog_c1_stays_quiet_while_orders_flow`
- `test_update_watchdog_c1_fires_critical_when_truly_idle`
- `test_submit_entry_order_counters_increment`
- `test_save_essential_state_does_not_reset_watchdog_tick`

## Regression tests — focused subset
Ran on affected surfaces:
- `tests/test_organism_live_engine.py` — PASS
- `tests/test_organism_engine_scenarios.py` — PASS (30)
- `tests/test_multi_tick_state.py` — PASS
- `tests/test_safety_invariants.py` — PASS
- `tests/test_self_evolution.py` — PASS
- Combined organism subset: **77 passed, 0 failed**
- `tests/test_replay_simulator.py` — 1 failure
  (`test_replay_no_throttle_blocking`), confirmed **pre-existing** by
  running the same test against `git stash`ed baseline on the main HEAD
  commit `2018999`. Not caused by this change.

## Deploy risk
- **Low.** Changes are additive counters + one guard condition on a
  pre-existing decay mutation. No strategy parameters, entry gates, exit
  rules, sizing, Kelly, or ML boundaries touched. No historical brain
  files mutated.
- Monotonic counters are simple int fields — no thread-safety issue
  (GIL-protected, bumped in the same event loop as the scheduler).
- The P1 guard preserves the original decay path on day 1 of any bad
  regression; it only prevents the intra-day compounding.

## Rollback
Single `git revert` of the commit that introduces these three files,
or file-by-file:
- `git checkout 2018999 -- backend/organism/live_engine.py`
- `git checkout 2018999 -- backend/organism/brain_persistence.py`
- `rm tests/test_apr7_p0_p1_fixes.py`

## Verdict: safe to deploy before 2026-04-08 13:30 UTC open?
**YES.** All three fixes are narrow, proven, covered by focused tests,
and do not touch any trading-invariant surface. Required organism test
subset is green. The single replay failure is pre-existing.
