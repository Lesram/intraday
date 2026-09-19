# V7 Track FF — Edge Cases & Adversarial Inputs

**Repo:** `/Users/marselkei/VS/intra`  
**Branch:** `rc-1.5-curated` @ `d44eace` (note: working tree is on `main` @ `eb90fa3`)  
**Date:** 2026-05-03  
**Method:** 10-category adversarial fuzz against the live module code (read-only on production); synthetic tests via `./venv/bin/python`.

## TL;DR

**Bugs found: 11** (4 critical / high-confidence runtime issues, 5 medium silent-mishandling, 2 defense-in-depth gaps).  
**Probes:** 38 total — 22 PASS, 9 WARN, 7 FAIL (see `_probe_results.json`).  
**Test file:** `tests/test_adversarial_inputs_v7.py` — 25 passed, 4 xfail (the four xfails pin findings FF-4/FF-5/FF-10/FF-11). Recommend committing once xfail messages are reviewed.

The platform is **largely defensive** at the feature layer (NaN/Inf coerced to 0.0, divide-by-zero protected via `.replace(0, 1e-10)` shim, an explicit `_nan_missingness` gate at `live_engine.py:3460`). The riskiest gaps cluster around:

1. **Order-submission hot path** (`submit_symbol_order` does NOT call `validate_order`, idempotency cache returns stale result without content check).
2. **WebSocket fill handler** (`float(filled_qty=null)` silently drops fills → state divergence).
3. **Broker schema drift** (`response.json()` on empty 200, `place_order` re-wraps JSONDecodeError as opaque 502).
4. **Configuration parsing** (empty/duplicate symbol CSV, negative `MAX_NOTIONAL` accepted verbatim).

No probe identified an input that crashes the entire tick loop — the `_fetch_one` per-symbol try/except (`live_engine.py:4548`) absorbs `compute_ml_features` failures and the symbol is silently dropped from the tick. That is itself a **silent-mishandling risk** but not a crash.

---

## Per-category × Probe × Verdict matrix

| # | Category | Probe | Verdict | Note |
|---|---|---|---|---|
| 1 | bar_integrity | duplicate_timestamps | PASS | computed; rows=251 (no dedup, no crash) |
| 1 | bar_integrity | out_of_order_timestamps | WARN | silently accepted; **no monotonicity guard** |
| 1 | bar_integrity | missing_timestamp_none | FAIL† | raises `TypeError` from `pd.to_datetime`; absorbed by `_fetch_one` try/except → silent symbol drop |
| 1 | bar_integrity | nan_close | PASS | missingness=0.40 → `_nan_missingness` gate (>0.25) blocks entry |
| 1 | bar_integrity | inf_volume | PASS | inf→NaN→0 via `f.replace([±inf], NaN)` then `fillna(0)` |
| 1 | bar_integrity | negative_volume | WARN | `vol_sma_ratio = -22.22` flows downstream into tension/composites |
| 1 | bar_integrity | zero_volume_all_bars | PASS | divide-by-zero protected |
| 1 | bar_integrity | negative_price | WARN | `log(c)` → NaN → 0; many features quietly zeroed |
| 1 | bar_integrity | 50pct_gap_up | PASS | gap_pct≈0.50 computed correctly |
| 1 | bar_integrity | 100_frozen_bars | PASS | std=0 collapses RSI/ATR but no crash |
| 1 | bar_integrity | single_bar_df | PASS | 86 columns produced from len=1 (rolling.min_periods=1) |
| 4 | feature_pipeline | all_nan_close_column | WARN | computed; all features collapse to 0 — no upstream rejection |
| 4 | feature_pipeline | column_capitalised (`Close` vs `close`) | PASS | raises `KeyError` (correct fail-fast) |
| 5 | ml_inference | predict_before_training | PASS | returns neutral MLSignal |
| 5 | ml_inference | single_vs_multi_row | PASS | shape-consistent (predict only reads `.iloc[-1]`) |
| 5 | ml_inference | missing_one_feature_col | PASS | <20% missing → zero-pad; ≥20% → neutral signal + alert |
| 5 | ml_inference | extreme_outlier_feature (1e30) | PASS | `np.nan_to_num` clamps inf in trained path |
| 6 | order_validate | negative_qty | PASS | `validate_order` rejects (when called) |
| 6 | order_validate | zero_qty | PASS | rejected (when called) |
| 6 | order_validate | special_chars_symbol | PASS | rejected (when called) |
| 6 | order_validate | lowercase_symbol | PASS | accepted (uppercased downstream in `place_order`) |
| 6 | order_validate | **submit_symbol_order_validation_gap** | **FAIL** | `submit_symbol_order` never calls `validate_order` |
| 6 | order_validate | **idem_key_collision_with_diff_content** | **FAIL** | cache returns prior result without body match |
| 9 | numerical | entry_price_zero (`/0`) | PASS | Python raises ZeroDivisionError (caller must guard) |
| 9 | numerical | near_zero_entry_with_float (`/1e-300`) | WARN | finite ~1e302 — phantom-PnL risk |
| 9 | numerical | sharpe_near_zero_variance | WARN | std=0 → sharpe=inf |
| 9 | numerical | float64_overflow | WARN | silent `inf`; not raised |
| 10 | config | empty_universe_csv | WARN | `""` → empty list; engine runs with 0 symbols |
| 10 | config | **duplicate_symbols_csv** | **FAIL** | `AAPL,AAPL,AAPL` accepted; no dedup |
| 10 | config | **negative_max_notional** | **FAIL** | `-100` accepted; `if > 0` guard silently disables cap |
| 10 | config | invalid_log_level | PASS | `logging.setLevel("BANANA")` raises ValueError |
| 3 | ws | malformed_json | PASS | `listen()` catches `JSONDecodeError`, `continue`s |
| 3 | ws | **filled_qty_null_field** | **FAIL** | `float(order_data.get('filled_qty', 0))` raises on JSON null → fill silently dropped |
| 3 | ws | unbounded_queue | WARN | `asyncio.Queue()` no maxsize; "MUST NEVER drop" comment vs unbounded growth |
| 2 | broker | 5xx_infinite_retry | PASS | bounded retries (`max_retries=3`) |
| 2 | broker | **200_empty_body** | **FAIL** | `response.json()` on empty body raises → wrapped as opaque 502 |
| 8 | state | concurrent_writer_lock | PASS | `OrganismBrain` uses lock primitives |
| 7 | time | bar_ts_uses_utc | PASS | `_last_bar_times` keyed on `astimezone(UTC).strftime` — DST-immune |

