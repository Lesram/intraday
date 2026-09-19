# REPLAY SIMULATOR FIDELITY AUDIT
**Run:** 2026-04-25 (Saturday evening)
**Audited file:** `backend/organism/replay_simulator.py` (708 LOC)
**Tests:** `tests/test_replay_simulator.py` (497 LOC, 25/26 passing)
**Audit type:** Static code review + smoke run + structural comparison vs live engine

**Bottom line:** The replay simulator is **trustworthy for relative comparison testing within a single run** but has known fidelity gaps that mean **absolute backtest numbers should not be over-trusted as predictions of live performance**. For the specific use case of evaluating the three RC-1.5 fixes, it is appropriate IF we use it correctly (relative deltas, not absolute claims) AND we couple it with shadow-mode validation for the highest-risk change (composite gate).

---

## What the replay simulator does well (confirmed fidelity)

1. **Runs the actual live engine.** `ReplayEngine.run()` instantiates `OrganismLiveEngine` and calls the real `live_tick()`. There is no parallel simulation logic for gating, ML inference, regime detection, brain persistence, exit selection, pyramiding, alpha scoring, or breakout scanning. **The same code paths execute in replay as in live.** This is the most important property.

2. **Time clock is properly overridden** (lines 479-480):
   ```python
   engine._time_fn = lambda: bar_provider.current_simulated_time
   engine._now_fn = lambda: bar_provider.current_simulated_datetime
   ```
   No wall-clock leakage; the engine sees bar-derived time only.

3. **Brain persistence works.** Replay starts from a brain dir (default temp, can pass existing), saves brain through normal pathways. The F1–F4 guards apply identically.

4. **Universe + timeframe match production parameter shape.**

5. **Smoke test confirms regime classifier responds correctly to trend signal.** On synthetic up-trending bars, 100/100 ticks classified as `trending_up`. This means the live "stuck in chop" issue is specifically about the 200-bar-SMA × 1-min-bar scaling not the classifier itself.

---

## Significant fidelity gaps (must be aware of)

### Gap 1: Same-bar fill model — mild look-ahead optimism

The simulator advances cursor → engine reads bars up to (not including) cursor → engine submits order → broker fills at `current_price` which is the close of the bar the engine just observed.

In live, the engine sees bar N close, submits an order, and the fill happens at *next* bar's open or partway through bar N+1. **Replay assumes immediate same-bar fill at observed close + slippage.** Slight optimistic bias on entries during fast moves.

**Severity for RC-1.5 evaluation:** LOW. The bias is symmetric across baseline and treatment runs, so relative deltas are preserved.

### Gap 2: No bid/ask spread

Single close price is used for both entry and exit fills. Real markets have a half-spread cost on the round-trip. For SPY, NVDA, QQQ etc., the spread is often 1 cent (~0.5 bps), so impact is small for liquid US equities.

**Severity for RC-1.5 evaluation:** LOW for our universe; would matter more on illiquid names.

### Gap 3: MarketScanner is disabled (line 483: `engine.market_scanner = None`)

This is a **real fidelity gap.** Live tension is computed by MarketScanner and contributes 20% to the composite confidence formula. In replay, the live_engine fallback (lines 2157-2168) computes a tension *proxy* from `vol_sma_ratio` and `ret_1d` features — close in spirit but **different numbers**.

**Implication:** Composite confidence values in replay will systematically differ from composite confidence in live. So:
- The *gate-firing rate* will differ between replay and live
- The *trade count* will likely differ
- The *direction* of change (more vs fewer trades after gate fix) should still be reliable

**Severity for RC-1.5 evaluation:** MEDIUM. The composite-gate fix's *relative* impact (more/fewer rejections) should still be visible in replay, but the absolute trade count delta will be off. We should report relative percentages, not absolute trade counts as predictions.

### Gap 4: No order latency model

Live has order submission queue, broker round-trip latency, possible partial fills. Replay assumes instantaneous fills.

