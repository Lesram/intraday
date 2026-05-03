# Track DD3 v9 — Strategy Logic Phase 3

Repo: `/Users/marselkei/VS/intra`. Branch `rc-1.5-curated` @ `ccba97f`.
Read-only audit. No fixes. 6 findings + Day-1 production analysis. Source-file:line citations and behavioral test descriptions follow each finding.

---

## DD3-1 — Pyramider re-fires Layer 1 indefinitely (and Layer 2 is unreachable) after the post-fill collapse

**Severity:** High (correctness — wrong size profile per design; under-pyramids after L1; never reaches L2)

`_reconcile_fills` collapses every PyramidPosition to a single layer once a broker `avg_entry_price` sync runs:

- `backend/organism/live_engine.py:5114-5129` — after a successful add (`broker_qty > old_shares`), `highest_level += 1`, then `pyr.layers = [PyramidLevel(shares=int(broker_qty), entry_price=broker_avg, ..., level=highest_level)]`. So after a Layer 1 fill, `pyr.layers` has exactly one element with `level=1` and `len(layers) == 1`.

But `MomentumPyramider.check_pyramid` decides what to add by `position.layer_count` (= `len(self.layers)`), not by `level`:

- `backend/organism/pyramider.py:273-274` — `if position.layer_count == 1 and r_current >= self.ADD_1_THRESHOLD: add Layer 1 again` — fires whenever R returns to ≥1.5 after the collapse.
- `backend/organism/pyramider.py:289-290` — `if position.layer_count == 2 and r_current >= self.ADD_2_THRESHOLD:` — never reachable, because the post-fill collapse always leaves `layer_count == 1`.

Effect:
1. After a confirmed L1 add, the position is one layer with `level=1` but `layer_count==1`. The pyramider keeps suggesting `pyramid_L1_at_*`. Each re-add is gated by `_pending_entry` 30-tick TTL (`live_engine.py:1539`), but once that expires and the price is still at +1.5R, it re-fires — adding another L1 (30% of target) on top of the previously-collapsed cost basis.
2. Layer 2 (10% top-up at +3.0R) is dead code: `layer_count == 2` is never true post-collapse.
3. `MAX_LAYERS=3` early-out (`pyramider.py:256`) is also unreachable for the same reason — `layer_count` stays at 1 forever.

**Behavioral test that locks it:**
Construct a PyramidPosition with target=100 and an initial fill of 60 shares (Layer 0). Have the pyramider observe price hit +1.6R, return `add` for +30 shares. Inject a fake broker position showing 90 shares with the new weighted avg, run `_reconcile_fills`. Assert that `pyr.layers` has length 1 with `level=1`. Then call `pyramider.check_pyramid` with the same +1.6R price after the `_pending_entry` TTL expires. Assert the action is **not** `add` again. The current code returns `add` with another 30-share request — the test should fail until the pyramider keys on `level` rather than `layer_count`, or the collapse preserves multi-layer count.

---

## DD3-2 — `LotTracker.create_lot` is called once per `partially_filled` event with the **cumulative** filled_qty, producing duplicate position-lot rows

**Severity:** High (data integrity — `position_lots` and `realized_trades` cost basis is over-counted on multi-fill orders)

`backend/integrations/alpaca_stream.py:553-589` invokes `LotTracker.create_lot` whenever `internal_status in ("filled", "partially_filled") and filled_qty > 0`. Alpaca's WebSocket `trade_updates` payload semantics: `filled_qty` is **cumulative** across all fill events for the same order (i.e. event 1 = 30, event 2 = 80, event 3 = 100). The handler at line 568 (`_qty_dec = Decimal(str(filled_qty))`) and line 577 (`_lot_tracker.create_lot(qty=_qty_dec, ...)`) passes the cumulative value to `create_lot`.

`backend/services/lot_tracker_service.py:35-83` — `create_lot` always creates a new `PositionLot` row with `qty=qty, remaining_qty=qty`. There is no idempotency / upsert by `order_id`.

For a 100-share buy filled in 3 partial events (30, 50, 20):
- Event 1 (status=`partially_filled`, filled_qty=30) → row A: qty=30
- Event 2 (status=`partially_filled`, filled_qty=80) → row B: qty=80
- Event 3 (status=`filled`, filled_qty=100) → row C: qty=100

