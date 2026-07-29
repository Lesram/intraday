# Track X v6 — Backtesting Reliability Audit

V5 Track U found 8 replay-vs-live divergence bypass sites and revealed that
`_now_fn` injection only patched OrganismLiveEngine while RegimeDetector,
GovernanceController, PromotionController, ContinuousLearner all bypassed.
Wave 17b/19 extended the injection chain. Track X verifies the *result*:
with all clock injection in place, does replay produce deterministic,
reproducible output that matches a live-with-injected-clock execution?

This is the systematic divergence test V5 synthesis proposed.

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `3f660f4`.

## Files in scope

- `backend/organism/replay_simulator.py`
- `backend/organism/live_engine.py`
- All auxiliary components patched in waves 17b/19 (regime, governance, promotion, continuous_learner, streaming_data_provider)

## Method

### 1. Determinism test

Pick one canonical bar set:
- A small slice of historical 1-min bars for a single symbol (e.g. SPY,
  2024-01-15 09:30-10:00 ET, 30 bars). Use Alpaca historical fetch or a
  synthetic generated set committed to `tests/fixtures/`.

Run replay twice:
1. `replay_simulator.run_replay(bars, seed=42)` → snapshot final state
2. `replay_simulator.run_replay(bars, seed=42)` again → snapshot final state

Diff every field of the final state:
- `_total_orders_submitted`
- `_cumulative_pnl` (in learner.state)
- `_equity_curve` (last entry)
- `_pending_entry`, `_pending_entry_order_ids`, `_entry_metadata`
- `regime_detector._last_state` (post-V5 U-3 fix should be deterministic)
- `governance.snapshot()` (post-V5 U-4 fix)
- `_all_trades`

If any field differs across the two runs → non-determinism. Document
the exact field and which random source is responsible.

### 2. Replay-vs-live trace

Pick the same bar set. Drive the live engine with `_now_fn` injected
to advance per bar. Compare every internal state at every tick to the
replay output.

Differences fall into:
- **Acceptable**: external state that replay correctly stubs (broker
  account, DB sessions, streaming provider). Document.
- **Bug**: divergence in decision-relevant state. File as finding.

Tools: extend `replay_simulator` with a "trace" mode that logs every
tick's intermediate state. Run live + replay; diff the traces.

### 3. Stress: replay over a known-historical day

Run replay over an entire trading day (e.g. 2024-01-15, 09:30-16:00,
~390 bars × ~22 symbols). Capture:
- Total trades made
- Cumulative PnL
- Generation count (should not advance — replay shouldn't trigger evolution)
- Brain manifest delta (should be empty in replay-only mode)

If replay touches the brain (writes to `organism_brain/`), that's a bug.
Replay must be side-effect-free on production state.

### 4. Idempotency of replay

Run replay over the same bar set with `seed=42` from clean state.
Capture the trade list. Now run again starting from the *output* of the
first run (i.e. the replay engine has a learner with prior trades).
Does it produce the same trades on the same bars?

It shouldn't necessarily — the learner state is different. But the
*decision logic* should be deterministic given the input state. This
test pins the determinism boundary: state-given → output is
deterministic; state-different → output may differ.

### 5. Replay write-side audit

Find every place replay could mutate persistent state:
- Does `replay_simulator` write to `organism_brain/`?
- Does it write to the DB (orders, position_lots, realized_trades, outbox)?
- Does it call any external API?

Replay should NOT do any of these. List any sites that do.

### 6. Replay test fixtures

Write `tests/fixtures/replay_canonical_bars_*.csv` (or similar) — a
small committed bar set the determinism test depends on. Future audits
re-run on this fixture to detect determinism regressions.

### 7. CI integration proposal

End with a concrete proposal for adding the determinism test to CI:
- Test runs on every PR
- Compares deterministic-replay output to a committed golden snapshot
- Updates the snapshot only on intentional change (with reviewer sign-off)

## Output

`artifacts/audit/v6_reports/track_x_backtesting_reliability.md` with:
- Determinism test results (fields × diff)
- Replay-vs-live trace diff
- Day-long replay outcome (trades, PnL, brain delta)
- Idempotency boundary table
- Replay write-side audit
- "Determinism violations: N" + TL;DR

## Constraints

Read-only on production. Synthetic replay via `./venv/bin/python` /
`replay_simulator.py` ok. NO writes to `organism_brain/` or DB.

## Quality bar

Expect 2-5 issues:
- Subtle non-determinism (RNG seed not propagated, dict iteration order)
- A replay write-side that should be stubbed
- A divergence between live + replay paths

End with a one-paragraph summary.
