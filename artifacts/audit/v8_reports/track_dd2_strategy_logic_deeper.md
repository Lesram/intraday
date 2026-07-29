# Track DD2 — Strategy Logic Deeper Pass (V8)

**Branch**: `rc-1.5-curated` @ `5bc4046`
**Date**: 2026-05-02
**Method**: Read-only code audit + targeted greps. No fixes.

This pass drills into the deepest edges flagged by V7 DD: Kelly under partial fills, regime hysteresis, exit precedence under partials, ML feature staleness, confidence calibration drift, burst cap precedence, inverse ETFs, warm-start race, EOD flatten, and replay determinism.

---

## Findings

### DD2-1 — `_pending_exit` TTL silences stop-loss for ~3 ticks after partial TP / ML-reversal partial (subsystem 3)

**Severity**: HIGH
**Files**: `backend/organism/live_engine.py:2154`, `2320-2360`, `1548-1552`, `613`
**Files**: `backend/organism/adaptive_exits.py:583-613`

`AdaptiveExitEngine._check_partial_tp` returns an `ExitSignal(should_exit=True, partial_exit=True, partial_pct=0.30)` on the first partial-TP touch. In `live_engine.py:2320-2337`, the partial-exit submits an order for `int(qty * 0.30)` shares, then sets `self._exit_cooldown[sym]` AND `self._pending_exit[sym] = self._tick_count`. On the very next tick, line 2154 short-circuits exit processing entirely:

```python
if sym in self._pending_exit:
    logger.debug("Skipping exit check for %s — pending exit from tick %d", ...)
    continue
```

The pending-exit window is `self._PENDING_EXIT_TICKS = 3` (line 613). With ~10 s/tick, that is ~30 s during which **no exit logic runs**, including:
- Hard stop-loss (`adaptive_exits.py:397-400`)
- Absolute max-loss safety net (`adaptive_exits.py:391-394`)
- The pre-features safety net at `live_engine.py:2168-2186`
- The no-exit-levels safety net at `live_engine.py:2244-2287`

Therefore: a position that gets a partial TP exit at 3R (sells 30 %) and then sees a sudden adverse move can lose >> max_loss_pct on the *remaining 70 %* before any check runs. The same pattern affects ML-reversal partial exits (`live_engine.py:2308-2316`).

**Why tests miss it**: most exit tests construct one position, call `check_exit()` directly with one price tick, and observe the returned signal. They do not exercise the live-engine outer loop where `_pending_exit` blocks the call.

**Behavioral test to lock the regression**:
- Open one long position with `partial_tp_price` at +3 % and `stop_loss` at -5 %.
- Drive prices: bar N at +3 % (triggers partial TP, exit submitted, `_pending_exit[sym]` set).
- Bars N+1, N+2, N+3 at -10 % (well past stop_loss).
- Assert: `_submit_exit_order` is called for the remaining 70 % within those 3 bars. Today it is NOT.

---

### DD2-2 — `_compute_effective_confidence` and `record_prediction_outcome` use mismatched bin axes; calibration map is computed against wrong distribution (subsystem 4 + 5)

**Severity**: HIGH
**Files**: `backend/organism/ml_signal.py:474-552`, `live_engine.py:5293-5300`

Three call sites use three different "confidences":
1. `record_prediction_outcome(self, confidence, was_correct)` — `live_engine.py:5298-5300` passes `meta["confidence"]`, which is **calibrated_confidence** (`MLSignal.confidence` is set to `calibrated_confidence` at `ml_signal.py:496`). The bucket `bin_idx = min(int(confidence * 5), 4)` therefore indexes the **calibrated** axis.
2. `update_calibration_map()` — `ml_signal.py:522-535` computes `actual_rate = correct/total` per bin and stores `_calibration_map[i] = actual_rate / bin_midpoint`. The `bin_midpoint = ((i*0.2)+(i+1)*0.2)/2` is interpreted as the *expected* accuracy in that bin, but the actual data was binned by **calibrated** confidence, not the bin midpoint.
3. `calibrate_confidence(raw_confidence)` — `ml_signal.py:580-583` is called with **raw_confidence** (line 478) and uses `_calibration_map[int(raw*5)]`. So the map produced from calibrated-bin counts is consumed against raw-confidence indexing.

