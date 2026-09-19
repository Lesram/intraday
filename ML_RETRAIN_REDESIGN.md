# ML Retraining Pipeline — Redesign Notes

**Status:** DESIGN — RC-3+ candidate, multi-week implementation
**Author:** Saturday 2026-04-25 weekend sprint, S11
**Builds on:** Track 1 (corr=0.056), Data Leakage Audit (apples-to-oranges comparison flagged)

## The problem

Track 1 found `corr(predicted_return, actual_return) = 0.056` over 182 live trades. Effectively zero. The classifier produces direction predictions and the regressor produces magnitude predictions, but neither correlates with realized outcomes.

Possible causes (not mutually exclusive):
1. **Target is too noisy.** We predict `(close[t+H] - close[t]) / close[t]` where H=1. 1-bar forward returns on 1-min equities are dominated by microstructure noise; the signal-to-noise ratio is too low for our current features.
2. **Training sample is contaminated by entry-quality bias.** We train on ALL bars (every bar gets an X/y pair), but the model is USED only on bars where alpha+breakout fired. The training distribution isn't matching the inference distribution.
3. **Model selection is permissive.** The acceptance gate (`continuous_learner._validate_new_model`) compares new vs old metrics from DIFFERENT validation periods (apples-to-oranges, see Data Leakage Audit). Weak models can pass.
4. **Feature space is wrong.** 79 features, mostly conventional technicals. Same as everyone else.
5. **No regime conditioning.** One model for all regimes. Trending vs chop call for different feature relationships, and we're not letting the model learn that.

## Redesign principles

### 1. Train on the population we'll evaluate on

Currently: train on every bar of every symbol (`_build_training_data` produces ~2000 rows per symbol). Inference happens only on bars where alpha+breakout fired (~5-15 entries per session).

**Problem**: the model learns the average bar's behavior, then we ask it to predict on a self-selected population (high-breakout, high-tension bars).

**Fix**: filter training data to bars that *would have been* candidate entries (breakout >= 0.4 OR alpha rank in top-5). Reduces training set ~10× but matches the inference distribution.

### 2. Predict the right target

Currently: `y = (close[t+H] - close[t]) / close[t]` where H=1 (next bar return).

**Problem**: a 1-bar return is mostly noise. Even if the model is perfect, the realized 1-bar return is dominated by random walk noise, not predictable signal.

**Fix candidates** (rank by likely improvement):
- (a) **Predict the trade outcome we'll actually realize**: `y = (exit_price - entry_price) / entry_price` for trades that fired. Conditional on trade being taken. Smaller training set, but the right thing.
- (b) **Predict longer-horizon return**: H = 5 or 10 bars. Reduces noise. But also reduces granularity.
- (c) **Predict direction only** (binary classification): `y = (close[t+H] > close[t])`. Already done; but coupled with regression in our pipeline. Maybe direction-only is enough.
- (d) **Predict the next favorable excursion** (not realized return): `y = max(close[t:t+H]) - close[t]` for longs. Captures "will this bar lead to favorable movement at any point in the next H bars" — more informative for entry decisions.

### 3. Same-holdout fair comparison

(From Data Leakage Audit Concern 1.) When validating retrained models, evaluate BOTH new and old on the SAME concurrent holdout. Don't compare new-on-new-validation vs old-on-old-validation.

### 4. Regime-conditional ensemble

Once the regime classifier fix lands (RC-2), train SEPARATE models per regime:
- One model for trending_up bars
- One model for chop bars
- One model for trending_down

Each gets its own training data filtered to its regime. Each gets its own acceptance gate. At inference, regime decides which model to use.

This is `Phase C-2` adjacent — needs the regime classifier working first.

### 5. Feature pruning

Current: 79 features, many likely uncorrelated with target. Train a baseline model, dump feature importances, drop bottom-half. Keep top 30-40 features.

Reduced model:
- Faster to train and infer
- Less overfit risk
- Cleaner interpretation

### 6. Prediction calibration

Current: `predicted_return` is the regressor output, raw. We saw +0.4% systematic long bias in Track 1.

**Fix**: post-hoc calibrator that learns `actual = a*predicted + b` on validation data. Subtract the bias. Adjust the variance.

This is Platt scaling / isotonic regression for the regressor. Common in ML production pipelines, not currently implemented.

## Migration plan (sketch — RC-3 to RC-6)

| Stage | Change | Validation |
|---|---|---|
| RC-3a | Train on candidate-bars-only (filtered training set) | Replay backtest: new model on filtered training vs old model. Same holdout. |
| RC-3b | Add prediction-calibrator to regressor (subtract bias) | Replay backtest: with vs without calibrator. |
| RC-4 | Same-holdout new-vs-old in `_validate_new_model` | Unit tests + replay. |
| RC-5 | Try direction-only model (drop regressor) | Replay A/B. |
| RC-6 | Regime-conditional ensemble (after regime fix lives) | Replay A/B per regime. |
| RC-7+ | Try alternative target (favorable-excursion, longer horizon) | Replay A/B. |

Each stage is a self-contained PR with replay validation. We learn from each one before moving on.

## Why not now

This is genuinely multi-week work. The training pipeline touches:
- `ml_features.py` (feature pruning)
- `ml_signal.py` (target definition, calibration)
- `continuous_learner.py` (acceptance gate)
- `walk_forward.py` (proper out-of-sample evaluation)
- `background_trainer.py` (regime conditioning)
- All training-related tests

Each stage needs replay validation, which takes ~1 hour of compute per A/B comparison. So: ~5 stages × ~3-4 days each = 3-4 weeks of focused work, longer if interleaved with other priorities.

## Honest expectation-setting

The redesign doesn't guarantee profitability. It may move ML correlation from 0.056 to 0.10-0.20 in the best case. That's a 2-4× improvement in signal, but if the underlying market structure doesn't have predictable intraday alpha at our universe and timeframe, even a perfectly calibrated model won't make money.

The composite-gate fix in RC-1.5 attacks the immediate harm (ML noise admitting bad entries). The regime + ML-weight fixes in RC-2 reduce ML's influence further. **These fixes can stop the bleeding even if the ML pipeline is fundamentally limited.**

Real-money decisions should rest on the gate fixes + risk hardening + observation, not on speculative ML retraining gains.

## Recommendation

**Do not attempt ML retrain redesign before RC-1.5 + RC-2 are stable in live.** The right sequence:

1. RC-1.5 deploys Monday. Observe 5+ sessions.
2. RC-2 deploys (after shadow validation of regime + ML weight).
3. Observe RC-2 for 5+ sessions. Confirm pyramid_cut share dropped.
4. Stage-1 tiny capital decision based on 1-2 above.
5. THEN if we want to extract more juice: RC-3 starts the ML retrain redesign.

This staging matters. We don't want to optimize a model that's about to be filtered out by a better gate, or vice-versa.
