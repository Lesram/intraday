# Track DD3 v9 — Strategy Logic Phase 3

V8 DD2 found 10 strategy findings. Wave-32-35 closed DD2-1/2/3/4/5/7/8/9/10. **DD3 drills into the position lifecycle, partial-fill state machine, pyramid vs new-entry conflicts, and the Day-1 production observations** (per memory: "best post-deploy day, 16 trades, +$69.35 PnL, 50% win").

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `db1a3fc`.

## Method

### 1. Position lifecycle state machine — full audit

For one symbol, walk every state transition the position goes through:
- entry signal → entry order submitted → order accepted → order filled → position open
- pyramid signal → pyramid order → pyramid filled → position size increased
- partial-TP signal → partial exit submitted → partial fill → position size decreased
- ML reversal → partial exit → reduced position
- stop_loss → exit submitted → fill → position closed
- broker-side close (e.g. broker timeout) → reconciliation → realized_trade

For each transition, enumerate:
- What state is mutated? (`_exit_levels`, `_pending_entry`, `_pending_exit`, `_pyramid_positions`, `_ml_reversal_used`, etc.)
- Is the state mutation atomic w.r.t. concurrent ticks (if any)?
- What rollback path exists if the broker rejects?

### 2. Partial-fill state machine

Specifically:
- Order placed for 100 shares; broker fills 30, then 50, then nothing.
- `_pending_entry[sym]` set to tick-N; cleared by terminal-id detection or 3-tick TTL.
- Does `_exit_levels[sym]` get the correct avg_entry_price (weighted by partial fills)?
- Does `LotTracker.create_lot` get called once per fill or once per order?
- If the order is canceled with 30 of 100 filled, what happens to the remaining 70? Does Kelly attempt to re-size?

### 3. Pyramid vs new-entry conflict

Open position in AAPL (100 shares). Tick fires:
- Alpha + breakout signal recommend AAPL entry.
- Pyramid logic also recommends adding 50 shares.

Walk the code:
- `_passes_pyramid_gate` (or equivalent) — what's the precedence?
- Could a tick produce BOTH a "new entry" and a "pyramid" event for the same symbol, double-submitting?
- If pyramid is gated by `sym in self._exit_levels`, what if `_exit_levels` was cleared mid-tick by a stop-loss?

### 4. EOD flatten vs in-flight orders

Wave-35 added EOD upper bound at 16:00. But:
- What happens to entries SUBMITTED at 15:57 (1 minute before EOD)? Are they auto-cancelled?
- The pending-entry 30-tick TTL is ~5min — could a fill arrive AFTER 16:00 with no symbol now in the universe?

### 5. Reconciliation drift — full reconcile cycle audit

`_reconcile_fills` runs every tick. Verify:
- Brain trade count vs broker fills count — do they match per symbol?
- Are reconciliation artifacts properly tagged so they don't pollute calibration / Kelly stats?
- What if a fill is reported by broker but never gets a `_pending_entry` clear? Does the position become a phantom?

### 6. ATR-based stop drift under low-vol bars

V8 DD2-5 closed Kelly's zero-vol Kelly bypass. Check the symmetric case in `adaptive_exits.py`:
- If ATR is near-zero, what stop distance does ExitLevels compute?
- Does the stop ever get tighter than 1 cent? Wider than 50%?

### 7. ML feature ordering / leakage

V8 DD-7 (carryover) flagged ML anti-predictivity. After wave-33's DD2-2 axis fix:
- Are training features ordered identically to inference features?
- Is there any look-ahead leakage (e.g. a feature that uses data from `iloc[-1]` AFTER the prediction is made)?
- The brain manifest persists feature_count = 79; verify the live tick computes exactly 79 features in the same order.

### 8. Day-1 production observation analysis

Per memory: 16 trades, +$69.35, 50% win. Investigate:
- Why so few trades? Was the universe filter aggressive?
- Win rate 50% — same as random; is this consistent with calibration data?
- Average trade PnL = $4.33 → very small edge. Is this the expected steady-state, or sub-optimal?

(Read-only: pull `organism_brain/trade_history.csv`, examine the 16 rows.)

### 9. Mean-reversion engine status

Per memory: "Mean-reversion engine added as alternative; promotion gated on shadow data."
- Is MR running in shadow today?
- How does shadow MR's predicted PnL compare to alpha+breakout?
- What's the promotion gate criterion?

### 10. Fitness gate vs shadow telemetry

Per memory: "Fitness gate: Learning=no gate (soft ranking). Production=0.45 for symbols with 10+ trades."
- For each symbol with ≥10 trades, what's the current fitness?
- Are any below 0.45? Are they being soft-ranked-down or hard-blocked?

## Output

`artifacts/audit/v9_reports/track_dd3_strategy_logic_phase3.md` with findings table per subsystem, source-file:line citations, behavioral test descriptions, severity breakdown.

Quality bar: 3-7 findings. End with one-paragraph TL;DR.