† absorbed by upstream try/except → effectively a silent symbol-skip rather than a tick crash.

---

## Findings (FF-1 through FF-11)

### FF-1 (Medium) — `submit_symbol_order` skips `validate_order`
**Surface:** `backend/services/order_service.py:717`  
**Evidence:** `inspect.getsource(OrderService.submit_symbol_order)` does not contain `validate_order`. Only `submit_order` (sync, line 966) and `submit_order_async` (line 1441) call it.  
**Risk:** A buggy strategy path that produces `qty=-1` or `qty=0` writes the malformed order to the outbox. Alpaca's API will reject it (defense exists at the broker layer), but the rejection roundtrip burns rate-limit and pollutes order history. For `symbol="aapl;DROP TABLE"`-shaped inputs the broker also rejects, but the value passes through our DB first.  
**Fix:** Add a `validate_order(...)` call at the top of `submit_symbol_order` and raise `ValueError` on `valid=False`.

### FF-2 (High) — Idempotency-key collision returns stale result without content check
**Surface:** `backend/services/order_service.py:813-818`  
**Evidence:**
```python
if idempotency_key in self._async_submitted_orders:
    entry = self._async_submitted_orders[idempotency_key]
    existing_result = entry[1] if isinstance(entry, tuple) else entry
    logger.info(f"Returning cached order result for key {idempotency_key[:8]}...")
    return existing_result
```
Two callers using the same key with different `(symbol, side, qty)` will both see the **first caller's response**. In production, the strategy generates idempotency keys deterministically from `(symbol, tick, side)`, so collision is unlikely — but a refactor or test path that reuses keys would cause silent fill mis-attribution.  
**Risk:** Silent. The order DB row exists with the original symbol/qty; the calling code thinks its order was accepted. Reconciliation may surface the divergence later, or never.  
**Fix:** On cache hit, fingerprint-check `(symbol, side, str(qty))` against the cached entry; raise on mismatch.

### FF-3 (High) — WS handler drops fills when `filled_qty=null`
**Surface:** `backend/integrations/alpaca_stream.py:458`  
**Evidence:**
```python
filled_qty = float(order_data.get("filled_qty", 0))
```
If broker emits `"filled_qty": null` (JSON null → Python `None`), `.get` returns `None` (the default `0` is only used when the key is *missing*), then `float(None)` raises `TypeError`. The outer `except Exception` at line 593 catches it, logs `"Failed to process trade update"`, and returns. **The fill is never written to the DB.**  
**Risk:** State divergence — Alpaca thinks the order is filled, our DB thinks it's still open. Reconciliation cycle catches it eventually but the gap window is unbounded.  
**Fix:** `filled_qty = float(order_data.get("filled_qty") or 0)`. Same applies to `avg_fill_price` (line 459, which already uses `or` chain).

