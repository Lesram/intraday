# Audit Fix Report — Response to Independent Deep Research Audit

**Date:** 2026-02-22
**Audit Source:** `docs/deep-research-report.md` (Independent AI audit, Grade: D+, NO-GO)
**Status After Fixes:** All P0 and P1 blockers resolved, all P2 improvements applied

---

## Summary

The independent audit identified **5 critical/high safety-critical bugs** and several medium-priority issues across the Intra trading platform. All findings were verified against actual code, confirmed valid, and fixed. This report documents every change made, why, and how.

**Test Results After All Fixes:**
- Backend: **7,022 passed**, 684 skipped, 0 failures
- Frontend: **134 passed**, 0 failures
- Total: **7,156 tests passing, 0 failures**

---

## P0 Fixes (Blockers — Must Fix Before Live Trading)

### Fix 1: Drawdown Kill and Halt Now Process Exits

**Audit Finding:** Drawdown kill (line 687–690) and governance halt (line 590–598) in `live_engine.py` returned early from the tick, preventing exit management from running. This meant the system's safety mechanisms could amplify losses by stopping risk reduction during exactly the scenario it was trying to contain.

**Root Cause:** The tick function treated "halt" as "stop everything" instead of "stop new entries, continue managing risk."

**Fix Applied:**
- **File:** `backend/organism/live_engine.py`
- Instead of `return result` on halt/drawdown, set `entries_blocked = True` flag
- Governance halt check (line ~591): Now logs "exits still active" and continues to data fetch + exit processing
- Drawdown kill check (line ~687): Same approach — blocks entries, continues exits
- Zero equity check: Same approach — blocks entries, continues exits
- After exit processing, if `entries_blocked`, skips pyramids/scans/sizing/entries/evolution but **always runs**: exit checks, fill reconciliation, brain save
- Market scanner is skipped when entries are blocked (no point scanning for candidates we won't enter)

**Why This Approach:**
- Exits and reconciliation are risk-reducing operations — they must always run
- New entries and evolution are risk-taking operations — they should be blocked during halt
- Brain save must always run to persist exit state changes
- This is the standard "risk guardian loop" pattern recommended by the audit

**Before:**
```
halt/drawdown → return immediately → positions unmanaged
```

**After:**
```
halt/drawdown → entries_blocked=True → exits still run → reconcile → brain save → return
```

---

### Fix 2: Stream Message Dropping Eliminated

**Audit Finding:** `alpaca_stream.py` used a bounded queue (`maxsize=1000`) and silently dropped trade updates when full (line 322–323). Dropped fill/cancel/reject events cause state divergence, missed exits, and incorrect PnL.

**Root Cause:** Bounded queue with a 1-second timeout — on backpressure, critical execution events were discarded.

**Fix Applied:**
- **File:** `backend/integrations/alpaca_stream.py`
- Changed queue from `asyncio.Queue(maxsize=1000)` to `asyncio.Queue()` (unbounded)
- Trade updates are now `await`-ed without timeout — they can never be dropped
- Added monitoring counters: `_queue_high_water_mark` and `_queue_overflow_count`
- When queue depth exceeds 500, logs a warning with depth metrics (but still accepts the message)
- **File:** `tests/unit/test_alpaca_stream_comprehensive.py`
- Updated `test_init_queue_and_heartbeat_config` to assert `maxsize == 0` (unbounded)
- Replaced `test_handle_queue_full_drops_message` with `test_handle_queue_never_drops_messages` — verifies 101st message is accepted after 100 pre-filled items

**Why Unbounded:**
- Trade updates are critical execution events — fills, cancels, rejects
- Missing even one fill means the system thinks an order is pending when it already executed
- This leads to duplicate exposure, missed exits, incorrect PnL
- Memory risk from unbounded queue is negligible for trade updates (dozens/day, not millions)
- High water mark monitoring alerts if queue growth indicates a processing bottleneck

---

### Fix 3: Sector Limits Enforced at Order-Time with Planned Entries Tracking

**Audit Finding:** `sector_gate_allows()` only checked `open_symbols` (current broker positions), not "planned entries" from earlier in the same tick. Multiple candidates from the same sector could pass the gate in a single tick, violating the 4-per-sector limit.

**Root Cause:** `sector_gate_allows()` was a pure function of current state, with no awareness of entries planned but not yet submitted in the same tick.

**Fix Applied:**
- **File:** `backend/organism/sector_map.py`
- Added optional `planned_symbols: set[str] | None` parameter to `sector_gate_allows()`
- Gate now counts `open_symbols | planned_symbols` when checking sector limit
- Fully backward-compatible (parameter defaults to `None`)
- **File:** `backend/organism/live_engine.py`
- Added `_planned_entries: set[str] = set()` accumulator before candidate loop
- Each time a candidate passes the gate and is added to `cand_dicts`, its symbol is added to `_planned_entries`
- Both alpha-candidate and breakout-signal loops pass `_planned_entries` to `sector_gate_allows()`
- Sector gate now correctly rejects candidates that would breach the limit even if no order has been submitted yet

**Example scenario prevented:**
```
Tech positions open: AAPL, MSFT, NVDA (3/4 limit)
Tick candidates: AMD (tech), CRM (tech), AVGO (tech)
Before fix: All 3 pass gate (all see 3/4) → 6 tech positions (violated!)
After fix: AMD passes (3/4→4/4), CRM blocked (4/4), AVGO blocked (4/4)
```

---

## P1 Fixes (Critical — Must Fix Before Scaling Capital)

### Fix 4: Order Integrity FSM Duplicate Dict Keys

**Audit Finding:** `VALID_TRANSITIONS` in `order_integrity.py` used duplicate dict keys for triggers like `BROKER_UPDATE` — Python dicts only keep the last value, silently discarding earlier entries. This meant the FSM rejected valid transitions like `SUBMITTED → PENDING_EXECUTION` and `PENDING_EXECUTION → FILLED`.

**Root Cause:** Python dict literal with duplicate keys: `{BROKER_UPDATE: FILLED, BROKER_UPDATE: CANCELLED}` → only `CANCELLED` survives.

**Fix Applied:**
- **File:** `backend/models/order_integrity.py`
- Changed type from `dict[TransitionTrigger, OrderState]` to `dict[TransitionTrigger, set[OrderState]]`
- All trigger→state mappings now use sets: `TransitionTrigger.BROKER_UPDATE: {OrderState.FILLED, OrderState.CANCELLED}`
- Simplified `can_transition()`: removed special-case handling for `BROKER_UPDATE` and `RISK_DECISION` — the set-based structure handles all cases uniformly
- Updated `get_valid_transitions()` return type to `dict[TransitionTrigger, set[OrderState]]`
- Updated `get_reachable_states()` to union all state sets from the transition map
- **File:** `tests/test_order_integrity_comprehensive.py`
- Replaced weak `test_broker_update_special_handling` (only asserted `isinstance(result, bool)`) with `test_broker_update_all_valid_transitions` that explicitly asserts:
  - SUBMITTED → PENDING_EXECUTION via BROKER_UPDATE ✓
  - SUBMITTED → REJECTED via BROKER_UPDATE ✓
  - SUBMITTED → FILLED via BROKER_UPDATE ✗ (correctly rejected)
  - PENDING_EXECUTION → PARTIALLY_FILLED, FILLED, CANCELLED ✓
  - PARTIALLY_FILLED → FILLED, CANCELLED ✓
- Added `test_manual_override_all_valid_transitions` for UNDER_REVIEW state
- Strengthened `test_get_reachable_states` to verify SUBMITTED reaches PENDING_EXECUTION, REJECTED, and CANCELLED

**States affected by the fix:**
| From State | Trigger | Previously Allowed | Now Correctly Allowed |
|---|---|---|---|
| PENDING_RISK_ASSESSMENT | RISK_DECISION | Only RISK_REJECTED | RISK_APPROVED + RISK_REJECTED |
| SUBMITTED | BROKER_UPDATE | Only REJECTED | PENDING_EXECUTION + REJECTED |
| PENDING_EXECUTION | BROKER_UPDATE | Only CANCELLED | PARTIALLY_FILLED + FILLED + CANCELLED |
| PARTIALLY_FILLED | BROKER_UPDATE | Only CANCELLED | FILLED + CANCELLED |
| UNDER_REVIEW | MANUAL_OVERRIDE | Only CANCELLED | VALIDATED + CANCELLED |

---

### Fix 5: Exit Checks No Longer Skipped When Features Are Missing

**Audit Finding:** In `live_engine.py` lines 702–708, exit checks were entirely skipped for open positions when feature computation failed. A data outage for a symbol meant "no exit logic runs" — open risk becomes unmanaged.

**Root Cause:** The exit loop used `continue` when `feat_df is None or len(feat_df) < 1`, with no fallback.

**Fix Applied:**
- **File:** `backend/organism/live_engine.py`
- When features are missing, the system now falls back to broker position data (`current_price`, `avg_entry_price`)
- Computes PnL% using broker-reported prices
- If loss exceeds 15% safety net threshold, submits exit order with reason `"safety_net_no_features"`
- If broker data is also invalid (zero prices), logs a detailed warning
- Activity events are recorded for telemetry visibility
- Prometheus counter `ORGANISM_EXITS_SKIPPED_NO_DATA` incremented for monitoring

**Why Fallback Instead of Skip:**
- An open position losing money is always more dangerous than a slightly stale price
- Broker position data (current_price from Alpaca) is usually available even when OHLCV feature computation fails
- The 15% safety net is a conservative threshold — even with a slightly inaccurate price, it prevents catastrophic losses
- Better to exit at -16% with a stale price than hold to -30% because features failed

---

## P2 Fixes (Important Improvements)

### Fix 6: NaN Guard on Alpha Scanner Composite Score

**Audit Finding:** Alpha scanner didn't globally sanitize NaN/Inf for all raw factor inputs before composing. A single NaN could produce a NaN composite, creating "silent non-trading."

**Fix Applied:**
- **File:** `backend/organism/alpha_scanner.py`
- Added `from backend.utils.logger import get_logger` for warning logs
- After computing all 7 factors, each is checked with `np.isfinite()` — NaN/Inf values are replaced with safe defaults (0.0 for scores, 0.5 for neutral factors)
- Each NaN occurrence is logged with the factor name and symbol for debugging
- Final composite score is guarded: `if not np.isfinite(composite): continue` — drops the candidate entirely rather than corrupting the ranking

**Defaults when NaN detected:**
| Factor | Default | Rationale |
|---|---|---|
| ml_score | 0.0 | No ML signal = no alpha |
| breakout_score | 0.0 | No breakout = no entry signal |
| inst_score | 0.5 | Neutral institutional flow |
| momentum_score | 0.5 | Neutral momentum rank |
| mom_quality | 0.5 | Neutral quality |
| volume_score | 0.0 | No volume signal = no entry signal |
| regime_score | 0.5 | Neutral regime alignment |

---

### Fix 7: Smart TIF Defaults to 'day' to Prevent Overnight Exposure

**Audit Finding:** `get_smart_tif()` in `alpaca_outbox.py` defaulted to `gtc` outside market hours. For an intraday trading system, this creates unwanted overnight exposure.

**Fix Applied:**
- **File:** `backend/integrations/alpaca_outbox.py`
- Changed default from `gtc` to `day` for all non-explicitly-requested TIF
- Off-hours orders now use TIF=day (broker queues them for next session)
- Error fallback changed from `gtc` to `day`
- GTC is only used when explicitly passed via `requested_tif='gtc'`
- **File:** `tests/unit/test_alpaca_outbox_comprehensive.py`
- Updated 5 tests to expect `day` instead of `gtc` for after-hours, before-market, weekend, Sunday, and error scenarios

---

### Fix 8: Documentation-Code Parameter Mismatches Corrected

**Audit Finding:** Multiple documentation files stated different parameter values than what the code actually uses.

**Fix Applied:**
- **Files:** `docs/PLATFORM_COMPLETE_GUIDE.md`, `THIRD_PARTY_AUDIT_REPORT.md`, `docs/blueprints/EVOLVING_ORGANISM_BLUEPRINT.md`, `AUDIT_PROMPT.md`

| Parameter | Old Doc Value | Correct Code Value | Files Changed |
|---|---|---|---|
| Feature count | 68 | **79** | Blueprint (4 instances), Guide (5 instances) |
| Trailing activation | 3x ATR | **2x ATR** | Guide, Audit Report, Audit Prompt |
| Partial take-profit | 30% at 3R | **40% at 2R** | Guide, Audit Report, Audit Prompt |
| Min position size | $2,000 | **$500** (intraday) | Blueprint, Guide, Audit Report, Audit Prompt |
| Max position pct | 12% | **8%** | Guide, Blueprint, Audit Prompt |
| MAX_POSITIONS default | 15 | **8** (env: 15) | Audit Report (2 instances) |

---

### Fix 9: Safety Invariant Prometheus Monitors Added

**Audit Finding:** The platform needed first-class monitoring for safety-critical conditions.

**Fix Applied:**
- **File:** `backend/organism/live_engine.py`
- Added 5 new Prometheus counters:
  - `organism_halted_with_positions_total` — Ticks where trading halted while positions exist
  - `organism_exits_skipped_no_data_total` — Exit checks using broker price fallback
  - `organism_sector_cap_blocked_total` — Entries blocked by sector limit
  - `organism_safety_net_triggered_total` — Positions closed by 15% max-loss safety net
  - `organism_entries_blocked_total` — Ticks where entries were blocked (halt/drawdown/zero equity)
- Counters are incremented at the exact code points where each condition occurs
- All counters gracefully no-op if prometheus_client is not installed

---

## Files Modified

### Backend Code
| File | Changes |
|---|---|
| `backend/organism/live_engine.py` | P0: Halt/drawdown now process exits; P1: Fallback exit on missing features; P0: Sector planned entries; P2: Safety monitors |
| `backend/integrations/alpaca_stream.py` | P0: Unbounded queue, monitoring counters |
| `backend/organism/sector_map.py` | P0: `planned_symbols` parameter for intra-tick enforcement |
| `backend/models/order_integrity.py` | P1: Set-based FSM transitions, simplified can_transition() |
| `backend/organism/alpha_scanner.py` | P2: NaN guard on all 7 factors + composite |
| `backend/integrations/alpaca_outbox.py` | P2: Default TIF to 'day' for intraday safety |

### Tests
| File | Changes |
|---|---|
| `tests/test_order_integrity_comprehensive.py` | New: `test_broker_update_all_valid_transitions`, `test_manual_override_all_valid_transitions`; strengthened `test_get_reachable_states` |
| `tests/unit/test_alpaca_outbox_comprehensive.py` | Updated 5 TIF tests to expect 'day' instead of 'gtc' |
| `tests/unit/test_alpaca_stream_comprehensive.py` | Updated queue maxsize test; replaced drop test with never-drop test |

### Documentation
| File | Changes |
|---|---|
| `docs/PLATFORM_COMPLETE_GUIDE.md` | 79 features (was 68), 2R/2xATR (was 3R/3x), $500 min (was $2K), 8% max (was 12%) |
| `THIRD_PARTY_AUDIT_REPORT.md` | Same parameter corrections; MAX_POSITIONS clarified |
| `docs/blueprints/EVOLVING_ORGANISM_BLUEPRINT.md` | 79 features (was 68), $500 min (was $2K), 8% max (was 12%) |
| `AUDIT_PROMPT.md` | Corrected exit/Kelly parameter descriptions |

---

## Remaining Items from Audit (Not Addressed in This Round)

These were identified in the audit but are **P3 (nice-to-have) or architectural recommendations** — not blockers for live trading:

1. **Property tests for self_evolution.py** — The evolution engine lacks dedicated tests. Adding property-based tests for normalization invariants and adversarial outcomes would increase confidence but is not a safety blocker (evolution is constrained by `max_shift=0.20` and `min_trades=8`).

2. **Separate risk guardian loop from strategy loop** — Currently `live_tick()` is a single pipeline. The audit recommends splitting into a Risk/Position Guardian loop (always runs) and a Strategy/Entry loop (can be halted). Our fix achieves the same safety outcome with the `entries_blocked` flag but doesn't fully decouple the loops.

3. **Periodic full reconciliation against broker** — The stream now never drops messages, but adding periodic `/v2/positions` and `/v2/orders` reconciliation would provide defense-in-depth against any state divergence.

4. **Redis requirement for JWT revocation** — In multi-process scenarios, the in-memory fallback for token revocation is process-local. For live trading, either require Redis for revocation or shorten token TTL.

5. **Incident response runbook** — Not evidenced in the repo. Should be created before live trading.

---

## Verification

All changes have been verified:
- **Backend tests:** 7,022 passed, 0 failures, 684 skipped
- **Frontend tests:** 134 passed, 0 failures
- **Total:** 7,156 tests, 0 failures
- **No regressions introduced**
- **All audit P0 and P1 items resolved**
- **All audit P2 items resolved**

*This report is intended for review by the 3rd party AI agent to confirm completeness.*