The result is a feedback loop: high-raw-confidence predictions get up-multiplied to high-calibrated values; outcomes are recorded in the high-calibrated bin; the multiplier for the high-raw bin is computed against bin_midpoint=0.9 rather than against the actual high-calibrated confidence's empirical precision. Over many cycles this drifts the calibration multipliers away from a meaningful identity.

In addition, `_compute_effective_confidence(calibrated_confidence)` (`ml_signal.py:537-552`) bins by **calibrated** but the lookups in `record_prediction_outcome` and `_compute_effective_confidence` use the same calibrated axis, so that pair is internally consistent. The mismatch is between `record_prediction_outcome` (calibrated bin) and `calibrate_confidence` (raw bin).

This compounds the V7 DD-7 finding (system anti-predictivity): part of the reason `corr(confidence, correct_direction) = -0.112` is that the calibration multiplier's denominator and numerator come from different distributions.

**Behavioral test to lock the regression**:
- Seed a deterministic distribution: simulate N=1000 predictions where the model emits raw_confidence in {0.1, 0.3, 0.5, 0.7, 0.9} uniformly, with hand-crafted accuracy-per-raw-bin = {0.55, 0.60, 0.65, 0.70, 0.75}.
- Run all through `predict()` → `record_prediction_outcome` → `update_calibration_map`.
- Assert that for raw_confidence=0.7, `calibrate_confidence(0.7)` returns a value whose empirical accuracy (against ground truth) matches a stable target. Today the multiplier and the bin-counts are out of axis, so the assertion will fail in either direction.

---

### DD2-3 — `RegimeDetector.detect_market_regime` and `detect_cross_asset_regime` discard churn detection by saving/restoring `_history`; the live cross-asset regime never accumulates churn (subsystem 2)

**Severity**: MEDIUM
**File**: `backend/organism/regime.py:412-469`, `478-588`

`detect()` always appends to `self._history` (line 266) and computes `churn_rate` from the last `_churn_window` entries. But `detect_market_regime()` (line 431-448) and `detect_cross_asset_regime()` (line 507-521) explicitly **save and restore** `_history` and `_smoothed_probs` around each per-symbol/per-sector `detect()` call to avoid cross-contamination:

```python
saved_probs = dict(self._smoothed_probs)
saved_history = list(self._history)
saved_last = self._last_state
try:
    for sym, feat_df in per_symbol_features.items():
        self._smoothed_probs = dict(saved_probs)
        self._history = list(saved_history)
        state = self.detect(feat_df)
        ...
finally:
    self._smoothed_probs = saved_probs
    self._history = saved_history
    self._last_state = saved_last
```

After `detect_market_regime()` returns, `_history` is identical to before the call, so the actually-used market regime is never appended to history. The returned `RegimeState.churn_rate` is hard-coded to 0.0 (line 465, 584).

This is the path live_engine takes (line 1754 `detect_cross_asset_regime`, line 1763 `regime = regime_state.primary`). The churn signal — used by downstream stickiness logic and exposed via telemetry — is permanently zero in production. Anything that reads `regime_state.churn_rate` to gate trading (e.g. avoid entries during regime whipsaw) will see "no churn" forever.

**Behavioral test to lock the regression**:
- Construct two synthetic sector dataframes where the cross-asset primary regime alternates per call (e.g. half the sectors trending_up, half trending_down, just past the boundary).
- Call `detect_cross_asset_regime` on 30 successive feature snapshots designed to flip the primary.
- Assert `regime_state.churn_rate > 0.5`. Today it returns exactly 0.0.

---

### DD2-4 — Regime hysteresis applies *only* to softmax-probability EMA; the primary label can flap on a single-bar score tie at the trend threshold (subsystem 2)

**Severity**: MEDIUM
**File**: `backend/organism/regime.py:262-263`, `309-315`, `352-365`

`_compute_probabilities` produces hard-coded score additions (e.g. `scores[TRENDING_UP] += 2.0` if `trend_slope > self._trend_threshold`). On the boundary, an infinitesimal slope flip from `+threshold + ε` to `+threshold − ε` reassigns 2.0 from TRENDING_UP to CHOP. After softmax, the probability vector flips by ~50 %. EMA smoothing with `_alpha=0.3` (line 99) damps this, but `primary = max(self._smoothed_probs, key=...)` returns the *argmax* — there is no hysteresis band around the leader. A 50/50 EMA tie between TRENDING_UP and CHOP still flips `primary` on a single bar.