**Severity for RC-1.5 evaluation:** LOW for paper-mode comparison; would matter at higher trading frequency.

### Gap 5: No data gaps, halts, or bar corrections

Real Alpaca data has occasional missing bars, late bars, post-hoc corrections. Replay assumes pristine OHLCV.

**Severity for RC-1.5 evaluation:** LOW for short backtests on liquid universe; can matter on extended runs or stressed sessions.

### Gap 6: ML retraining timing differs

The live engine retrains ML every ~200 trades. During a replay run, retraining happens at points determined by the replay's own trade pace, not the live trade pace. So if a replay generates 500 trades over a 30-day window where live generated 250, the ML state will diverge as the replay progresses.

**Severity for RC-1.5 evaluation:** MEDIUM, but **only if the replay run is long enough to trigger retrains.** For a 5-10 session backtest, retrain cadence is unlikely to trigger.

### Gap 7: Trade log structure differs from `trade_history.csv`

`SimulatedBroker.trade_log` records sells with a small subset of fields (symbol, side, qty, entry, exit, pnl). The live `trade_history.csv` is written through a different code path with MFE/MAE/regime/exit_reason/etc. **Comparing replay output to `trade_history.csv` requires careful field mapping**, and some live-only fields (predicted_return, confidence as composite, regime_at_entry) may not exist in replay output.

**Severity for RC-1.5 evaluation:** LOW — we just need to compare *aggregate* metrics across runs; not field-level matching.

### Gap 8: Broker initial cash default 100k vs live ~111k

Just a parameter; trivially set. Doesn't bias results unless we compare absolute equity numbers.

---

## What the replay simulator can / cannot tell us about RC-1.5

### Can:

- **Relative trade-count delta** between baseline and treatment (e.g., "composite gate filter dropped 65% of entries")
- **Relative win-rate delta** ("baseline 31%, treatment 42%, +11pp")
- **Relative pyramid_cut share delta** ("baseline 31% of exits, treatment 18%")
- **Relative MFE-capture improvement** ("trailing-stop capture went from −2% to +35%")
- **Direction of expectancy change** (better/worse)
- **Whether new gating logic compiles, integrates, and doesn't crash**

### Cannot:

- Predict actual live trade count or PnL absolute number
- Validate behavior under data gaps, halts, or fast moves
- Validate behavior under ML retraining within the test window
- Predict slippage at scale (real fills > observed close + 5 bps)
- Predict realistic spread cost or partial fills
- Account for governance / drawdown-kill / daily max-loss interactions accurately if those weren't designed in test

---

## "Past horrible experiences" — defensive checks

Without specific knowledge of the user's past traps, here are the classic backtest failure modes I'm checking for in this audit:

| Trap | Status | Notes |
|---|---|---|
| Look-ahead bias | **PARTIAL** | Same-bar fill at close = mild same-bar look-ahead. Mitigated by fact that decision uses close and fill uses close — no future data. |
| Train/test leakage | **CLEAN** | Brain dir is per-run; ML doesn't see future bars |
| Survivorship bias | **N/A** | Universe is fixed at runtime |
| Data snooping / multiple-comparisons | **OPERATIONAL** | We are comparing N=3 fixes; should report at least directional confidence not just point estimates |
| Overfit to test set | **OPERATIONAL** | We have 12 sessions of live data; using replay to validate fixes designed from those 12 sessions has fitting risk. The fixes are mechanism-level (gate variable change, threshold tweak), not parameter-tuned to backtest output. Lower fit risk than hyperparameter sweeps. |
| Unrealistic fills | **MILD** | No spread, no latency, immediate fill — biases optimistic. |
| Different brain/ML state across runs | **MEDIUM** | Need to ensure baseline and treatment runs use same starting brain |
| Different bar data across runs | **CLEAN** | Same bars in both runs |
| Unrealistic position sizing | **CLEAN** | Same Kelly/risk-budget logic |