The position is now 100 shares but `position_lots` has three rows summing to 210 shares. Subsequent `close_lots_fifo` (`alpaca_stream.py:591-605`) walks FIFO across these inflated rows and produces wrong realized-PnL attribution.

This is one bug class away from V8 BB-8 / Wave-30, which fixed the *missing* `create_lot` call site but missed the partial-fill semantics.

**Behavioral test that locks it:**
Inject three trade-update messages with `client_order_id=X` and `filled_qty` values 30 / 80 / 100 (statuses `partially_filled` / `partially_filled` / `filled`). Drive them through `_process_trade_update`. Assert that `position_lots` has exactly one row for `order_id=X` with `qty=100`. Current code yields three rows.

---

## DD3-3 — Slow broker fills break `_pending_exit` dedup and can submit duplicate exit orders

**Severity:** High (oversell risk — second exit fires for full broker qty while first partial is still in flight)

The exit-side loop only de-duplicates exit submissions via `_pending_exit` with TTL `_PENDING_EXIT_TICKS = 3` (~30 s):

- `live_engine.py:613` — TTL constant.
- `live_engine.py:1562-1566` — pending_exit cleared at TTL.
- `live_engine.py:2224-2259` — exit-side loop: only routine exit checks are skipped while `sym in self._pending_exit`; `_exit_cooldown` is **not** checked.

Meanwhile `_exit_cooldown` (10 tick TTL, `live_engine.py:591`) is read **only** at the entry gate (`live_engine.py:840`) and the pyramid gate (`live_engine.py:2681`).

