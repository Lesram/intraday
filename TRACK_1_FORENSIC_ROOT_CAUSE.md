# TRACK 1 — Forensic Root-Cause on Negative Expectancy
**Run:** 2026-04-25 (Saturday evening), offline, read-only
**Window analyzed:** since `ce06d41` deploy (2026-04-13) — 12 sessions, 182 trades, −$107.98 cumulative
**Data source:** `organism_brain/trade_history.csv`, `organism_brain/regime_state.json`, `logs/application.log`, and the live code at HEAD `eb90fa3`

**Goal:** answer the four anomalies surfaced in the weekend pack with real tests — not more narrative.

**TL;DR — two findings are big, one is not what we thought it was, one is a code bug:**

1. **98% of the live-window loss (−$105.88 of −$107.98) comes from one subset: alpha-only entries with composite confidence < 0.45** (132 of 182 trades, 73% of all trades). The composite-confidence formula was designed to be the quality gate but isn't actually the gating variable — `_eff_conf` uses ML's self-confidence (`ml_signal.effective_confidence`) which waves trades through even when breakout and tension disagree. **Fix candidate: gate on composite, not ML self-score.** Counterfactual says this one change would have avoided the entire live-window loss.
2. **The regime classifier is stuck in chop.** 7,833 of 8,465 ticks (98.1%) = chop; **zero** trending_up events in the full log window. Not because the market was chop — because the trend_threshold (0.00102 post-intraday-scaling) is compared against the slope of a 200-bar SMA over 10 of its own values, which is mathematically near-impossible to exceed on 1-min bars. The code even comments that the unscaled 0.02 daily threshold "effectively prevents trending_up from ever triggering" — the scaling fix was insufficient. **Fix candidate: recalibrate trend signal to price-vs-shorter-MA or use multi-timeframe detection.**
3. **The "confidence inversion" (mid-bucket wins, high-bucket loses) is NOT statistically significant.** Permutation p-values of 0.40 (mid vs low) and 0.80 (mid vs very_high) with small-n in the high buckets. What IS significant: the low-composite bucket loses systematically (132 trades, CI upper bound +$0.08) — which collapses into finding #1.
4. **ML's predictive power is essentially zero.** Correlation(predicted_return, actual_return) = **0.056** over 182 trades. ML is +0.40% biased long (mean pred +0.36%, mean actual −0.04%). In the tail, win rate *decreases* with predicted return: ≥1.0% pred = 25% win rate, <0.1% pred = 31.2% win rate. **ML signal alone is anti-predictive at the high end.**

Plus a non-finding worth flagging to close the loop:

5. **"Directional accuracy 31% = worse than random" is a reporting artifact.** The `correct_direction` column in trade_history is just `pnl > 0` rewritten — it tracks win rate exactly (both = 31.32%). It's not an independent directional signal. This was on my top-10 weekend-pack findings list; I'm retracting it.

---

## Anomaly 1 — The composite-confidence gate bypass

### The pattern in the data

| Subset | n | PnL | Win rate | Expectancy |
|---|---|---|---|---|
| **alpha-only, composite < 0.45** | **132** | **−$105.88** | **27.3%** | **−$0.80** |
| alpha-only, composite ≥ 0.45 | 11 | +$12.46 | 45.5% | +$1.13 |
| alpha+breakout | 35 | −$10.25 | 40.0% | −$0.29 |
| (empty entry_source) | 4 | −$4.31 | 0.0% | −$1.08 |

Breakdown by confidence band:

| Band | n | PnL | 95% bootstrap CI (expectancy) |
|---|---|---|---|
| composite < 0.45 | 132 | **−$105.88** | **[−$1.81, +$0.08]** |
| 0.45 – 0.55 | 12 | +$15.06 | [−$1.11, +$3.99] |
| 0.55 – 0.65 | 28 | −$13.03 | [−$2.79, +$1.93] |
| ≥ 0.65 | 10 | −$4.13 | [−$2.04, +$1.22] |

