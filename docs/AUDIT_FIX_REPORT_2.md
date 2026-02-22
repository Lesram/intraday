# Audit Fix Report 2 — Response to Second Deep Research Audit

**Date:** 2026-02-22
**Audit Source:** `docs/deep-research-report2.md` (Second independent AI audit, Grade: D, NO-GO)
**Status After Fixes:** All P0, P1, and P2 findings resolved

---

## Summary

The second independent audit re-evaluated the codebase after the first round of fixes (documented in `docs/AUDIT_FIX_REPORT.md`). It confirmed that the first round's 9 fixes were correctly implemented but identified **5 remaining critical issues** that were either pre-existing or introduced by the first round's structural changes. All findings were verified against actual code, confirmed valid, and fixed.

**Test Results After All Fixes:**
- Backend: **7,031 passed**, 684 skipped, 0 failures
- Frontend: **134 passed**, 0 failures
- Safety invariant tests: **9 new tests** added
- Total: **7,165 tests passing, 0 failures**

---

## P0 Fixes (Blockers)

### Fix 1: Insufficient Features Early Return No Longer Skips Exits

**Audit Finding:** `live_engine.py` line 668-673 had `if len(features_by_symbol) < 3: return result` which returned BEFORE `get_all_positions()`, the exit loop, reconciliation, and brain save. A data outage affecting feature computation would leave all open positions completely unmanaged.

**Root Cause:** The insufficient-features check was a hard early return, not a soft gate.

**Fix Applied:**
- **File:** `backend/organism/live_engine.py`
- Converted the early return to the `entries_blocked` pattern (same pattern used for governance halt and drawdown kill)
- When features < 3: sets `entries_blocked = True`, logs warning, continues to position fetch and exit checks
- Regime detection is guarded by `if not insufficient_features:` since it requires meaningful data
- Position fetch, exit loop (with broker price fallback), reconciliation, brain save, and metric export all still run

**Before:**
```
insufficient features → return immediately → positions unmanaged, no exits, no metrics
```

**After:**
```
insufficient features → entries_blocked=True → skip regime → fetch positions → run exits (broker fallback) → reconcile → brain save → equity curve → Prometheus
```

**Safety test:** `test_insufficient_features_still_processes_exits` — verifies `get_all_positions()` called, safety net exit triggered for a position down 20%, `duration_s > 0`.

---

### Fix 2: Evolution Baseline Mismatch Corrected

**Audit Finding:** `apply_evolved_params()` in `self_evolution.py` used baselines `(1.5, 3.0, 2.5, 3.0)` that didn't match the live engine's intraday config `(1.0, 2.0, 1.5, 2.0)`. When evolution scales default to 1.0, the first application would cause discontinuous parameter jumps (e.g., `atr_multiplier` jumping from 1.0 to 1.5).

**Root Cause:** The baselines were from an older swing-trading configuration, not updated when the engine was configured for intraday.

**Fix Applied:**
- **File:** `backend/organism/self_evolution.py` (lines 1176-1179)
- Changed baselines to match live engine's `AdaptiveExitEngine` constructor:
  - `atr_multiplier`: 1.5 → **1.0**
  - `trailing_start_atr`: 3.0 → **2.0**
  - `trailing_distance_atr`: 2.5 → **1.5**
  - `partial_tp_r`: 3.0 → **2.0**
- Added comment documenting that baselines MUST match the live engine's constructor values
- **File:** `tests/test_self_evolution.py` — Updated `test_apply_to_exit_engine` assertions

**Safety test:** `test_apply_evolved_params_default_scale_matches_intraday_baseline` — verifies that with default scale=1.0, the exit engine parameters equal exactly (1.0, 2.0, 1.5, 2.0).

---

## P1 Fixes (Critical)

### Fix 3: TIF Upstream Default Changed from GTC to Day

**Audit Finding:** `order_service.py` line 1381 had `tif = order_data.get("tif", "gtc")` which overrode the outbox layer's `day` default. Orders arriving without an explicit TIF would get `gtc`, creating unwanted overnight exposure for an intraday system.

**Root Cause:** The first round fixed the outbox layer (`alpaca_outbox.py`) but missed the upstream extraction point in `order_service.py`.

**Fix Applied:**
- **File:** `backend/services/order_service.py` (line 1381)
- Changed `order_data.get("tif", "gtc")` to `order_data.get("tif", "day")`
- Now the entire TIF pipeline is consistent: `order_service` → `alpaca_outbox` → broker, all defaulting to `day`
- GTC is only used when explicitly requested

**Safety test:** `test_order_service_default_tif_is_day` — verifies dict without `tif` key defaults to `"day"`.

---

### Fix 4: entries_blocked Path No Longer Skips Metrics Export

**Audit Finding:** Lines 934-935 in `live_engine.py` had `result.duration_s = ...; return result` in the entries_blocked path. This returned BEFORE the equity curve update, Prometheus metrics export, decision telemetry capture, and invariant checks.

**Root Cause:** The first round's Fix 1 (entries_blocked pattern) correctly continued exit processing but then returned too early, skipping the post-tick bookkeeping that lives outside the `try` block.

**Fix Applied:**
- **File:** `backend/organism/live_engine.py`
- Removed the `return result` from the entries_blocked block
- Removed duplicated reconcile + brain save + metadata from the entries_blocked block
- Steps 6-9 (pyramids, scan, sizing, entries) wrapped in `if not entries_blocked:` guard
- Step 10 (reconcile) stays OUTSIDE the guard — always runs
- Step 11 (retrain/evolve) wrapped in `if not entries_blocked:` guard
- Step 12 (brain save) stays OUTSIDE the guard — always runs
- Metadata stays OUTSIDE the guard — always runs
- Equity curve, Prometheus, telemetry, and invariant checks all run regardless of entries_blocked