This was the V7 DD-2 wave-24 fix's neighbor: missing ATR returns UNKNOWN (good), but the trend↔chop boundary still flaps cleanly because the tiebreak is `max(..., key=...)` with no minimum-margin requirement. Symptoms: regime_at_entry will not match regime_at_exit for sub-threshold trends, and `_regime_cooldown_active` (live_engine.py:2484) churns on every flip (`if regime != self._last_regime`).

Note also `_regime_cooldown_active` only fires on the *adverse* transition `trending_up → high_vol|trending_down` (line 2489); benign flaps trending_up ↔ chop don't even cooldown. So the system silently re-enters in chop after a 1-bar dip.

**Behavioral test to lock the regression**:
- Construct an SPY price series where `trend_slope` is precisely at `self._trend_threshold` for 50 bars, with ±0.1 bp jitter.
- Feed bars to `detect()`.
- Assert: number of `primary` flips < 5 across 50 bars (sticky). Today it can flip on every bar.

---

### DD2-5 — Kelly's regime-stratified path bypasses unconditional Kelly + zero-vol refusal even though the comment block claims it is now an upper bound (subsystem 1)

**Severity**: MEDIUM
**File**: `backend/organism/kelly_sizer.py:362-388`

The comment at lines 362-378 says regime_kelly is now an "UPPER bound (when present) rather than a bypass — current-edge floors still apply." But the actual code:

```python
if _regime_eligible:
    kelly_raw = min(regime_kelly, 1.0)
else:
    mean_r = float(np.mean(dir_returns))
    var_r = float(np.var(dir_returns, ddof=1))
    if var_r < 1e-8 or mean_r <= 0 or ...:
        unconditional_kelly = 0.0
    else:
        unconditional_kelly = min(mean_r / var_r, 1.0)
    ...
    kelly_raw = min(max(signal_kelly, unconditional_kelly), 1.0)
```

When `_regime_eligible` is True (regime has ≥ 10 trades, candidate has positive predicted_return, confidence ≥ 0.5), the unconditional Kelly path is **never executed**. The wave-18 zero-vol refusal at lines 405-414 (`if atr_var_squared < _ATR_VAR_MIN: signal_kelly = 0.0`) is also gated entirely by the `else` branch, so on a zero-volatility bar with a stratified regime in play, kelly_raw inherits regime_kelly's full value despite the current bar having no edge.

Behavioral consequence: once 10 trades accrue in (say) `trending_up`, every candidate that has a positive `predicted_return` and `confidence ≥ 0.5` is sized from the historical regime average, even on a bar where current-edge volatility is essentially zero. The "still apply current-edge floors" claim is aspirational; the code does not enforce it.

**Behavioral test to lock the regression**:
- Seed `kelly_sizer._regime_stats["trending_up"]` with 15 wins + 0 losses (regime_kelly ≈ 1.0).
- Construct a candidate with `confidence = 0.6, predicted_return = 0.001`, ATR computed as 1e-8 (zero-vol bar).
- Call `size_positions(...)` in production mode (trade_count > 200).
- Assert: `kelly_raw` for that candidate is 0 (not 1.0). Today it is 1.0.

---

### DD2-6 — Inverse-ETF regime flip lives only in `AlphaScanner._regime_alignment`; Kelly's regime_scale, AdaptiveExitEngine's REGIME_STOP_ATR, and the exit time-limit table all see the un-flipped regime (subsystem 7)

**Severity**: MEDIUM
**Files**:
- Flip site: `backend/organism/alpha_scanner.py:319-362` (uses `_effective_regime` for SH/PSQ)
- Un-flipped: `backend/organism/kelly_sizer.py:614-652` (`_regime_scale(regime)` — symbol-agnostic)
- Un-flipped: `backend/organism/adaptive_exits.py:135-184` (`REGIME_STOP_ATR`, `REGIME_TP_R`, `REGIME_TRAIL_ATR`, `REGIME_MAX_BARS`, `REGIME_DECAY_START` — all keyed by raw regime)
- Un-flipped: `backend/organism/live_engine.py:2489` (regime-transition cooldown)

`AlphaScanner._regime_alignment` correctly inverts regime for SH/PSQ so "buy SH in trending_down" scores 0.9. But every downstream consumer of `regime` for that same trade sees the raw market regime:

- Kelly's `_regime_scale(regime)` returns 0.6 for `trending_down` (per the lookup at line 645) for SH (which is *aligned*, should be 1.2).
- ExitEngine's `REGIME_STOP_ATR["trending_down"] = 2.5` for an SH long (whose direction is *trend-aligned*, should be the trending_up value 3.5).
- ExitEngine's `REGIME_MAX_BARS["trending_down"] = 45` (a time stop) is applied to a position whose thesis is "ride the down-trend" — exactly when no time stop should fire.
- The `_regime_cooldown_active` check at live_engine.py:2489 is symbol-agnostic and triggers on the entry-side event "trending_up → trending_down", which is the *favorable* transition for SH/PSQ.

This is a structural inconsistency. The alpha scorer says "go long SH in trending_down", everything else treats SH as a normal stock in trending_down (smaller size, tighter stop, faster time-stop). Net: SH/PSQ entries are systematically under-sized and over-exited relative to the alpha thesis.

**Behavioral test to lock the regression**:
- For symbol SH in regime `trending_down`, direction +1, run the full sizing + exit-level path.
- Assert: `regime_scale == 1.2` (matches a trend-aligned long), `exit_levels.atr_at_entry * REGIME_STOP_ATR_FOR_ALIGNED == 3.5 * atr` (matches trending_up's stop). Today both are 0.6 and 2.5*atr.

---

### DD2-7 — `_is_learning_mode` is a property that recomputes from `len(self._strategy_trades())` on every read; one tick crossing the 200-trade boundary uses inconsistent rules across exit / sizing / gate sites (subsystem 8)

**Severity**: MEDIUM
**File**: `backend/organism/live_engine.py:770-775`, `2137`, `2729`, `2774-2779`, `2853-2867`, `3580-3593`

```python
@property
def _is_learning_mode(self) -> bool:
    return len(self._strategy_trades()) < LEARNING_MODE_TRADES  # 200
```

In a single tick, the property is read at:
- Line 2137 (`self.exit_engine.learning_mode = self._is_learning_mode`)
- Line 2729 (alpha scanner `learning_mode=` arg)
- Line 2774 (`_MIN_MAIN_CONF` selection)
- Line 2853 (composite-confidence formula switch)
- Line 2901 (`_conf_ml_component` blanking)
- Line 2930-2962 (heuristic routing + DROP_ML_FROM_GATE branch)
- Line 3061 (breakout pred_ret floor decision)
- Line 3580 → `kelly_sizer.size_positions(trade_count=trade_count, ...)` where trade_count is read separately

If a closed-trade reconciliation lands inside `_reconcile_fills()` mid-tick (called at line 3837 after entry submission), `len(self._strategy_trades())` increments. Earlier in the same tick, exit processing (line 2137) and entry composition (line 2853) used learning rules; later sites in *the same tick* (after reconciliation, e.g. governance / brain save / sizing-side guards if re-checked) read production rules. The `trade_count` passed to Kelly at line 3580 was sampled at one point and may differ from `_is_learning_mode` reads later in the tick.

Worse: the warm-start path (`live_engine.py:1241-1272`) is gated by `len(self._all_trades) >= 300` at engine startup *only*. If trade #300 closes mid-session, the freeze never lifts until the next process restart — there is no in-tick re-trigger. So the warm-start race the prompt asked about is one-shot at startup, not mid-tick — the issue is the inverse: in-session trade-count crossing changes behavior of every gate in `step()` but does NOT trigger warm-start application until restart.

**Behavioral test to lock the regression**:
- Seed `_all_trades` with 199 strategy trades. In the test harness, monkey-patch `_reconcile_fills` to push trade #200 onto `_all_trades` between the exit-step and entry-step of a single `step()` call.
- Run one full step.
- Assert: the entry-step decision points (`_eff_conf` formula, breakout pred_ret floor, kelly trade_count) all see the same `_is_learning_mode` value as the exit-step did. Today they will diverge.

---

### DD2-8 — Breakout fallback path strips ML sign via `abs(ml_sig.predicted_return)`; a neutral (`direction == 0`) ML with negative `predicted_return` still sizes a long entry (subsystem 4)

**Severity**: LOW–MEDIUM
**File**: `backend/organism/live_engine.py:3043-3067`

The pure-breakout entry path at line 3044 vetoes only on `ml_sig.direction < 0`:

```python
if not self._is_learning_mode and ml_sig and ml_sig.direction < 0:
    continue
```

`direction` is set in `ml_signal.py:466-471` as a 3-way (-1/0/+1) using buy/sell thresholds (default 0.52/0.48). When `0.48 ≤ p_up ≤ 0.52`, `direction = 0`. The veto does NOT trigger. Then at line 3061-3067:

```python
if ml_sig and not self._is_learning_mode:
    if abs(ml_sig.predicted_return) > 1e-4:
        pred_ret = abs(ml_sig.predicted_return)
    else:
        pred_ret = 0.005 + 0.015 * bs.composite_score
```

`abs(...)` strips the sign. So a "neutral ML with negative magnitude" feeds Kelly a *positive* expected return for a long-only breakout entry. The breakout is taken even when the ML, while not strong enough to veto, leans against the trade.

**Behavioral test to lock the regression**:
- Construct an ML signal: `direction=0, predicted_return=-0.005, confidence=0.4`. Pair with a breakout signal at `composite_score=0.7`.
- Run the entry pipeline in production mode.
- Assert: candidate is rejected OR `pred_ret` is set to the heuristic floor, NOT to 0.005. Today `pred_ret = 0.005`.

---

### DD2-9 — EOD flatten has no upper time bound; if the engine ticks after market close the flatten path retries indefinitely with broker rejections, and a single failure has no carry-over retry beyond `pending_exit` TTL (subsystem 9)

**Severity**: LOW–MEDIUM
**File**: `backend/organism/live_engine.py:1660-1679`, `2363-2396`

```python
_hhmm_eod = _now_et.hour * 100 + _now_et.minute
if _hhmm_eod >= 1545:
    self._alpha_breakout_late_blocked = True
if _hhmm_eod >= 1558:
    _eod_flatten_triggered = True
```

There is no upper bound. At 17:30 ET (after-hours), `_hhmm_eod = 1730 >= 1558` is still true. As long as the engine ticks (e.g. paper-trading runs 24/7 in development mode), flatten continues to fire. Each tick re-submits exits for whatever positions still appear in `current_positions`, the broker rejects (market closed), the `except Exception as e` at line 2392 logs it as `EOD flatten failed for {sym}: {e}`, and `_pending_exit[sym]` is set in the `finally` (line 2395). That pending-exit expires after `_PENDING_EXIT_TICKS = 3` ticks (~30 s), at which point the next tick retries — burst-fail loop.

If the broker's reject reason is wash-trade or insufficient buying power for an EOD-only short close (not a market-closed reject), the position carries to the next session because the bracket of "did the order actually fill" is not checked; only `_pending_exit` TTL is. The fail at 15:58 ET silently expires by 15:58:30 with no escalation, no Slack alert (the alert wiring at 33d6138 isn't wired into the EOD flatten branch), no force-flatten retry path.

