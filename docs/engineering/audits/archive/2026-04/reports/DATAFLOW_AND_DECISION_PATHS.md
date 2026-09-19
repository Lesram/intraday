# Dataflow and Decision Paths

**Date**: 2026-04-23 | **Live commit**: `ce06d41` (ref file/line numbers are against repo HEAD `33d6138`; semantics are equivalent for the decision-path tracing)

This document traces one trade end-to-end for 5 scenarios with exact file:function references. It calls out duplication, split source-of-truth, and evaluation-order dependencies.

---

## 0. The canonical path (abstract)

```
streaming bar → features → regime → (breakout + alpha) scanners → ML inference
  → confidence blend → entry gates → Kelly sizing → Alpaca submit
  → stream terminal state → reconcile → TradeRecord → continuous_learner
  → walk-forward + acceptance gate → model swap (gated) → brain save (guarded)
```

12 phases in `live_engine._live_tick_inner()`. Each scenario below follows this spine and calls out where it diverges.

---

## Scenario 1 — A normal winning trade (e.g., SPY long)

### Inputs
- Symbol: SPY
- Regime: trending_up (rare; 3% of ticks)
- Trade count at entry: 370 (> 200 → production confidence blend)
- ML state: is_trained=true, accuracy 0.617

### Trace

1. **Tick enters** — `scheduler.start()` loop calls `live_engine.live_tick()` (`live_engine.py:1138`)
2. **Governance & warmup checks** — `_live_tick_inner()` @ line 1246:
   - `governance.is_trading_halted` → False (halted=false, no active cooldown)
   - `_warmup_counter` passed
   - `streaming_provider.last_update_time` within 120s
   - Not after 15:45 ET (entry allowed)
3. **Bar + features** — `_fetch_bars()` + `_compute_features()` → `features_by_symbol["SPY"]` has 79 features
4. **Regime detect** — `regime_detector.detect(features_by_symbol)` → returns `("trending_up", regime_state)` at line 1368–1389
5. **Scanners run**:
   - `breakout_scanner.scan()` → candidate with `breakout_score=0.72`
   - `alpha_scanner.scan(features, ml_signals, regime, ml_is_trained=True, learning_mode=False)` @ line 2049 → `AlphaCandidate(SPY, composite_score=0.62, ml_pred=+0.008)`
6. **Confidence blend** — `live_engine.py:2170–2184`:
   - Production branch: `conf = 0.50 * ml_conf (0.58) + 0.30 * breakout (0.72) + 0.20 * tension (0.45) = 0.596`
   - Gate threshold: baseline 0.40 (trending_up is not defensive) → pass
7. **Entry gates** — `_passes_entry_gates()` @ line 595–650:
   - `open_position[SPY]`? no
   - `exit_cooldown` active? no
   - `_pending_entries[SPY]`? no
   - `sector_gate` (ETF bucket 2/3)? pass
   - `fitness_gate` (SPY has 6 prior trades, below 10-trade threshold) → no gate applied (learning-style)
   - `liquidity_gate` (SPY daily vol >> floor) → pass
   - `_symbol_banned[SPY]`? no
8. **Kelly size** — `kelly_sizer.size(confidence=0.596, regime="trending_up", equity=111529.48, fitness=0.55)`:
   - `risk_budget_production=0.0025` * 111529.48 = $278.82 theoretical risk dollar
   - regime_size_scale[trending_up] = 1.2 → 334.58
   - `_ML_CONFIDENCE_MIN=0.5` passes (0.596 ≥ 0.5)
   - Compute share count from stop distance (ATR × 3.5) → shares
9. **Submit** — `order_service.submit_entry(SPY, shares, buy)` → Alpaca accepts, order_id recorded
10. **Stream watch** — subsequent tick(s): `_stream.is_order_terminal(order_id)` → `FILLED`; `_pending_entries[SPY]` cleared; position recorded
11. **Exit evaluation** over N bars — `adaptive_exits.check_exit()`:
    - At bar 12: price reaches `take_profit` level (trending_up tp_r=6.0) → **take_profit** exit fires at +$9.99