Scenario:
1. Tick T: trailing_stop fires → `_submit_exit_order(qty=100, partial=False)`. Both `_pending_exit[sym]=T` and `_exit_cooldown[sym]=T` set.
2. Broker is slow; the order is still `pending` at T+3.
3. Tick T+4: `_pending_exit` has expired. Broker `pos_data["qty"]` still shows 100. Exit loop runs `check_exit` again; trailing still fires (price hasn't recovered). New order for 100 shares submitted with a fresh idempotency key (`tick_count` differs — `live_engine.py:5028-5029`).
4. Both broker orders eventually fill → 200 shares sold against a 100-share long → 100-share **short**. LONG_ONLY guard at `_submit_exit_order` (line 4994-4999) clamps the *second* attempt to `min(shares, broker_qty)`, but only if broker has not yet booked the first fill against the position. In practice the second submit lands while broker still shows qty=100, slips through the clamp, and creates an opposing position when both fills land within milliseconds.

Worse for **partial** exits: the partial-TP path submits (e.g.) 30 shares with `partial_pct=0.30`, sets `_pending_exit`, sets `partial_tp_taken=True` on `levels`. After TTL expiry, `partial_tp_taken` blocks **partial** re-fire (`adaptive_exits.py:587`) — but the unsold 70 still satisfies a stop/trailing/timeout test. A second non-partial exit can then fire for the full broker qty (100), and now the partial 30 + full 100 both pend.

**Behavioral test that locks it:**
Build a synthetic test where a position has `qty=100` at the broker, the engine submits an exit at tick T, the broker mock holds the order in `pending` state, and `pos_data["qty"]` is still 100 at tick T+4. Drive `_live_tick_inner` four times. Assert `_total_exits_submitted == 1`. Current code submits a second exit at T+4 and reaches `_total_exits_submitted == 2`.

---

## DD3-4 — EOD flatten does not cancel pending entries; entries submitted at 15:57 ET can fill after 16:00 with no exit infrastructure

**Severity:** Medium (after-hours risk, post-EOD exposure not blocked)

`_cancel_pending_entry_orders` exists and is wired only at drawdown-kill (`live_engine.py:2189`). The EOD flatten branch (`live_engine.py:2463-2497`) only iterates `current_positions` to send sells — it never clears `_pending_entry_order_ids` or calls `cancel_order` on entry orders that were submitted in the last few minutes before 15:58 ET.

Combined with `_PENDING_ENTRY_TICKS = 30` (~5 min, `live_engine.py:597`) and the bar-close cadence:
- Tick at 15:57:30 ET: alpha+breakout passes the late-day rule (`_alpha_breakout_late_blocked` only sets at 15:45+ but doesn't unwind already-queued candidates inside the same tick), or ORB live (which is exempt from the late-day rule per the comment at line 1709-1717). Broker order placed.
- Tick at 15:58 ET: EOD flatten fires for *existing* positions; the still-pending entry order is **not cancelled**.
- Tick at 16:00 ET: market closes. The 15:57 order has not filled at the broker yet (paper Alpaca queues for next-open).
- Next session: order fills overnight or on next open. The position appears as orphaned at the broker. The `_reconcile_fills` orphan-adoption path (`live_engine.py:5453-5530`) adopts it, tags it `entry_source="reconciliation_orphan"`, and computes new exit levels from a stale ATR. Pyramid adds are blocked for orphan-adopted positions (`live_engine.py:2706-2712`), but **regular exit/trailing logic still applies**, with an ATR computed from the previous-day's history.

**Behavioral test that locks it:**
Patch the clock at 15:57 ET, drive a tick that successfully submits a paper entry order. Patch the clock at 15:58 ET and drive another tick. Assert that `_pending_entry_order_ids` is empty (current code keeps it). Assert that `cancel_order` was called against the broker for the pending order id (current code never calls cancel here). The test should fail until EOD flatten calls `_cancel_pending_entry_orders()`.

---

## DD3-5 — `symbol_fitness` is empty in saved brain state; the production fitness gate is structurally inert

**Severity:** Medium (governance design intent not realised)

`evolved_params.json` after generation 168 / 491 strategy trades shows:
```
"symbol_fitness": {}
"symbol_trade_counts": {"XLE": 10, "XLK": 8, "SH": 6, "SPY": 5, ...}
```

The production gate at `live_engine.py:2846-2867`:
```
_MAIN_FITNESS_GATE = 0.45
_MIN_TRADES_FOR_FITNESS_GATE = 10
sym_fitness = self.evolved_params.symbol_fitness.get(symbol, 0.5)
if (not self._is_learning_mode
    and _sym_trade_count >= 10
    and sym_fitness < 0.45):
    return False, "fitness_gate"
```

Because `symbol_fitness` is empty, every lookup returns the safe default `0.5`. `0.5 > 0.45` for every symbol — the gate **never rejects**. XLE (the only symbol that has crossed 10 trades) currently has no recorded fitness value despite 168 evolution generations.

`_evolve_symbol_fitness` (`backend/organism/self_evolution.py:623-707`) groups the latest 200 strategy trades by symbol and writes fitness when `params.symbol_trade_counts[sym] >= 10`. The check uses the canonical `symbol_trade_counts` (not just the slice) so XLE with 10 should populate. The serialization at `self_evolution.py:157-159` does include the field. The empty saved state therefore implies one of:
- evolve() ran but XLE's recent slice contained no XLE trades (the latest 200-trade window ends before XLE's 10 trades), so `by_symbol["XLE"]` was missing and the assignment never happened — XLE keeps default 0.5 (which is never written), and the production-mode "hard gate at 0.45" is functionally absent for the only qualifying symbol.
- The brain restore path overwrites the in-memory map. `from_dict` (`self_evolution.py:218-221`) only assigns `symbol_fitness` when present in the persisted dict. If a previous save did write `{}`, the live restore reads `{}`.

Either way, the *runtime*-observable fact is: production gate is permissive for the foreseeable trading window because the data structure it depends on is empty.

**Behavioral test that locks it:**
Construct an EvolvedParams with `symbol_trade_counts={"XLE": 12}` and `symbol_fitness={}`. Run `EvolutionEngine.evolve()` with a list of 200 trades that includes 5 XLE trades all losing. Assert that `evolved_params.symbol_fitness["XLE"] < 0.45`. Then in live_engine, drive an XLE entry candidate; assert it is rejected with `reason="fitness_gate"`. Currently, the slot stays empty and the candidate passes.

---

## DD3-6 — Day-1 production analysis (2026-05-01): edge concentrated in one trade; pyramid_cut accounts for a third of all closes

**Severity:** Diagnostic (not a code bug — but flags strategic fragility)

From `organism_brain/trade_history.csv` filtered on `closed_at LIKE '2026-05-01%'` (16 rows):

| exit_reason | count | total_pnl |
|---|---|---|
| max_holding_period | 7 | +$85.34 |
| pyramid_cut_full_at_-1.0R…-1.7R | 5 | -$4.72 |
| trailing_stop | 2 | -$9.13 |
| failure_to_follow | 2 | -$3.14 |

Net: **+$69.35 (memory matches), 8/16 wins (50%), avg $4.33/trade**. Removing the single AMD trade (held 72 bars high_vol→chop, +$51.45 via max_holding_period) leaves **$17.90 across 15 trades = $1.19/trade — economically indistinguishable from zero** after broker rounding and slippage on intraday fills.

Pyramider's anti-pyramid (`pyramider.py:240-253`) cut 5 of 16 positions at -1.0R to -1.7R — 31% of all exits. The pyramider's `CUT_FULL=-1.0` and `CUT_PARTIAL=-0.7` gates fire **before** the regime ATR stop has had a chance to trigger; the position is closed at a fraction of the regime's intended risk distance. Combined with finding **DD3-1** (pyramider stuck in Layer 1 add loop), the pyramider is doing more cutting than adding on Day-1.

12 of 16 trades had `predicted_return ≤ 0.001` (effectively zero ML signal); only 1 trade (XLE, 0.010375) carried a non-trivial ML prediction. So the surgical-fix-#2 (`DROP_ML_FROM_GATE=true`) is doing what was intended — ML weight is dropped — but the consequence is that **all but one Day-1 entry was effectively pure-breakout / pure-tension**, with no ML steering. Several `entry_source="alpha+breakout"` trades had `predicted_return=0.003` exactly: that's the legacy floor, meaning these trades were tagged before today's deploy. Current `entry_source` semantics for those rows is unreliable (consistent with the memory note about pre-2026-05-01 source tags being corrupted).

Day-1 is one session: not enough to draw distributional conclusions, but it surfaces two structural points:
1. The strategy survives Day-1 only because of a single high-vol trend trade. Removing it surfaces zero edge.
2. Pyramider cut-rate is consistent with `_CHOP_MIN_HOLD_BARS=10` Experiment 1A blocking *some* premature cuts, but pyramider cuts via `r_current` (not via the EXIT-001 close_partial path) — so the chop-min-hold gate at `live_engine.py:2750-2766` does NOT apply to the `cut_partial`/`cut_full` paths in `pyramider.py:240-253`. Those go through the same `close_partial` action handler at `live_engine.py:2740`, where the chop-min-hold guard **does** sit — but only for the `pyramid_close_partial` action. Re-reading the code: yes, the chop-min-hold gate at line 2755 catches *all* `close_partial` actions, including pyramider cuts. So 5 cut exits despite chop-min-hold means either (a) bars_held ≥ 10 already at cut time, or (b) regime was not chop. From the row data, 4 of 5 were `chop`, with bars_held: 6 (XLE), 9 (AMZN), 7 (GOOGL), 27 (CRM). Only the CRM cut respected the 10-bar minimum; the other three chop cuts at bars_held < 10 should have been suppressed but were not. The mismatch deserves drill-down (could be an off-by-one in `_bars_held = self._tick_count - _entry_tick` since `entry_tick` is set at submit time, not first-fill time).

**Behavioral test that locks it (for the chop-min-hold mismatch):**
Construct a chop position with `_entry_metadata[sym]["entry_tick"]` set 8 ticks before current tick. Have the pyramider return `close_partial` with `reason="cut_partial_at_-0.8R"`. Drive `_live_tick_inner`. Assert no exit order is submitted (chop-min-hold should suppress). Currently the exit appears to fire — verify against the GOOGL/AMZN/XLE rows that show `bars_held=7,9,6` with chop+pyramid_cut exit reasons.

---

## TL;DR

DD3 finds one high-severity logic bug in the pyramid state machine (Layer 1 re-fires, Layer 2 unreachable post-fill collapse — `pyramider.py:273-304` + `live_engine.py:5114-5129`); one high-severity data-integrity bug in the lot-tracker fill handler (cumulative `filled_qty` written as a fresh row per partial event in `alpaca_stream.py:553-589`); one high-severity oversell race when broker fills are slower than the 3-tick `_pending_exit` TTL (`live_engine.py:2224 / 1562-1566`); one medium EOD blind spot where pending entries are not cancelled at flatten and can fill after-hours (`live_engine.py:2463-2497`); one medium governance issue where `symbol_fitness` is empty so the production "hard gate at 0.45" is permissive in practice (`evolved_params.json` + `live_engine.py:2860`); plus a Day-1 production diagnostic showing edge concentrated in a single AMD trade ($51 of $69 P&L) and a chop-min-hold suppression mismatch on three pyramid cuts. Net: the lifecycle and partial-fill state machines have real gaps, and the few-trade Day-1 result is statistically and structurally fragile.
