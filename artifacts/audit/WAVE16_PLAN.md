# Wave 16 — Final Closure Plan

**Scope:** 4 remaining open V4 items deferred from the wave 12-15 sweep.
**Branch:** `rc-1.5-curated` @ HEAD `3fe2a0d`.
**Risk profile:** higher than 12-15 because H-1 touches the order-tracking
state machine (highest blast radius surface in the platform). Sub-wave
ordering is **lowest-risk → highest-risk** so we can deploy/verify between each.

## Sub-wave inventory

### 16a — Z-R-4 (lowest risk: investigate pre-existing test failures)

**Findings:** `test_get_sector_known_symbol` and `test_missing_data_passes`
in the 185-test curated suite. Z confirmed pre-existing at `f65f9c3` (pre
wave-8). Decide: fix, mark `xfail` with reason, or skip.

**Risk:** none — test-only.

**Verification:** the two tests' verdict (pass / xfail / skipped) shows up
on the next pytest run.

### 16b — Z-R-3 (low risk: rewrite fragile string-grep tests)

**Findings:** `test_pending_entries_cleared_on_drawdown_kill` and
`test_pending_entry_without_order_id_still_cleared`. Both literally grep
for `"self._pending_entry.clear()"` in source — the source was refactored
post-wave-6 and the grep target moved. Behavior is preserved; the tests
are just too rigid.

**Fix:** rewrite as behavioral assertions — instantiate the engine,
trigger drawdown-kill, assert `_pending_entry == {}` and
`_pending_entry_order_ids == {}` post-call.

**Risk:** test-only. Worst case: tests still fail under the new shape and
need another iteration.

**Verification:** the 2 tests pass.

### 16c — H-2 (low risk: dead-code cleanup + comment, no behavior change)

**Finding:** `live_engine.py:3551` reads `filled_qty` from the sync submit
response (which never contains it). `live_engine.py:4734` reads
`avg_fill_price` from the sync exit response (same — never contains it).
The fall-through default and `_lookup_exit_fill_from_db` already
correctly handle the missing data, so this is dead-code that *looked*
live to the audit.

**Fix:** remove the dead-code reads; document the canonical path
(sync response → outbox → broker → WS `_on_trade_update` →
`orders.avg_fill_price` row → `_lookup_exit_fill_from_db`). Update the
`submit_symbol_order` docstring to explicitly state it returns no fill
data because the broker submission is asynchronous.

**Risk:** low. The dead branches were never executing (the audit's whole
point); removing them only changes optics. Verified by Track Z that
`avg_fill_price` is in the DB row populated by alpaca_stream.

**Verification:** brain coherent across recreate; `_lookup_exit_fill_from_db`
still functions on the next exit.

### 16d — H-1 (highest risk: ID-namespace unification on order tracking)

**Finding:** `live_engine._pending_entry_order_ids[sym]` stores the
*internal* DB UUID. `alpaca_stream._terminal_order_ids` is keyed by
*broker* `order_id`. `is_order_terminal(internal_uuid)` checks against
the broker-id set — never matches. The 30-tick early-clear path for
rejected orders is dead, so symbols stay locked for the full cooldown
after every reject.

**Fix design:** `alpaca_stream._on_trade_update` already has both IDs
in scope at the moment we record terminal state (line 510 reads
`order.id` from the DB lookup; line 525 reads `order_data["id"]` =
broker id). Add **both** strings to `_terminal_order_ids` so
`is_order_terminal()` returns True regardless of which ID the caller has.
Cap doubles to 2000-keep-1000 to keep the same effective horizon
(`_terminal_order_ids` was already capped at 1000-keep-500).

This is the smallest possible change that unifies the namespace without
restructuring the order state machine.

**Risk:** medium. The set is hot-path-read by `live_engine` early-clear.
A bug in the recording side could lock symbols (current behavior — no
regression) or unlock symbols incorrectly (fixable by reverting).
Mitigation:
- Keep the broker_oid recording exactly as before (no behavior loss).
- Just *additionally* record `order.id`.
- Verify in container that the early-clear path now fires for a synthetic
  rejected order (or at least that the set contains both IDs).

**Verification:**
- Brain coherent across recreate.
- Container healthy.
- Add an inline guard / log at the early-clear path so we can see in
  logs when it actually fires (this is observable evidence the fix
  works in production).

## Execution order

| Order | Wave | Risk | Reason |
|---|---|---|---|
| 1 | 16a | none | test-only, decide & document |
| 2 | 16b | low | test-only, rewrite |
| 3 | 16c | low | dead-code + docstring, no behavior change |
| 4 | 16d | medium | order-tracking state machine — last so we can deploy/verify each prior layer first |

Each sub-wave: implement → unit test → docker-compose build & recreate →
health check → brain-coherence diff → commit. Same cadence as 12-15.

## Rollback policy

If 16d shows any post-deploy anomaly (restart count > 0, brain
manifest divergence, unexpected log volume), `git revert HEAD` and
re-deploy. The fix is additive (adds an ID to a set); the revert is one
commit.

## What remains after 16

After 16 ships:
- All V4 findings closed except items explicitly marked "hold for design"
  (none remain after Wave 16).
- Audit history: V1 30, V2 8, V3 58, V4 52 — total 148; ~145 closed.
- Suggest a V5 closure-regression sweep + new-surface tracks (S/T/U
  proposed in V4 synthesis) when ready.