132 trades with composite < 0.45 is a *lot* — that's 73% of all live-window trades. These trades were admitted despite the composite landing under even the baseline gate (0.40 in trending regimes, 0.45 defensive / chop).

### The mechanism in the code

From `live_engine.py` lines 2070–2260:

- The per-regime gate thresholds are correct: baseline 0.40, defensive 0.45 (chop), exploration floor 0.25.
- The composite formula (production): `confidence = 0.50 * ml_conf + 0.30 * breakout + 0.20 * tension`.
- **But the gate comparison uses `_eff_conf`, not `confidence`:**
  ```python
  if self._is_learning_mode:
      _eff_conf = confidence
  else:
      _eff_conf = (
          c.ml_signal.effective_confidence
          if c.ml_signal and c.ml_signal.effective_confidence > 0
          else confidence
      )
  ```
- If `ml_signal.effective_confidence > 0`, that value drives the gate. ML's self-reported confidence can be 0.55 and pass the 0.45 chop gate even when the composite lands at 0.30 (because breakout_score × 0.30 + tension × 0.20 contribute little).
- Entry_source = `alpha` is assigned whenever `breakout_score < 0.4` (lines 2600–2606). So "alpha-only" literally means "breakout did not confirm this entry." Those are the trades losing money.

### Interpretation

The composite formula was the *design intent* of a multi-factor quality gate. The *implementation* has the gate keying off a different variable — ML's self-confidence — which turns out to have no predictive power (see Anomaly 4). So the gate admits trades that the composite would have filtered, and those are exactly the losers.

### Counterfactual

If we had gated on **composite ≥ 0.45** over the full live window:
- Keep: 50 trades, net −$2.10 (flat)
- Drop: 132 trades, net −$105.88
- **Net delta: +$105.88 (avoided loss). That's the entire 12-session cumulative.**

This isn't a backtest — it's an arithmetic counterfactual on already-executed trades. But the direction is stark.

### Fix candidates, ranked

1. **Gate on composite, not `_eff_conf`** (one-line change in production path; learning-mode path already does this). Test offline against replay simulator before deploying.
2. **Raise the effective gate when breakout is not confirming** (e.g., alpha-only requires composite ≥ 0.45 regardless of regime).
3. **Re-weight the composite** — the current 0.50 ML / 0.30 breakout / 0.20 tension assumes ML is the strongest signal. Given Anomaly 4 (corr ≈ 0), consider 0.20 / 0.50 / 0.30 or dynamic weighting that de-weights ML when composite-vs-ml_eff disagree by a threshold.

**My recommendation:** start with (1). Smallest code change, largest data support, easiest to reverse. (2) and (3) are follow-ons for the Exp 3/4/5 track.

---

## Anomaly 2 — Regime classifier stuck in chop

### The pattern in the data

Across ~8,465 logged organism ticks (log window ~Mar-Apr):

| Regime | Ticks | % |
|---|---|---|
| chop | 7,833 | 98.1% |
| trending_down | 58 | 0.7% |
| high_vol | 56 | 0.7% |
| stress | 18 | 0.2% |
| **trending_up** | **0** | **0.0%** |
| low_vol | 0 | 0.0% |
| unknown | ~500 | ~5% (startup / insufficient data) |

In a market that objectively did trend up (SPY ~+1% across many of these sessions), **not a single `trending_up` classification occurred in the entire log window**. That is not a market fact; that is a classifier fact.

### The mechanism in the code

From `regime.py` lines 100-180:

- `sma_period = 50 × 4 = 200` (scaled for intraday).
- `trend_slope = (last - first) / first` where first/last are the first and last values of the *last 10 values of the 200-bar SMA*.
- `_trend_threshold = 0.02 / sqrt(390)` ≈ **0.00102** (on disk: 0.0010127).
- Trending_up scores +2.0 if `trend_slope > _trend_threshold`.