**Before:**
```
entries_blocked → reconcile → brain save → return → (equity curve SKIPPED, Prometheus SKIPPED)
```

**After:**
```
entries_blocked → skip steps 6-9,11 → reconcile → brain save → metadata → equity curve → Prometheus → telemetry → invariants
```

**Safety test:** `test_entries_blocked_still_exports_metrics_and_runs_exits` — verifies `duration_s > 0`, reconcile called, orders_submitted == 0.

---

## P2 Fixes (Important)

### Fix 5: ORGANISM_SECTOR_CAP_BLOCKED Counter Wired

**Audit Finding:** The Prometheus counter `ORGANISM_SECTOR_CAP_BLOCKED` was declared at line 120 but never incremented anywhere in the code.

**Fix Applied:**
- **File:** `backend/organism/live_engine.py`
- Added `ORGANISM_SECTOR_CAP_BLOCKED.inc()` at both sector gate blocking sites:
  1. Alpha candidate loop — when `sector_gate_allows()` returns False
  2. Breakout signal loop — restructured the compound conditional to check sector gate separately, increment counter when blocked
- Both sites are guarded by `if _PROMETHEUS_AVAILABLE:`

---

### Fix 6: Safety Invariant Tests Added

**Audit Finding:** The audit recommended tests for critical safety properties to prevent regression.

**Fix Applied:**
- **File:** `tests/test_safety_invariants.py` (NEW — 9 tests)

| Test | Safety Property |
|---|---|
| `test_insufficient_features_still_processes_exits` | Exits run even with < 3 features symbols |
| `test_entries_blocked_still_exports_metrics_and_runs_exits` | Halted tick still exports metrics |
| `test_sector_gate_blocks_excess_same_sector_entries` | Sector accumulator prevents intra-tick breach |
| `test_sector_gate_unknown_sector_always_passes` | Unknown sectors don't crash the gate |
| `test_sector_gate_planned_symbols_none` | None planned_symbols is backward-compatible |
| `test_apply_evolved_params_default_scale_matches_intraday_baseline` | Evolution defaults = live engine init |
| `test_apply_evolved_params_with_scaled_values` | Non-unity scales multiply correctly |
| `test_order_service_default_tif_is_day` | TIF default is 'day', not 'gtc' |
| `test_order_service_explicit_tif_honored` | Explicit TIF values pass through |

---

## Files Modified

### Backend Code
| File | Changes |
|---|---|
| `backend/organism/live_engine.py` | P0: Insufficient features uses entries_blocked instead of early return; P1: entries_blocked falls through to metrics; P2: Sector cap counter wired at both gate sites; Regime detection guarded by insufficient_features flag; Steps 6-9 and 11 wrapped in `if not entries_blocked:` |
| `backend/organism/self_evolution.py` | P0: Evolution baselines corrected from (1.5, 3.0, 2.5, 3.0) to (1.0, 2.0, 1.5, 2.0) |
| `backend/services/order_service.py` | P1: TIF default changed from 'gtc' to 'day' |

### Tests
| File | Changes |
|---|---|
| `tests/test_safety_invariants.py` | NEW: 9 safety invariant tests |
| `tests/test_self_evolution.py` | Updated: `test_apply_to_exit_engine` assertions match corrected baselines |

---

## Architecture Summary: Tick Flow After All Fixes

```
live_tick():
  1. GOVERNANCE CHECK
     halted → entries_blocked=True (fall through)

  2. FETCH FEATURES
     insufficient (<3 symbols) → entries_blocked=True (fall through)

  3. DETECT REGIME (only if sufficient features)

  4. GET POSITIONS (ALWAYS)
     drawdown kill → entries_blocked=True
     zero equity → entries_blocked=True

  5. CHECK EXITS (ALWAYS — broker price fallback if no features)

  ── if not entries_blocked: ──
  6. CHECK PYRAMIDS
  7. SCAN FOR NEW ENTRIES
  8. SIZE POSITIONS (Kelly)
  9. SUBMIT ENTRY ORDERS
  ── end gate ──

  10. RECONCILE FILLS (ALWAYS)

  ── if not entries_blocked: ──
  11. PERIODIC RETRAIN + EVOLVE
  ── end gate ──

  12. BRAIN SAVE (ALWAYS)
  13. METADATA (ALWAYS)

  ── outside try block (ALWAYS runs): ──
  14. UPDATE EQUITY CURVE
  15. PROMETHEUS METRICS EXPORT
  16. DECISION TELEMETRY CAPTURE
  17. INVARIANT CHECKS
```

**Key invariant:** Steps 4, 5, 10, 12-17 ALWAYS run regardless of halt/drawdown/insufficient-data state. No code path can skip exits, reconciliation, brain save, or metric export.

---

## Remaining Items

These were identified in the second audit as architectural recommendations (not blockers):

1. **Periodic full reconciliation against broker** — The stream never drops messages (first round Fix 2), but periodic `/v2/positions` polling would provide defense-in-depth.

2. **Property tests for self_evolution.py** — Evolution is constrained by `max_shift=0.20` and `min_trades=8`, but property-based tests would increase confidence in edge cases.

3. **Incident response runbook** — Should be created before live trading.

---

## Verification

All changes verified:
- **Backend tests:** 7,031 passed, 0 failures, 684 skipped
- **Frontend tests:** 134 passed, 0 failures
- **Safety invariant tests:** 9 passed, 0 failures (new)
- **Total:** 7,165 tests, 0 failures
- **No regressions introduced**
- **All second audit P0, P1, and P2 items resolved**
- **Syntax validation:** `ast.parse()` confirms `live_engine.py` parses correctly

*This report is intended for review by the 3rd party AI agent to confirm completeness.*