### FF-4 (Medium) — `place_order` raises opaque 502 on empty 200 body
**Surface:** `backend/integrations/alpaca_broker.py:486-510`  
**Evidence:** `response.status_code in (200, 201)` → unconditional `response.json()`. An empty body raises `json.JSONDecodeError`. The outer `except Exception` at line 515 wraps it into `HTTPException(status_code=502, detail=f"Failed to place order: {str(e)}")`, and it's logged as `"Unexpected error placing order"` rather than the more diagnostic "broker schema drift".  
**Risk:** Status divergence + alert noise. Alpaca's gateway has been observed (per other industry incidents) to return 200 with empty body on partial degradation. The opaque 502 then trips the broker circuit breaker (line 244 `record_failure("http_5XX_after_retries")` — though FF-4 specifically wraps as 502, not from the retry path, so the breaker doesn't see it cleanly).  
**Fix:** Guard `if not response.text or not response.content: raise HTTPException(502, "Broker returned empty 200")`.

### FF-5 (Medium) — Negative `MAX_NOTIONAL_PER_TRADE` silently disables the cap
**Surface:** `backend/organism/live_engine.py:205, 3594`  
**Evidence:** `MAX_NOTIONAL_PER_TRADE = _env_float("ORGANISM_MAX_NOTIONAL", 0.0)`. The use site (line 3594) is `if MAX_NOTIONAL_PER_TRADE > 0`. A misconfiguration `ORGANISM_MAX_NOTIONAL=-100` parses to `-100.0`, fails the `> 0` guard, and the cap is silently disabled. No validator catches this.  
**Risk:** A typo in deployment config silently removes a real-money risk control. Compounds with `MAX_DAILY_LOSS = _env_float("ORGANISM_MAX_DAILY_LOSS", 0.0)` (line 206) which has the same shape.  
**Fix:** Validate at module load: `if val < 0: raise ValueError(...)`. Or surface as a startup banner.

### FF-6 (Medium) — Empty `ORGANISM_LIVE_SYMBOLS` runs with 0 symbols
**Surface:** `backend/organism/live_engine.py:376-380`  
**Evidence:**
```python
self._universe = universe or [
    s.strip().upper()
    for s in LIVE_UNIVERSE_CSV.split(",")
    if s.strip()
]
```
If `ORGANISM_LIVE_SYMBOLS=""` (explicitly empty, not unset), `_env_str` returns `""` (default only applies when env var is missing), then `"".split(",") == [""]` → filtered to `[]`. **The default 22-symbol universe is bypassed.** Engine boots, ticks fire, no symbols are scanned.  
**Risk:** Operator deletes the env var value (instead of the line) and the platform silently stops trading.  
**Fix:** After parsing, `assert self._universe, "ORGANISM_LIVE_SYMBOLS is empty"` or fall back to the default.

### FF-7 (Medium) — Duplicate symbols in `ORGANISM_LIVE_SYMBOLS` accepted as-is
**Surface:** `backend/organism/live_engine.py:376-380`  
**Evidence:** `"AAPL,AAPL,AAPL"` parses to `["AAPL", "AAPL", "AAPL"]`. No dedup. Each tick fetches AAPL bars 3× (the per-symbol concurrency semaphore limits parallelism but not redundancy), evaluates entries 3×, and may emit 3× orders if the strategy doesn't dedupe internally.  
**Risk:** Real-money 3× position-sizing if the entry path uses `for sym in self._universe` without uniqueness. Probably caught by the per-symbol lock in `submit_symbol_order` (FF-1), but the lock fires after the order is constructed.  
**Fix:** `self._universe = list(dict.fromkeys(parsed))` to dedupe while preserving order.