**Why the threshold is effectively unreachable:** a 200-bar SMA is an extremely smooth series. If the underlying moves 1% quickly, the 200-bar SMA changes by roughly `(10 * 1-bar-return) / 200 ≈ 0.05%` across its last 10 values. To cross the 0.102% threshold, the underlying would need to sustain a very large (multi-percent) directional move, which is rare intraday. The code comment on lines 116-118 explicitly acknowledges this problem and the fix (divide by √bars_per_day) was insufficient.

The secondary trending signal (`pct_above = (close - sma) / sma > 0.02 × tf_scale`) has the same scaling issue. Price-vs-SMA threshold ≈ 0.1%, which intraday flat stretches rarely cross when using a 200-bar SMA as the reference.

### Impact

Because everything classifies as chop, the platform runs these settings *always*:

- Stop ATR = 2.5 (vs 3.5 for trending_up — stops ~30% tighter than they should be on a trend day)
- Position size scaler = 0.5 (vs 1.2 for trending_up — **sizing at 40% of trending-mode target**)
- Confidence gate = 0.45 defensive (vs 0.40 baseline)
- Exp 2 inverse-ETF chop suppression = always on
- Exp 1A chop min-hold pyramid_cut gate = always on

So even if we fix the composite gate (Anomaly 1), we're still running a chop-tuned strategy on every market, which is the wrong calibration for directional days.

### Fix candidates, ranked

1. **Replace the 200-bar SMA trend signal with a shorter timeframe** — e.g., 20-bar SMA slope measured over last 5 values, or a simple EMA crossover (12/26) against its own slope. Tuning target: trending_up fires 15-25% of the time on days SPY ends +0.5% or more.
2. **Multi-timeframe confirmation** — detect regime on 5-min or 15-min bars and inherit into the 1-min decisions. The 1-min "chop" might be noise around a 15-min trend.
3. **Use features we already have** — `realized_vol_5`, `atr_ratio`, `hurst_exponent` (already in the ML feature set) as direct inputs to regime probs. Current regime classifier uses `atr_ratio` and `returns_vol` but is dominated by the broken SMA slope.
4. **Empirical recalibration** — run a backtest over 60 days of 1-min bars and pick thresholds that produce a trending_up/chop/trending_down split matching the objective market classification from daily bars.

**My recommendation:** start with (1). Shortest path to a meaningful regime signal and it's a drop-in replacement. Needs an offline calibration run to pick the specific lookback/threshold.

---

## Anomaly 3 — ML calibration

### The data

| Metric | Value |
|---|---|
| n | 182 |
| mean(predicted_return) | +0.0036 |
| mean(actual_return) | −0.0004 |
| bias (pred − actual) | **+0.0040** |
| RMSE | 0.0070 |
| **corr(pred, actual)** | **+0.056** |

By predicted_return bucket:

| Bucket | n | avg_pred | avg_actual | Win rate |
|---|---|---|---|---|
| < 0.001 | 77 | +0.0007 | −0.0005 | 31.2% |
| 0.001 – 0.003 | 29 | +0.0014 | −0.0005 | 34.5% |
| 0.003 – 0.010 | 52 | +0.0043 | −0.0004 | 32.7% |
| **≥ 0.010** | **24** | **+0.0142** | **+0.0001** | **25.0%** |

### Interpretation

- Correlation 0.056 over 182 trades = essentially zero. **The ML signal as currently trained does not predict returns.**
- Systematic +0.4% long bias means the model has a positive-return prior independent of features.
- In the ≥1.0% predicted bucket — the trades the model feels *most confident* about — win rate drops to 25%. That's worse than the baseline 31% and suggests the tail predictions are capturing overfit / noise-driven signals that *anti-predict*.

### Why this matters for the composite gate