12. **Reconcile** — `_reconcile_closes()` @ line 3688:
    - Matches entry order + exit order
    - `order_service.get_position_cost_basis()` → entry 587.12 avg, exit 597.11
    - Build `TradeRecord(symbol=SPY, direction=long, entry_price=587.12, exit_price=597.11, shares=N, entry_bar=t0, exit_bar=t12, exit_reason="take_profit", mfe=9.06, mae=0.2, confidence=0.596, regime_at_entry="trending_up", regime_at_exit="trending_up")` @ line 3886
    - Append to `self._all_trades` (line 3909)
13. **Learner update** — `learner.observe_trade(trade)` — increments total_trades to 371, cumulative_pnl += $9.99, updates Sharpe rolling window
14. **Retrain check** — if `bars_since_retrain >= 60`: `learner.retrain(features_by_symbol)` → acceptance_gate runs composite-score + calibration check
15. **Persist** — `brain.save_essential_state(signal_gen, learner, all_trades, ...)` @ line 4601 → writes trade_history.csv, learning_state.json, manifest.json (guarded via `_write_manifest_guarded()` @ `brain_persistence.py:728`)

### Duplication / authority splits
- **Confidence weights** appear in 3 places: `live_engine.py:2170–2184` (blend), `alpha_scanner.py:122` (learning-mode zero of ML), `kelly_sizer.py:110` (`_ML_CONFIDENCE_MIN=0.5`). A future refactor should consolidate.
- **Fitness gate** static value 0.45 appears in `decision_telemetry.py:45` AND computed as `0.45 if production & trades>=10 else 0.0` in `live_engine.py:2916`. Telemetry may log 0.45 even when actual gate was 0.0.

### Evaluation-order dependency
- If `breakout_scanner` runs before `alpha_scanner` (it does), the alpha path has access to the breakout's classification; changing order would change features fed to ML inference.

---

## Scenario 2 — A losing trade (XLE pyramid_cut at 5 bars)

### Inputs
- Symbol: XLE
- Regime: chop (96% of ticks lately)
- Entry confidence: 0.41 (just above baseline)
- Entry at 10:07 ET (just past opening-range block)

### Trace

1. **Entry path** — same as Scenario 1 through step 9 (submit). Order fills at $89.32.
2. **Bar 1–4**: price oscillates: 89.32 → 89.38 → 89.30 → 89.15 → 89.12 → 89.05 (MFE=$0.06, MAE=−$0.27)
3. **Bar 5 pyramid check** — `pyramider.should_pyramid(position, current_price=89.05, atr=0.21)` @ line ~1700:
   - Computes excursion: (89.32−89.05) / 0.21 = 1.29 ATR **adverse** excursion
   - Branch: `pyramid_cut` trigger (excursion exceeds cut threshold)
   - **Exp1A chop min-hold gate** checks: bars_held=5 < min_hold_bars (e.g., 10 in chop) → **suppress** cut
     - OR if entry occurred OUTSIDE the min-hold window, gate allows (see PRE_300 report: "XLE −$6.65 was a −3.3R cut at just 5 bars — Exp1A should have fired but XLE may have entered outside the min-hold window")
4. **If Exp1A fires**: returns `PyramidAction(action="none")` → trade continues
5. **If Exp1A doesn't fire**: returns `PyramidAction(action="cut", reduce_shares=...)` → exit at 89.05, loss realized at −$6.65 (−3.3R)
6. **Reconcile** — `_reconcile_closes()` builds `TradeRecord(exit_reason="pyramid_cut", regime_at_entry="chop", regime_at_exit="chop", confidence=0.41, mfe=0.06, mae=0.27)`
7. **Learner update** — total_trades += 1, cumulative_pnl += −6.65
8. **Persist** — same save path
9. **No retrain** — drift_events=0, no model swap

### Key leak point (documented repeatedly)
- Trade went green (MFE > 0) briefly
- Exited at −1.29× ATR on a temporary dip that would have recovered (per `TRADING_EDGE_BASELINE_REPORT.md` and `POST300_STABILITY_REVIEW_2026-04-21.md`)
- **This is the dominant leak**: 24/32 baseline trades; 6/16 on Apr-21
- **Exp4 (chop trail widen, NOT LIVE) would NOT affect pyramid_cut; Exp1A (LIVE) and future broader widening of pyramid_cut adverse threshold in chop are the levers**