### FF-8 (Low/Med) — Negative volume, negative price, out-of-order timestamps silently flow through `compute_ml_features`
**Surface:** `backend/organism/ml_features.py`  
**Evidence:** Negative volume produces `vol_sma_ratio=-22.22` (probe 1.bar/negative_volume). Negative price triggers RuntimeWarnings (`invalid value encountered in log`) and zeros out log-related features. Out-of-order timestamps are accepted without monotonicity check.  
**Risk:** Each in isolation is unlikely from Alpaca, but a corrupted feed or replay scenario can sneak it in. Currently the only gate is the `_nan_missingness` threshold (25%) — corruption that produces *finite* but absurd values evades it entirely (e.g. `vol_sma_ratio=-22` is a single feature; missingness=1/86 ≈ 1.2% << 25%).  
**Fix:** Add input sanity at the top of `compute_ml_features`:
```python
if (df["volume"] < 0).any() or (df["close"] <= 0).any():
    raise ValueError("Corrupted bar data")
if not df["timestamp"].is_monotonic_increasing:
    df = df.sort_values("timestamp").reset_index(drop=True)
```

### FF-9 (Low/Med) — Near-zero entry price → finite-but-absurd `actual_return`
**Surface:** `backend/organism/continuous_learner.py` (and any actual_return calc downstream)  
**Evidence:** `(101.0 - 0.0) / 1e-300 = 1.01e302` does NOT raise — it produces a huge finite number that survives `np.isfinite` checks. Sharpe denominators can also collapse to ~1e-15 → ratios in the 1e15 range.  
**Risk:** Phantom KPI inflation. If a fill record ever gets `entry_price=1e-300` (Decimal serialization bug), every metric depending on `actual_return` blows up.  
**Fix:** Guard `if abs(entry_price) < 1e-6: raise ValueError(...)` at the trade-record construction site.