Anomaly 1 showed the gate keys off `ml_signal.effective_confidence`. Anomaly 3 shows that ML's self-confidence is uncorrelated with actual outcome. Together: **the gate variable is random noise, which is why 132 below-composite-threshold trades got through.**

### Fix candidates, ranked

1. **Drop ML signal weight in the composite to 0.0–0.2 until retrained with a better target.** Current production weight is 0.50; the data says that's overweighting noise. (Learning mode already does 0×ML; this is making production look more like learning mode.)
2. **Retrain on a different target** — current ML predicts `predicted_return` directionally; consider predicting `actual_return_given_entry_filter` (i.e., trained only on trades that would have passed the composite quality filter) to reduce distributional mismatch.
3. **Add an ML-confidence calibration gate** — require that ML self-confidence matches historical win-rate-at-that-confidence-level within tolerance, else reject. This is a form of isotonic calibration check.
4. **Ensemble / regime-conditional models** — once regime classifier works (Anomaly 2), train separate models per regime. The current single-model approach is fitting a chop-dominated sample which may be why tail predictions anti-predict.

**My recommendation:** start with (1) — a trivial config change with immediate effect. (2)–(4) are research tracks for the observation window and beyond.

---

## Anomaly 4 — Edge source (drift vs direction)

### Data: exit reason performance, per-share basis

| Exit reason | n | avg MFE | avg MAE | avg realized | MFE capture % | Total PnL |
|---|---|---|---|---|---|---|
| `max_holding_period` | 40 | +$5.39 | $4.10 | +$0.454 | **8.4%** | **+$138.67** |
| `take_profit` | 4 | +$9.44 | $2.79 | +$0.770 | 8.2% | +$19.27 |
| `ml_reversal` | 2 | +$1.17 | $1.09 | +$1.25 | 107% | +$2.50 |
| `eod_flatten` | 1 | +$7.44 | $3.49 | +$0.635 | 8.5% | +$7.62 |
| **WINNERS** | **47** | — | — | — | — | **+$168.06** |
| `trailing_stop` | 17 | +$4.55 | $3.65 | −$0.071 | −1.6% | −$10.14 |
| `failure_to_follow` | 22 | +$1.17 | $2.92 | −$0.190 | −16% | −$15.99 |
| `stop_loss` | 35 | +$1.25 | $1.48 | −$0.408 | −33% | −$67.75 |
| `reconciliation_adjustment` | 4 | $0.00 | $4.12 | −$1.570 | — | −$17.19 |
| `pyramid_cut` (all) | 57 | ~+$0.50 | ~$3.00 | ~−$0.50 | — | −$164.97 |
| **LOSERS** | **135** | — | — | — | — | **−$276.04** |

### What this says about edge

- **The primary earner is `max_holding_period`** — trades that just *timed out* at 30 bars. Not trades that hit take-profit. Not trades where the ML signal was right about direction. Just drift-capture within a stop-loss safety margin.
- **Take_profit captures 8.2% of MFE.** The take-profit level is set well inside the trade's maximum-favorable point, so on the rare occasions it hits, we're leaving substantial MFE on the table. This suggests take_profit levels are too tight OR partial-profit + ride the rest could improve this.
- **Trailing_stop loses nearly 100% of MFE** (captures −1.6%). This is the Exp 4 motivation — 3.0× ATR chop trail is too tight. Exp 4 widens to 5.0× ATR.
- **Pyramid_cut trades have tiny MFE** (mostly 0-1.5/share) and large MAE (2-4/share). These are positions that were never going our way; pyramid-sizing them up compounded the loss.
- **Stop_loss trades briefly favored, then reversed** — MFE $1.25, MAE $1.48. Classic "almost worked" pattern, consistent with no direction edge.

### Interpretation

The strategy does not appear to have a **directional edge** — ML has corr 0.056, and the majority of dollars come from timeouts (drift harvest) rather than targeted entries. It does have a **risk-control edge** — stops cap losers, max-hold lets drift-winners play out. That's why cumulative is only −$108 on 182 trades rather than multiples of that.