### Split authority / duplication
- **Pyramid adverse threshold** is hard-coded in `pyramider.py`; no single config source. Memory says "evolved_params does not directly move this" — it's not in the evolved set.
- **Exp1A min-hold bars** per regime — hard-coded in pyramider; no env override. Fine in principle but not observable via config snapshot.

### Evaluation-order dependency
- `_reconcile_closes()` (step 8 in tick) runs BEFORE `_pyramid_check()` (step 9 in tick). This is important: if a position was already closed externally, the pyramid check sees `open_position[symbol]` as closed and skips.

---

## Scenario 3 — An inverse ETF candidate (PSQ in chop, Exp2 blocks)

### Inputs
- Symbol: PSQ
- Regime: chop
- `inverse_etfs=["DOG","PSQ","RWM","SH"]` in runtime config

### Trace

1. **Tick enters** — same 1–7 as Scenario 1
2. **Scanners produce PSQ candidate** — e.g., `composite_score=0.55` from breakout_scanner (inverse ETFs are in universe per `e7112e1`)
3. **`_regime_alignment()` for inverse ETF** — `live_engine._regime_alignment(symbol, regime)` flips the regime label: for PSQ in `trending_down`, alignment returns `trending_up` (sign-flip) so the inverse tracks correctly
4. **Exp2 inverse-ETF chop suppression** @ `live_engine.py:2468–2474`:
   - Condition: `regime == "chop" AND symbol in inverse_etfs` → **SKIP entry candidacy**
   - Suppression counter incremented (observable via logs)
5. **No entry submitted** for PSQ
6. **Alpha scanner** may still rank PSQ but entry path short-circuits before Kelly sizing

### Outcome
- Zero PSQ/SH trades in chop since Exp2 deploy (2026-04-10)
- Baseline had 6 PSQ/SH trades all losers; Exp2 eliminates them

### Key distinction
- **Exp2 is a pre-gate**, not a post-filter. It prevents entry candidacy entirely — no confidence scoring wasted, no Kelly compute, no pending-entry slot consumed.
- **Exp2 does not remove PSQ/SH from universe**. They remain for monitoring (`e7112e1` ensures they survive brain restore). If regime shifts to `trending_down`, suppression lifts.

### Split authority
- Inverse-ETF list defined in multiple places:
  1. `backend/config.py` / runtime default: `["DOG","PSQ","RWM","SH"]`
  2. `.env` (`ORGANISM_INVERSE_ETFS`) — likely overrideable
  3. `alpha_scanner.py` may have its own check for inverse behavior
  - Recommend single source-of-truth (low priority — list is stable).

---

## Scenario 4 — pyramid_cut / trailing_stop case

### Inputs
- Symbol: NVDA
- Entry long at $880 in chop
- ATR = $4.00

### Trace (two sub-cases)

**Sub-case A — pyramid_cut (covered in Scenario 2)**

**Sub-case B — trailing_stop giveback**

1. Entry at $880 passes all gates
2. Bar 3: price → $885 (MFE = $5)
3. Trailing activates at `trailing_start` (evolved: 1.00× multiplier of base)
4. Trailing distance: `trail_atr = REGIME_TRAIL_ATR["chop"] = 3.0` × ATR (4.00) = $12.00 below high
5. Bar 5: price drops back to $880, then $878, then $875 — still above trailing stop ($885 − $12 = $873)
6. Bar 7: price → $873.5 → trailing stop triggers at $873 → exit at −$7 (MFE was $5, giveback is $12)
7. **Exp4 would widen this** to 5.0× ATR in chop = $20 below high, letting trade ride longer (OR disable trailing in chop entirely, relying on timeout)
8. **Exp4 is REVERTED IN WORKTREE, NOT IN CONTAINER** — so the $195 of giveback observed over 5 sessions persists

### Evaluation-order dependency
- Trailing-stop check fires AFTER pyramid_cut check in the exit evaluation sequence (`adaptive_exits.check_exit`). If price crosses pyramid_cut adverse threshold AND trailing-stop in the same bar, pyramid_cut wins because it's evaluated first.

---

## Scenario 5 — Force-save / persistence path