Also note that the `try / pass` for timezone parsing failure (line 1678) silently sets neither flag — if `zoneinfo` import fails, EOD flatten never fires at all. The previous commit guarded against `zoneinfo` not existing with `pass`, but that means a misconfigured base image (no timezone data) silently disables EOD flatten globally.

**Behavioral test to lock the regression**:
- Inject `_now_fn` returning 16:30 ET (post-close).
- Open one position. Mock `_submit_exit_order` to raise `BrokerClosedError`.
- Run 10 successive ticks.
- Assert: position is escalated (alert fired, or moved to a manual-intervention queue) by the end. Today it just spins.

---

### DD2-10 — `runner.py:104` and `routes.py:677,704` still bypass `_now_fn` in cron-style decisions; replay test scenarios that exercise the runner's session-boundary logic compute against wall clock (subsystem 10)

**Severity**: LOW
**File**: `backend/organism/runner.py:104`, `backend/organism/routes.py:677,704`

Wave-27 added `default_now_fn` plumbing across nine classes, but two control-path call sites still use direct `datetime.now(UTC)`:

- `runner.py:104` — `now = datetime.now(UTC)` in the per-tick scheduler. This determines when to run the live tick, which strategies to invoke, and is read independently of `engine._now_fn`. Replay tests that drive the runner directly (rather than the engine) see wall clock here.
- `routes.py:677` and `:704` — `cutoff = datetime.now(UTC) - timedelta(hours=1)` and `{"cutoff": cutoff, "now": datetime.now(UTC)}` filter recent activity for the API. This affects what the UI / curl-based tests see and could let a replay-mode HTTP poll show wall-clock-stamped data alongside replay-clock-stamped data.