This is actually a reasonably clean structural picture: **we have infrastructure, not alpha.** The Stage 1 question is whether you can make money on drift harvest + disciplined exits against realistic transaction costs on tiny capital. The honest answer is: probably not at these parameters, but the gap to neutral is small (~−$0.6/trade) and Anomalies 1+2 together should close it.

### Fix candidates, ranked

1. **Fix Anomaly 1 + Anomaly 2** and observe whether max_holding_period's edge holds after composite-gate filtering.
2. **Tighten or drop the take_profit** — if we're only capturing 8% of MFE at take_profit, the rule is either noise or suboptimal. Partial profit + trail-the-rest is a classic improvement.
3. **Investigate pyramid entry triggers** — pyramid_cut trades had near-zero MFE, meaning we sized up on positions that never went favorable. The pyramid trigger is probably too permissive.

**My recommendation:** (1) first — if the bulk of losers disappear under composite-gating, pyramid_cut and stop_loss counts drop naturally. Then tackle (2) and (3) in the observation window.

---

## What this all adds up to

The platform does not have a "design to fail" — it has three specific, fixable issues:

1. **Gate variable mismatch** (composite vs ml_eff_conf) → 73% of trades below composite threshold → 98% of the loss
2. **Regime classifier wedged on chop** → always running defensive settings regardless of market
3. **ML signal essentially uncalibrated** → driving the broken gate above

These are not research questions. They are code-level findings with specific line numbers and specific data backing them. Fix them offline first (composite gate change is a one-line edit; regime threshold recalibration is ~2 lines; ML weight drop is a config constant), backtest against replay simulator, then propose as the next deploy candidate *after* `eb90fa3`.

## Pre-deploy judgment

**`eb90fa3` on Monday still goes.** None of these findings require patching before Monday. `eb90fa3` is safety-and-hardening (notional cap, daily max-loss, alert wiring, drawdown-kill canonicalization, G1/G2/G3 mechanical fixes, Exp 4 giveback control). Those are orthogonal to the composite-gate / regime-classifier / ML-calibration issues above. In fact, `eb90fa3`'s H2 feature drift guard will add a safety layer that helps in the exact scenario where ML is mis-calibrated.

**What CHANGES in the 14-day plan:**
- Track 1 (this report) supersedes the "Exp 3 execution variant" priority. The composite-gate finding is larger leverage than Exp 3 and testable offline immediately.
- Post-eb90fa3 observation week-1 target list should add: "diff composite vs ml_eff_conf per entry in live telemetry" so we can see how often the two disagree.
- Next-deploy RC should bundle a **composite-gate fix + regime-threshold recalibration + ML weight drop** as one coherent RC-2.

## Open questions for you (partner-mode)

1. **Gate fix urgency.** The composite-gate mismatch could be back-patched onto `eb90fa3` before Monday as a one-line edit. I would not do that because: it's not tested, we've told ourselves "no code changes this weekend," and it's a behavior change that should be observed in isolation not mixed with the hardening bundle. But you might weigh "we're knowingly shipping a known losing gate Monday" differently. **Do you want me to leave this for RC-2 post-observation (my default), or do you want to talk about inlining it?**
2. **Regime fix scope.** My instinct is to replace the SMA-slope trend signal with a 20-bar EMA cross. That's a bigger change (new code path) and will change the regime distribution meaningfully. Alternative is to just lower the threshold further by another ~3x. **Do you want the bigger redesign, or the conservative threshold adjustment, or both ranked for offline test?**
3. **ML weight decision.** Dropping ML to 0.2 in composite is a clear data-supported step, but we've been retraining ML every ~200 trades with the current target. Changing the weight changes what sample future retrains see. **Do you want to (a) drop weight now, (b) retrain on filtered sample first, then adjust weight?**

Nothing about these questions blocks Monday. They shape RC-2.