---

## Verdict (T1.2)

**GREEN with conditions.** Specifically:

1. **Use replay for RELATIVE comparison only.** Report deltas (treatment vs baseline), not absolute predictions. Headlines like "composite-gate fix reduces pyramid_cut share from 31% to 18%" are fine. Headlines like "new strategy will earn $X next week" are not.

2. **For the composite-gate fix, ALSO ship in shadow mode for live validation.** The gate change is the highest-leverage and highest-risk in RC-1.5. Shadow mode pattern: log what the new gate WOULD have decided alongside what the old gate DID decide, no behavior change yet, for 5 sessions. Then compare live disagreement rate to backtest predictions. **This is the gold-standard validation for a critical-path change.**

3. **For regime-classifier recalibration and ML weight drop, replay-only validation is sufficient.** Both are lower-risk: regime change just shifts which parameter set is used (and the parameter sets themselves are unchanged), ML weight is a config constant that downweights an already-uncalibrated signal. Either could ship Monday with replay validation alone if backtest deltas are clean.

4. **Empirical fidelity check (recommended, ~30-45 min).** Pull bars for the most recent live trading day from Alpaca, run replay against them with the live brain snapshot, compare gross stats (trade count, regime mix, exit reason distribution) to live. If within ~50%, replay is calibrated for our use case. If wildly off, we know to be more conservative.

---

## Proposed validation plan for RC-1.5

| Fix | Validation |
|---|---|
| **Composite-gate change** | (a) Unit tests for new gate logic. (b) Replay backtest: baseline `eb90fa3` vs treatment, 30 days bars, compare relative deltas. (c) **Shadow mode in production for 5 sessions** before flipping the actual gate. → Ships RC-2 *next* Monday, not this Monday. |
| **Regime classifier recalibration** | (a) Unit tests verify trending_up fires on known-trending bars. (b) Replay backtest comparison. (c) Ship in RC-1.5 if backtest delta is positive. |
| **ML weight drop (0.50 → 0.20)** | (a) Trivial — config constant. (b) Replay backtest. (c) Ship in RC-1.5 if backtest delta is positive. |

**Net deploy plan revision:**
- **Monday RC-1.5:** `eb90fa3` + regime recalibration + ML weight drop. Composite-gate logic *included* in shadow-mode telemetry only.
- **Following Monday RC-2:** Flip the composite gate from `_eff_conf` to `composite` based on shadow-mode disagreement data.

This is more conservative than "ship all three fixes Monday" but materially more honest about what we know vs what we'd be assuming.

---

## What this means for the next ~6 hours of work

**Tonight:** Build all three fixes in branches with unit tests. (~3-4h)
**Tonight:** Empirical fidelity smoke check against last live session. (~30 min)
**Sunday morning:** Run replay backtests on each branch separately. Compare deltas.
**Sunday afternoon:** If regime + ML weight backtest deltas are clean → bundle into RC-1.5, refresh preflight. If composite-gate delta is clean → ship in shadow mode (logging only) inside RC-1.5. Update `MONDAY_DEPLOY_eb90fa3.md` to `MONDAY_DEPLOY_RC-1.5.md`.
**Sunday evening:** Final preflight on RC-1.5. Brain backup.
**Monday open:** Deploy RC-1.5.

---

## One question for you (partner-mode)

Two of the three fixes (regime, ML weight) are low-enough risk that I'd ship them in RC-1.5 if the backtest looks clean. The composite-gate fix is the highest-leverage but I want to ship it in shadow mode first.

**Are you comfortable with that staged plan**, or do you want me to also ship the composite-gate change live in RC-1.5 (with full backtest validation but skipping shadow-mode)?

The conservative answer (mine): shadow-mode the gate first.
The aggressive answer: if backtest is unambiguous, ship it live Monday.

Either way I'll execute. Tell me which one you want.
