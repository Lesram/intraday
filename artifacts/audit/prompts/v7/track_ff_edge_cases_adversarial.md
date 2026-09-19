# Track FF v7 — Edge Cases & Adversarial Inputs (NEW SURFACE)

How does the system behave when given malformed, adversarial, or
extreme inputs? Property-based / fuzz-style audit of input boundaries.

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `d44eace`.

## Method

For each input boundary, enumerate adversarial cases and verify the
system's response.

### 1. Bar data integrity

- **Duplicate timestamps**: two bars with identical timestamp (broker
  bug / data feed glitch). Does the engine dedup? Crash?
- **Out-of-order timestamps**: bar N+1 has earlier timestamp than bar N.
- **Missing timestamps**: bar with `timestamp=None` or empty string.
- **NaN / Inf in OHLCV**: `close=NaN`, `volume=Inf`, etc. Does feature
  pipeline propagate NaN, raise, or default?
- **Negative volume**: corrupted bar.
- **Zero volume**: thin / illiquid bar.
- **Negative price**: extremely corrupted.
- **Extreme price moves**: 50% gap up/down on next bar (real event:
  earnings, halt-and-resume).
- **Wide spread**: bid=0.01, ask=1000 (broken quote).
- **Frozen bar**: 100 consecutive bars with identical OHLCV (data feed
  stuck).

For each: what does `feature_engineering.py` produce? What does the
gate / sizer / ML signal do?

### 2. Adversarial broker responses

`alpaca_broker.py` and `alpaca_stream.py`:
- Malformed JSON (truncated, invalid UTF-8).
- Status 200 with empty body.
- Status 429 with no `Retry-After` header.
- Status 500 forever (infinite retry?).
- Status 200 but with wrong schema (e.g. `filled_qty=None` when
  expected number).
- Order ID format change (broker upgrades and Alpaca's UUID becomes 36
  chars instead of 32).
- Position payload with extra fields the parser doesn't expect.

### 3. WS adversarial

Alpaca WS:
- Message with invalid JSON.
- Message with valid JSON but wrong schema.
- Message with timestamp far in the future / past.
- Message with `order_id` that we have no record of.
- Burst: 1000 messages in 1 second.
- Disconnect mid-message.

### 4. Feature pipeline edge cases

`ml_features.py`:
- DataFrame with all-NaN column.
- DataFrame with one bar (insufficient lookback).
- Symbol with no trade history.
- Mid-pipeline column rename (e.g. `close` becomes `Close` capitalized).
- Symbol that changed underlying instrument (ticker reused for new
  company).

### 5. ML inference edge cases

`ml_signal.py`:
- Predict on a single feature row vs many — consistent outputs?
- Predict with one missing feature column — graceful?
- Predict with a feature value far outside training distribution (extreme
  outlier).
- Predict before any training has happened — returns neutral / refuses?
- Predict during retrain (race between read and write of `_clf`).

### 6. Order submission adversarial

`order_service.submit_symbol_order`:
- Negative `qty`: rejected at validation? Or sent to broker?
- `qty=0`: rejected?
- Very large `qty` (e.g. 1M shares): broker rate-limit triggered?
- Invalid `symbol` (lowercase, special characters): handled?
- `idempotency_key` collision (same key, different content): returns
  cached result?
- `idempotency_key` collision (same key, same content): no double-submit?

### 7. Time / scheduling adversarial

- Tick fires during DST transition (clocks jump forward 1 hour or back
  1 hour). What happens to `_last_bar_times`?
- Container clock skew (NTP off by 30s). Bar staleness check behavior?
- Holiday day: market closed but cron tick fires?
- Pre-market vs RTH boundary: 09:29:59 → 09:30:00 transition.
- 16:00:00.500: between EOD flatten and tick close.

### 8. State persistence adversarial

- Brain save mid-tick: tick state captured but tick continues; manifest
  may say "saved" but in-memory state continues advancing. Read-after-
  write consistency?
- `trade_history.csv` with duplicate row (race between two writers)?
- Concurrent process writes to `organism_brain/` (e.g. shadow scanner +
  live engine sharing volume): file lock semantics?

### 9. Numerical adversarial

- Cumulative P&L approaches float64 limit (extreme over months).
- Single trade with PnL = inf (zero-division somewhere)?
- Trade with NaN actual_return (entry_price=0)?
- Sharpe denominator = 1e-15 (near-zero variance)?

### 10. Configuration adversarial

- `LOG_LEVEL=BANANA` (invalid)?
- `MAX_NOTIONAL_PER_TRADE=-100` (negative)?
- `ORGANISM_LIVE_SYMBOLS=` (empty)?
- `ORGANISM_LIVE_SYMBOLS=AAPL,AAPL,AAPL` (duplicates)?

## Synthetic test plan

For each numbered category, write 1-3 small probe tests. Probes can be:
- Pure pytest (file-only) for cases that don't require running services.
- Synthetic replay scenarios for tick-loop cases.
- Unit-level tests against the relevant module.

Deliverable: a test file `tests/test_adversarial_inputs_v7.py` (don't
commit unless probes are clean enough — discuss in the report).

## Output

`artifacts/audit/v7_reports/track_ff_edge_cases_adversarial.md` with:
- Per-category × probe × verdict matrix
- Crashes / silent-mishandling list
- Defensive-code gaps inventory
- "Bugs found: N" + TL;DR

## Constraints

Read-only on production. Synthetic tests via `./venv/bin/python` ok.

## Quality bar

Expect 4-10 findings. Especially:
- An input that crashes the tick loop instead of being skipped.
- A NaN propagation that produces a 0-PnL phantom trade.
- A broker malformed-JSON case that hangs the WS handler.

End with a one-paragraph summary.