### Inputs
- Admin issues `POST /organism/save?force=true` (e.g., after restart for brain recovery)

### Trace

1. **Route handler** — `backend/organism/routes.py` `save_brain()` @ line ~200:
   - `Depends(require_admin)` checks admin auth
   - Query param `force=true` required; absence → 400
2. **Delegates to engine** — `engine.force_save_brain()` @ `live_engine.py:~4428`
3. **`brain.save()`** (not `save_essential_state`) — this path writes ALL artifacts including ML joblib and evolved_params bypassing walk-forward gate
4. **Call chain**:
   - `save_essential_state()` semantics (trade_history, learning_state, manifest guarded) PLUS
   - `_save_models()` — writes `ml_classifier.joblib`, `ml_regressor.joblib`
   - `_save_evolved_params()` — writes `evolved_params.json`
5. **Manifest guard runs**:
   - `_write_manifest_guarded(force=True, allow_reset=True, reset_reason="force_save_admin_route")`:
   - Guard checks: if incoming trained → write freely
   - If incoming untrained but force=True + allow_reset=True + reason provided → allow with **suspicious-write instrumentation logged** (F3)
   - Read-back invariant runs (F3): verifies written manifest matches `learner.state` + `signal_gen._is_trained`
6. **On failure** (e.g., disk full, manifest mismatch):
   - Exception bubbles to route → 500 returned
   - Alert fired via `send_alert(AlertCategory.CRITICAL, ...)` — **but only if running at HEAD** (alerting wiring lives in commit `33d6138`; live `ce06d41` does not alert here)

### Why this matters
- **F3 read-back invariant** is the difference between "save succeeded silently while brain was wrong" and "save fails loud". Deployed in live container.
- **Alerting on guard fire** is at HEAD, NOT in live — silent criticals risk until `33d6138` deploys.

### Split authority / duplication
- Force-save lives in `routes.py` + `live_engine.py`; persistence fork (essential vs full) lives in `brain_persistence.py`. Three modules collaborate. Good separation in practice (routes = auth, engine = context, brain = atomic write), but any change requires all three to stay in sync.

---

## Cross-cutting observations

### Entry-gate ordering is correctness-load-bearing

The `_passes_entry_gates()` sequence:
```
open_position → exit_cooldown → pending_entry → entry_metadata → long_only →
  sector_gate → fitness_gate → liquidity_gate → circuit_breaker
```
- If fitness_gate moved before sector_gate, you could reject a symbol for fitness before checking whether sector cap was already hit — benign but changes observable gate-rejection counters.
- If circuit_breaker moved before open_position, a banned symbol could still be marked as "in-position handled" — potential for stuck state.
- Current order has been stable since H6 (unified gates). Do not reorder without matching test updates.

### Two entry sources, one gate — UNIFIED
After H6, the pure-breakout and alpha paths **share** the liquidity gate and confidence threshold. Before H6 they had different thresholds — that divergence is gone. Good.

### `_reconcile_closes()` is the single source of truth for TradeRecord creation
Any exit — stop, trail, tp, ftf, pyramid_cut, timeout, eod_flatten — produces a TradeRecord via this path. This means the forensic fields (MFE, MAE, regime_at_entry/exit, confidence, bars_held, is_exploration) are uniformly populated. The centralization is a strength.

### Persistence has a clean split-state contract
- **Runtime truth** always persists (trade_history, learning_state, manifest): commits `007a977`, `3534346`, F-lite, F1–F4
- **Promotion-gated artifacts** only persist when acceptance gate passes (ML joblib, evolved_params)
- **Force-save** overrides the promotion gate but logs suspicious-write
- This separation was the outcome of multiple incidents (brain wipes) and is now robust.

### Admin routes are behind `require_admin` Depends — NOT open
All dangerous mutations (halt/freeze/save/rollback/tick) require admin auth. The main risk is not in the routes but in the fact that an in-band admin resume would restart trading that's operationally paused.

### The edge-destroying path is concentrated in `adaptive_exits.py` + `pyramider.py`
All 5 scenarios route through these two files for exit decisions. The fix to expectancy goes through them, not through scanners or ML.

— End of Dataflow and Decision Paths —
