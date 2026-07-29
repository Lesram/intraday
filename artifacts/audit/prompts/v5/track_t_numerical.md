# Track T v5 — Numerical / Floating-Point Audit

Audit the platform's numerical layer: Decimal vs float boundaries,
cumulative-counter drift, ATR / Sharpe / Kelly numerical stability,
calibration math, bar-timestamp arithmetic. The platform mixes Decimal
(orders, lots, broker payloads) and float (live_engine, ML, returns
math); the boundary is a rich source of subtle bugs.

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `d43dbec`.

## Files in scope

- Anywhere `Decimal` and `float` meet:
  - `backend/services/lot_tracker_service.py` (Decimal lot math)
  - `backend/services/order_service.py` (Decimal qty / price)
  - `backend/integrations/alpaca_*.py` (broker payload types)
  - `backend/organism/live_engine.py` (float P&L, equity, ATR)
  - `backend/organism/kelly_sizer.py` (float Kelly fraction)
  - `backend/organism/adaptive_exits.py` (float ATR / stop math)
  - `backend/organism/regime.py` (float Sharpe)
  - `backend/organism/continuous_learner.py` (float P&L accumulation)
  - `backend/organism/ml_signal.py`, `ml_features.py`, `ensemble_models.py`
  - `backend/organism/replay_simulator.py` (float for backtest realism)

## Method

### 1. Decimal/float boundary audit

For every `float(some_decimal)` and `Decimal(str(some_float))` cast in scope:
- Where does the boundary cross?
- What precision is lost?
- Is the rounding direction explicit or implicit?
- Can a malicious or pathological input (e.g. 0.1 + 0.2 = 0.30000000000000004)
  cross the boundary in a way that violates an invariant?

Targets:
- Cost-basis calculation in lot tracker — must match broker's view.
- Realized P&L — must match `(close - open) * qty` to the cent.
- Notional cap (`MAX_NOTIONAL_PER_TRADE`) — Decimal-safe?
- Drawdown threshold — float comparison against `_drawdown_limit`. Any
  IEEE-754 drift like the 599-vs-600 cooldown bug Audit-F-19 caught?

### 2. Cumulative-counter drift

For every accumulator running per-tick:
- `_cumulative_pnl` — incremented per closed trade. Drift over 10k+ trades?
- `_equity_curve` — capped at 100k post wave-14, but is each entry
  computed as `equity = base + sum(pnl)`, or as the broker's authoritative
  account.equity (no drift)?
- `_total_orders_submitted`, `_total_exits_submitted` — int counters,
  no drift, but verify monotonic.
- ATR rolling — multiplicative variance accumulator; can drift if
  stream-update rather than recomputed-from-bars.

### 3. Sharpe / Kelly / fitness numerical stability

Edge cases:
- All trades are 0 P&L → variance = 0 → Sharpe = ∞ or NaN. How handled?
- Single-trade window → variance = 0 → same.
- Negative variance from numerical instability → sqrt(-x) = NaN.
- Kelly fraction with `win_rate * payoff_ratio - loss_rate` going to 0 or
  negative — kelly_fraction = -inf or 0?
- Calibration log-loss with predicted prob = 0 or 1 → -log(0) = inf.

For each potential pathology, find the call site and check the guard.

### 4. ATR / volatility numerical

- `pandas_ta.atr` — verify input handling for short windows (≤3 bars).
- Normalized vs raw SMA (regime detector). V3 fixed normalization
  (test_detect_uses_raw_sma_not_normalized). Are there other normalize/
  denormalize boundaries that drift?

### 5. Bar timestamp arithmetic

- Bar boundaries: `floor(now / bar_seconds) * bar_seconds`. Off-by-one at
  boundary instants?
- Bar age comparisons: tz-aware after wave 8d. Any remaining naive
  arithmetic?
- Replay vs live: `self._now_fn()` returns float (time.time) or datetime
  (replay clock). Arithmetic across the boundary?

### 6. Returns math

- `actual_return = (exit_price - entry_price) / entry_price` — division
  by zero if entry_price == 0?
- log returns vs simple returns — any place they're added (which is wrong)?
- `predicted_return` floor = 1e-4 (post Day-1 fix); ML threshold matches?

### 7. Position quantity rounding

- Fractional shares: are they supported by the broker? If yes, every
  `int(qty)` cast is a bug.
- `int(qty)` vs `round(qty)`: rounding direction.
- Min share count: `max(1, ...)` applied AFTER notional cap. Verified
  in wave-9 H-3 fix; re-test under T's lens.

### 8. Float comparison patterns

- `if a == b:` against floats — anywhere it's an exact equality that
  should be `abs(a - b) < eps`?
- `if val > 0:` where val could be 0.0 (zero-equity check should pass).
- `if drawdown >= self._drawdown_limit:` — IEEE-754 sensitivity at
  boundary.

### 9. Random / non-deterministic sources

- `random.uniform`, `numpy.random.*`: seeded in tests? Replay determinism?
- ML training shuffle seed.
- Order idempotency_key: UUID4 — non-deterministic by design, but is
  it safe?

## Output

`artifacts/audit/v5_reports/track_t_numerical.md` with:

- Decimal/float boundary table (file:line × from-type × to-type × precision-risk)
- Cumulative-counter drift inventory
- Sharpe/Kelly/fitness pathology coverage
- ATR / volatility numerical concerns
- Bar timestamp / replay-determinism issues
- "Bugs found: N" + TL;DR

## Constraints

Read-only. `./venv/bin/python` ok for synthetic numerical tests.

## Quality bar

Expect 3-7 issues. Numerical bugs are usually subtle and hidden behind
defensive guards; the test is whether the guards cover the actual paths.

End with a one-paragraph summary.
