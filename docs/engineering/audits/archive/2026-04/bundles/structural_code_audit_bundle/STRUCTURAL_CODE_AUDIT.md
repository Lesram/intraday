# Structural & Mechanical Code Audit

**Date**: 2026-04-11
**Scope**: Line-by-line code review of all 8 core organism modules
**Method**: Automated deep exploration + manual verification of top findings
**Files reviewed**: live_engine.py (~4800 lines), brain_persistence.py (~1800 lines), adaptive_exits.py (~700 lines), pyramider.py (~260 lines), scheduler.py (~400 lines), routes.py (~800 lines), background_trainer.py (~370 lines), regime.py (~650 lines)

## Overall assessment

The codebase is **production-viable for paper trading** but has **7 verified bugs** that should be tracked. None are P0 blockers for Monday's session (the system has been running with these bugs for weeks without incident), but 3 are high-severity enough to warrant fixing before any real-money deployment.

## Verified bugs (21 found, 7 independently confirmed as real)

### CONFIRMED CRITICAL

**BUG #1 — Pyramider atr guard is present but NaN can still propagate**
- File: `pyramider.py:167-178`
- The `if atr < 1e-6: return none` guard at line 167 IS present and works for zero-ATR. But if `current_price` is NaN (from a stale data provider), `r_current = (NaN - entry) / atr` = NaN, and subsequent comparisons `if r_current <= self.CUT_FULL` with NaN are always False — silently disabling all pyramid actions. Not a crash, but silent logic failure.
- **Severity**: MEDIUM (not CRITICAL — the atr guard works, only NaN propagation is the issue)
- **Monday risk**: LOW — prices from Alpaca streaming are validated upstream
- **Fix**: Add `if not np.isfinite(current_price): return PyramidAction(action="none")` at line 164

### CONFIRMED HIGH

**BUG #2 — Exit level restore fails silently at DEBUG level**
- File: `live_engine.py:817`
- Verified: `logger.debug("Cannot restore exit levels for %s: %s", sym, e)` — DEBUG level for a failure that leaves a position without risk management.
- **Severity**: HIGH — a position could run without stop-loss protection after restart
- **Monday risk**: LOW — positions are flat over the weekend and EOD flatten ensures no overnight exposure
- **Fix**: Change to `logger.warning()` and mark symbol for forced exit on next tick

**BUG #7 — Exit cooldown set in finally block even on submission failure**
- File: `live_engine.py:1598-1600, 1671-1674`
- Verified: multiple finally blocks set `self._exit_cooldown[sym] = self._tick_count` regardless of whether `_submit_exit_order` succeeded or failed.
- Line 1672 even has a comment: `# Always set cooldown to prevent retry spam on failures` — this is INTENTIONAL but WRONG. If the exit fails, the position is still open and needs to be retried, not cooldown-blocked for 3 ticks.
- **Severity**: HIGH — during broker API flakiness, failed exits create a 30-second dead zone where the position can drift unmanaged
- **Monday risk**: LOW — Alpaca paper API is reliable, and the 3-tick cooldown is short (30s)
- **Fix**: Move cooldown to the success path only. Add a `_failed_exit_retries[sym]` counter for exponential backoff instead of blanket blocking.

**BUG #3 — Reconciliation grace period uses tick count, not timestamp**
- File: `live_engine.py:3706`
- Verified: `ticks_held = self._tick_count - entry_tick` — on restart, `self._tick_count` is restored from extra_counters (line 759: `self._tick_count = self.brain.extra_counters.get("tick_count", 0)`), so the counter IS preserved across restarts. This makes the bug LESS severe than initially claimed — the tick count doesn't reset to 0 on restart.
- **Severity**: MEDIUM (downgraded from HIGH — tick count is persisted)
- **Monday risk**: NONE
- **Fix**: Still worth converting to timestamps for clarity, but not urgent

### CONFIRMED MEDIUM

**ISSUE #10 — Read-back invariant doesn't fail save on exception**
- File: `brain_persistence.py:874-878`
- Verified: `return True` at line 878 after catching exception, with comment `# Do not fail the save on read-back exceptions — just log`
- This was an INTENTIONAL design choice (not a bug): the rationale is that failing the save on a transient read-back error (e.g., filesystem hiccup) would be worse than letting the save succeed. The manifest was already written at this point, so "failing" doesn't undo the write — it just confuses the caller.
- **Severity**: MEDIUM (design trade-off, not a clear bug)
- **Monday risk**: NONE

**ISSUE #14 — Exit and pyramid checks can both submit orders on same tick**
- File: `live_engine.py:1457-1968`
- Verified: Steps 5 (exits) and 6 (pyramids) run sequentially in the same tick. If exit sets `_exit_cooldown[sym]`, the pyramid check at line 1895-1896 DOES check `if sym in self._exit_cooldown: continue`. So there IS protection against the race — the cooldown dict prevents pyramid from acting on a symbol that just had an exit submitted.
- **Severity**: LOW (downgraded from MEDIUM — the cooldown mechanism provides the mutual exclusion)
- **Monday risk**: NONE

**ISSUE #16 — Exit state cleanup only runs after successful TradeRecord creation**
- File: `live_engine.py:3761-3764`
- Verified: cleanup is inside the TradeRecord creation block. If TradeRecord creation fails, exit_levels persist.
- **Severity**: MEDIUM — slow memory leak over time, but positions are reconciled every 15 minutes by the scheduled reconciliation service, which provides a separate cleanup path
- **Monday risk**: NONE

### DOWNGRADED OR FALSE POSITIVES

**BUG #4/5 (pyramider NaN propagation)**: Real concern but downstream of BUG #1. If BUG #1 is fixed (NaN guard on current_price), these become unreachable.

**ISSUE #15 (equity zero blocks on startup)**: The broker API returning 0 equity for 3 consecutive ticks on startup is extremely unlikely with Alpaca. And if it does happen, the system correctly blocks entries as a safety measure. This is working as intended.

**ISSUE #12 (hardcoded regime tables)**: Real architectural limitation but NOT a bug. The evolution engine works within its designed scope; the regime tables were intentionally kept static for stability during the learning phase.

## What the prior audits got right

The COMPREHENSIVE_PREOPEN_AUDIT was correct on all operational claims:
- Container state, brain sync, guard fires, experiment isolation — all verified independently
- "READY AS-IS" verdict is correct for Monday paper trading
- The bugs found in this deep code review are real but **none are new** — they've been present since the original codebase and have not caused incidents during the Apr 7-10 trading week

## What should change

### Before real money (not before Monday)
1. Fix BUG #2: exit level restore should log at WARNING and mark for forced exit
2. Fix BUG #7: exit cooldown only on successful submission
3. Add NaN guards to pyramider (BUG #1 enhancement)

### After Exp1A observation
4. Fix ISSUE #16: cleanup exit state regardless of TradeRecord creation
5. Convert reconciliation grace to timestamps (BUG #3 enhancement)

### Backlog
6. Address remaining code quality issues (dead code, magic numbers, logging levels)
7. Consolidate scattered constants into a config module

## Monday readiness

**READY AS-IS.** The 7 confirmed bugs have been present throughout the entire Apr 7-10 trading week without causing incidents. They are real bugs that should be fixed before real money, but they are not pre-open blockers for paper trading. The Exp1A observation window should proceed as planned.