Less consequential: `feature_store.py:139,233`, `attribution.py:409`, `walk_forward.py:185`, `training.py:140-353` use `datetime.now(UTC)` for `created_at` of persisted artifacts. None of these are control-path inputs to strategy decisions, but they break artifact provenance under replay.

**Behavioral test to lock the regression**:
- Run a replay simulator that drives 1 hour of historical bars with `_now_fn` returning the historical timestamp.
- Hit `/api/organism/recent-activity` (uses routes.py:677-704).
- Assert: returned timestamps are in the historical range, not the wall-clock range. Today they are wall-clock.

---

## Summary

**DD2 findings**: 10 (Critical/High/Medium/Low breakdown: 0 / 2 / 5 / 3)

| # | Subsystem | Severity | One-liner |
|---|-----------|----------|-----------|
| DD2-1 | 3 (exits/partials) | HIGH | partial-TP `_pending_exit` TTL silences stop-loss for ~30s |
| DD2-2 | 4 + 5 (ML calibration) | HIGH | calibration_map indexed on raw, populated on calibrated — axis mismatch |
| DD2-3 | 2 (regime) | MEDIUM | cross-asset regime never accumulates churn (history saved/restored) |
| DD2-4 | 2 (regime) | MEDIUM | regime primary flaps on argmax tie despite EMA — no hysteresis band |
| DD2-5 | 1 (Kelly) | MEDIUM | regime-stratified Kelly bypasses zero-vol refusal despite comment claim |
| DD2-6 | 7 (inverse ETF) | MEDIUM | SH/PSQ flip is alpha-scorer only; sizing + exits see un-flipped regime |
| DD2-7 | 8 (warm-start/race) | MEDIUM | `_is_learning_mode` is a live property, mid-tick reads diverge |
| DD2-8 | 4 (ML) | LOW–MED | breakout fallback strips sign of ML predicted_return via `abs()` |
| DD2-9 | 9 (EOD flatten) | LOW–MED | EOD flatten unbounded; no retry / no alert on fail; tz-fail silent disable |
| DD2-10 | 10 (replay) | LOW | runner.py + routes.py still use `datetime.now(UTC)` directly |

> The bar in the prompt was 3-7 findings; DD2 returned 10. **By the prompt's own threshold, this exceeds V7's disclosed strategy debt (`>7`)**. The cluster of 5 medium-severity structural bugs (DD2-3, -4, -5, -6, -7) suggests the recent feature stack (cross-asset regime, regime-stratified Kelly, inverse ETFs, learning/production phase machinery) was layered on without auditing the existing call graph for consistency. The two HIGH findings (partial-TP exit suppression and ML calibration axis mismatch) are reachable in current production paper trading — they are not hypothetical.

## TL;DR

DD2 found 10 strategy-logic edges, with two HIGH-severity defects that production already hits: (a) partial take-profit and ML-reversal partial exits set `_pending_exit` for 3 ticks, silencing all stop-loss / max-loss / safety-net checks for ~30 seconds — a position can blow through max_loss_pct on the unsold 70 % during that window (live_engine.py:2154 vs adaptive_exits.py:583+); and (b) the ML calibration map is populated by binning on calibrated_confidence in `record_prediction_outcome` but consumed by binning on raw_confidence in `calibrate_confidence`, so the multipliers are computed against the wrong distribution and slowly drift away from a meaningful identity (ml_signal.py:474-583, live_engine.py:5298). The five medium findings cluster around composability gaps in recently-layered features: cross-asset regime detection silently drops churn (regime.py:431-448), regime-primary has no hysteresis band at threshold ties (regime.py:262), regime-stratified Kelly bypasses the zero-vol refusal (kelly_sizer.py:362-388), inverse-ETF regime flip lives only in alpha_scanner and not in Kelly/exits (alpha_scanner.py:319 vs kelly_sizer.py:614/adaptive_exits.py:135), and `_is_learning_mode` is recomputed every property read so a 200-trade boundary crossed mid-tick splits exit/entry/sizing rules across the same step. DD2 exceeds the prompt's >7 ceiling, indicating the strategy stack carries more debt than V7 disclosed; the partial-TP exit suppression and the calibration axis mismatch should be the first two fix tickets.
