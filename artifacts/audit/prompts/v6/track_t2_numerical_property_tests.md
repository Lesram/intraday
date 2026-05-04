# Track T2 v6 — Property-Based Numerical Tests

V5 Track T found 6 numerical bugs (Decimal/float boundaries, cumulative-counter
drift, Sharpe pathology, Kelly saturation). Wave 17d/18/19 fixed them. Track T2
formalizes those invariants as property-based tests so a regression fails CI.

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `3f660f4`.

## Files in scope

- `backend/organism/continuous_learner.py` — cumulative_pnl accumulator
- `backend/organism/brain_persistence.py` — CSV pnl writes
- `backend/organism/walk_forward.py` — Sharpe calc
- `backend/organism/kelly_sizer.py` — Kelly fraction, atr_var floor
- `backend/services/lot_tracker_service.py` — Decimal lot math
- `backend/organism/regime.py` — Sharpe inputs

## Method

### 1. Identify the invariants

For each fix in V5 wave 17-19, write the invariant the fix establishes:

- **B-T-2 invariant**: `round(sum(t.pnl for t in CSV), 2) == round(state.cumulative_pnl, 2)` after a roundtrip.
- **B-T-5 invariant**: `Sharpe(daily_pnls)` returns 0.0 when `len(daily_pnls) <= 1` OR `std < 1e-8`. Never synthesizes a number.
- **B-T-7 invariant**: `Kelly(predicted_return, atr_pct=0.0, ...)` returns 0 size for the signal contribution. Never saturates.
- **B-T-1 invariant**: DB-replayed trade has direction = ±1 matching the entry order's side. Never hard-coded 1.
- **B-T-3 invariant**: `_safe_int_qty(0.5)` warns and returns 0; `_safe_int_qty(10.0)` returns 10 silently.

### 2. Property-based test files

Write `tests/test_numerical_properties_v6.py` containing:

- `test_cumulative_pnl_roundtrip`: generate N random trades, save via
  `_save_trade_history`, reload via `_load_trade_history`, assert reconciled
  cumulative_pnl matches saved cumulative_pnl within $0.10 tolerance for
  legacy + within $0.001 for new (6dp) writes.
- `test_sharpe_under_determined_returns_zero`:
  `WalkForwardEvaluator._compute_metrics` with `daily_pnls=[]`, `[5.0]`,
  `[5.0, 5.0]` (zero variance), `[5.0, 5.0001]` (variance below 1e-8) all
  return Sharpe=0.0.
- `test_kelly_zero_atr_returns_zero_signal`:
  `kelly_sizer.size_orders` with a candidate whose `atr_pct=0.0` returns
  0 shares. Re-test for `atr_pct=1e-9` (below floor).
- `test_db_replay_direction_buy_vs_sell`: fake entry order with
  `side="buy"` → reconstructed trade has direction=+1. With `side="sell"`
  → direction=-1. With missing side → direction=+1 (legacy LONG_ONLY-safe).
- `test_safe_int_qty_warns_on_fractional`: assert the warn fires for
  fractional inputs and is silent for whole-number inputs.

### 3. Regression-test gap analysis

For every numerical-related fix in waves 1-19, identify which currently
have property-based tests and which have only:
- structural tests (assert source contains a string)
- example-based tests (one fixed input/output)
- no test at all

Surface the gap.

### 4. Hypothesis library audit

If `hypothesis` (the property-based testing framework) is available, propose
upgrading the example-based tests to genuinely property-based with random
inputs. List which tests would benefit.

If hypothesis is not in `requirements*.txt`, just structure the tests
example-based (fixed inputs covering edge cases) with a comment indicating
the property they validate.

### 5. Numerical regression matrix

Build a table:

| Invariant | Source fix | Test type | Test file:test_name | Pass? |
|---|---|---|---|---|
| cumulative_pnl roundtrip | B-T-2 / 17d | example | tests/test_numerical_properties_v6.py::test_cumulative_pnl_roundtrip | ✓ |
| Sharpe under-determined | B-T-5 / 19 | example | ... | ✓ |
| Kelly zero atr | B-T-7 / 18 | example | ... | ✓ |
| DB-replay direction | B-T-1 / 18 | example | ... | ✓ |
| _safe_int_qty fractional warn | B-T-3 / 18 | example | ... | ✓ |

The table is the deliverable for this track.

### 6. Run the new tests

`./venv/bin/python -m pytest tests/test_numerical_properties_v6.py -v`
should pass on the current HEAD. The audit's deliverable is both the test
file (committed) AND a passing run.

## Output

`artifacts/audit/v6_reports/track_t2_numerical_property_tests.md` with:
- Numerical regression matrix
- Gap analysis (existing tests by category)
- New test file path + pass/fail summary
- Any new bugs surfaced while writing the tests
- "Bugs found while writing T2 tests: N" + TL;DR

## Constraints

Read-only on production code. **WRITE the new test file** to
`tests/test_numerical_properties_v6.py` — that's the deliverable.

## Quality bar

Expect 0-2 new bugs surfaced while writing the tests. If 3+, that's a
material issue with the wave-17/18/19 fixes themselves.

End with a one-paragraph summary.