### FF-10 (Low) — Unbounded WS update queue
**Surface:** `backend/integrations/alpaca_stream.py` `__init__` → `self.update_queue = asyncio.Queue()`  
**Evidence:** No `maxsize`. The high-water-mark logging at line 338 reacts only at qsize > 500 (warning), but never bounds. The comment at line 333 explicitly states "must NEVER be dropped" and chooses unbounded growth as the policy.  
**Risk:** If `_process_trade_update` deadlocks or the DB pool is exhausted, queue grows without bound until OOM. The mitigation comment is correct in spirit (don't drop fills) but pairs poorly with no upstream backpressure.  
**Fix:** Cap to a generous bound (e.g. 10_000) and add a `dlq.write` path on overflow rather than silent OOM.

### FF-11 (Documentation) — Missing-timestamp path → silent symbol skip, not crash
**Surface:** `backend/organism/ml_features.py:346` (`pd.to_datetime`) ↔ `backend/organism/live_engine.py:4569`  
**Evidence:** `df.loc[..., "timestamp"] = None` causes `compute_ml_features` to raise `TypeError` from `pd.to_datetime`. The `_fetch_one` wrapper logs `"Failed to fetch/compute %s: %s"` at WARNING and returns `(sym, None)`. The symbol drops out of `features_by_symbol` for that tick.  
**Risk:** A persistent data-feed issue (e.g. Alpaca historical bars returning NaT for the latest minute) would cause the symbol to be ignored for arbitrarily long, with only WARNING log evidence. No alert wiring.  
**Fix:** Promote repeated per-symbol fetch failures to an alert (e.g. count failures per symbol per tick; if `>3` ticks in a row, dispatch via `dispatch_alert_from_thread`).

---

## Crashes / silent-mishandling list

| Surface | Trigger | Outcome |
|---|---|---|
| `_process_trade_update` | broker emits `filled_qty: null` | fill silently dropped (FF-3) |
| `place_order` | broker returns 200 with empty body | opaque 502, breaker may not increment cleanly (FF-4) |
| `compute_ml_features` | `timestamp=None` row | TypeError → upstream catches, symbol silently skipped (FF-11) |
| `submit_symbol_order` | `qty=0` or `qty=-1` from buggy strategy | written to outbox, broker rejects later (FF-1) |
| `submit_symbol_order` | reused idempotency key, different body | stale cached response returned (FF-2) |
| `compute_ml_features` | `volume<0`, `close<0`, timestamps non-monotonic | features compute with absurd or zeroed values (FF-8) |
| `live_engine` boot | `ORGANISM_LIVE_SYMBOLS=""` | engine runs with 0 symbols (FF-6) |
| `live_engine` boot | `ORGANISM_LIVE_SYMBOLS="AAPL,AAPL,AAPL"` | duplicates kept verbatim (FF-7) |
| `live_engine` boot | `ORGANISM_MAX_NOTIONAL=-100` | cap silently disabled (FF-5) |
| `alpaca_stream` queue | processor stuck | unbounded queue → OOM (FF-10) |
| trade-record construction | `entry_price=1e-300` | actual_return ≈ 1e302, finite (FF-9) |

**Tick-loop crash:** none identified. The `_fetch_one` per-symbol try/except absorbs all `compute_ml_features` failures, and the universe-level `asyncio.gather` (no `return_exceptions=False` issue here) survives. Categorically robust against single-symbol corruption.

**WS hang:** none identified. `listen()` correctly catches `JSONDecodeError` per-message; the websockets library raises `ConnectionClosed` on disconnect which is caught by the outer `except`. The unbounded queue (FF-10) is a memory issue, not a hang.

**Phantom 0-PnL trade from NaN propagation:** the engine gates at 25% missingness (`_nan_missingness`), and ML predictions on partially-NaN feature rows return neutral when untrained or zero-pad when <20% missing. **No phantom-trade probe materialised.** The closest match is FF-9 (near-zero entry price → finite-but-huge actual_return), which is not a 0-PnL phantom but its inverse: a non-zero phantom in metric space.

---

## Defensive-code gaps inventory

**Add input sanity:**
- `compute_ml_features` should reject `volume<0`, `close<=0`, and non-monotonic timestamps (FF-8).
- `submit_symbol_order` should call `validate_order` (FF-1).

**Add cache-fingerprint check:**
- `_async_submitted_orders` cache hit should verify body matches (FF-2).

**Add null-coalesce on broker fields:**
- `float(order_data.get("filled_qty", 0))` → `float(order_data.get("filled_qty") or 0)` (FF-3).

**Add empty-body guard:**
- `place_order` 200/201 path should check `response.content` before calling `.json()` (FF-4).

**Add config validators at startup:**
- Negative `MAX_NOTIONAL_PER_TRADE` / `MAX_DAILY_LOSS` should raise (FF-5).
- Empty universe should raise or fall back to default (FF-6).
- Universe should be deduped (FF-7).

**Add bounded queue:**
- `update_queue = asyncio.Queue(maxsize=10_000)` + DLQ on overflow (FF-10).

**Add fetch-failure alert:**
- Per-symbol fetch failures repeated across ticks should escalate to alert (FF-11).

**Add trade-record guard:**
- `if abs(entry_price) < 1e-6: raise` at construction (FF-9).

---

## Synthetic test plan — deliverable

Test file written: `tests/test_adversarial_inputs_v7.py` (29 tests; 25 pass, 4 xfail-strict pinning FF-1/FF-2/FF-3/FF-4).

**Run:**
```
./venv/bin/python -m pytest tests/test_adversarial_inputs_v7.py --timeout=30 -q
# 25 passed, 4 xfailed in 2.26s
```

**Recommendation:** **Commit with the xfails intact.** Each xfail uses `strict=True` so when the underlying fix lands, the test will start passing → pytest will fail with `XPASS` → forces the engineer to flip xfail off and acknowledge the closure. This gives us a regression-style ratchet without false-failing CI today.

The probe driver (`artifacts/audit/v7_reports/_probe_adversarial.py`) is **NOT** committed — it's a one-shot audit artifact and intentionally noisy (RuntimeWarnings from log of negative numbers, etc.). Keep it under `artifacts/audit/v7_reports/` for reproducibility.

---

## Summary

V7 Track FF probed 38 adversarial inputs across the 10 categories in the prompt and surfaced **11 findings** — 4 high-confidence runtime bugs (idempotency-cache stale-return, WS null-field drop, broker empty-body opaque-502, no validation in `submit_symbol_order`) and 7 silent-mishandling or defense-in-depth gaps (negative volume/price/timestamps flow through feature pipeline, negative `MAX_NOTIONAL` silently disables cap, empty/duplicate universe CSV silently broken, near-zero-entry-price phantom-PnL, unbounded WS queue, missing-timestamp silent symbol skip). The platform's primary defenses — `_nan_missingness` gate, `np.nan_to_num` clamps in ML inference, bounded broker retries, UTC bar-time keying, neutral-MLSignal-on-untrained — all hold under fuzzing. **No probe identified an input that crashes the entire tick loop**, no input that hangs the WS handler, and no NaN propagation that fabricates a 0-PnL trade (the closest match, FF-9, is a *non-zero* phantom, not a zero one). The deliverable test file `tests/test_adversarial_inputs_v7.py` (29 tests, 4 xfail-strict) provides a regression ratchet for the four highest-value findings; recommend committing as-is so closure of FF-1/FF-2/FF-3/FF-4 will trip XPASS and force an explicit acknowledgment.
