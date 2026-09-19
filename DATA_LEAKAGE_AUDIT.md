# Data Leakage Audit — ML Pipeline (S6)

**Run:** 2026-04-25 weekend sprint
**Branch:** `rc-1.5-curated`
**Scope:** `backend/organism/ml_features.py`, `ml_signal.py`, `training.py`, `walk_forward.py`, `continuous_learner.py`, `background_trainer.py`, `ensemble_models.py`
**Audit type:** static code review, grep-based pattern scan, control-flow trace

**Bottom line: no critical leakage found. One medium-severity methodological issue (apples-to-oranges model comparison) and three low-severity items worth flagging.** The most dangerous categories — look-ahead bias in features, train/test data leakage, normalization leakage — are all clean.

---

## Categories audited

| Category | Risk if violated | Status |
|---|---|---|
| **Look-ahead bias in features** | Catastrophic — model learns "future" | ✅ CLEAN |
| **Train/test data overlap** | Inflated validation metrics, no real generalization | ✅ CLEAN |
| **Normalization fitting on full data** | Validation set leaks into preprocessing | ✅ CLEAN (no normalizer used) |
| **Cross-symbol leakage** | Cross-sectional pattern fitting confused with edge | ⚠️ INTENTIONAL (not leakage; flagged for clarity) |
| **Old/new model comparison fairness** | Weak new models pass acceptance gate | ⚠️ MEDIUM — apples-to-oranges issue |
| **Drift detection threshold** | Over/under-frequent retrains | ⚠️ LOW — PSI threshold 0.10 is aggressive |
| **Survivorship bias in symbol set** | Model only learns from "winners" | ✅ N/A — universe is fixed at runtime |

---

## ✅ CLEAN: No look-ahead bias in features

`backend/organism/ml_features.py` — module-level docstring asserts "No lookahead" and the implementation matches:

- All `.shift(N)` calls use **positive N** (past bars). Grep confirms zero instances of `shift(-`.
- All `.rolling()` calls use the default left-anchored window. No `center=True` (which would use future bars). Grep confirms zero instances.
- All `pct_change(N)` calls compute current-vs-N-bars-ago — past only.
- No `iloc[start:]` slicing that reaches into a future window.

**Verification:**
```
$ grep -nE "shift\(-|center=True" backend/organism/ml_features.py
(no matches)
```

Cross-asset features (rel_strength_spy, beta, etc., lines 218-260) use SPY data. The slicing `spy_c = spy_df["close"].iloc[-len(df):]` takes the **last N rows** of SPY — past data only, ending at the same bar as the symbol df. See Concern 2 below for an alignment caveat.

## ✅ CLEAN: No train/test leakage in `_temporal_split`

From `ml_signal.py:692-720`:

```
Each symbol's chunk is split independently: first (1 - val_ratio)
bars go to train, the rest to validation.  This ensures no future
data from any symbol leaks into the training set.
```

Implementation:
- `_build_training_data` stores `_chunk_sizes` (one per symbol).
- `_temporal_split` walks each chunk separately, assigns first 80% to train, last 20% to validation.
- No shuffling. No random selection. No future bars in train.

This is the right pattern for time-series cross-validation when stacking multiple symbols.

## ✅ CLEAN: No normalization-based leakage

```
$ grep -nE "fit_transform|StandardScaler|MinMaxScaler|RobustScaler|preprocessing" \
        backend/organism/ml_signal.py backend/organism/training.py \
        backend/organism/walk_forward.py backend/organism/continuous_learner.py \
        backend/organism/background_trainer.py backend/organism/ensemble_models.py
(no matches)
```

The pipeline trains tree-based models (sklearn `RandomForestClassifier` / `GradientBoostingClassifier` / `XGBoost`) directly on raw features after `np.nan_to_num`. Tree-based models are scale-invariant by design — no normalization required, no normalization-based leakage possible.

If we ever add a neural-network or distance-based model (KNN, SVM, MLP) we'd need to add a `Pipeline([('scaler', StandardScaler()), ('model', X)])` so scaling fits on train only. **Not a current risk, but a design constraint to remember.**

## ⚠️ MEDIUM: Apples-to-oranges old/new model comparison in `_validate_new_model`

Location: `backend/organism/continuous_learner.py:432-456`.

When the system retrains:
1. New model trains on data up to T_now, validates on its own internal 20% (which ends at T_now).
2. Old model has previously-stored metrics computed at T_old, on the validation period that ended at T_old (different time window).
3. Acceptance gate compares: "new model's metrics on T_now-validation" vs "old model's metrics on T_old-validation".

**Problem**: a weak new model trained in an "easy" market period could pass the gate just because the validation window was easier. There's no apples-to-apples comparison.

**Why this isn't strict leakage**: no future data leaks into the new model's training. The new model is honestly evaluated on its own holdout. But the **comparison standard** is unfair.

**The right fix**: when validating, evaluate BOTH new and old on the SAME holdout window (the recent N bars). `walk_forward.py` does this rigorously, but the docstring notes "walk_forward is OFFLINE-ONLY... not used in the live model promotion path."

**Recommendation**: in RC-2 or RC-3, add a same-holdout comparison step to `_validate_new_model`:
```
holdout_X, holdout_y = build_recent_holdout(features, last_N_bars=200)
new_score = score_on_holdout(new_clf, holdout_X, holdout_y)
old_score = score_on_holdout(old_clf, holdout_X, holdout_y)
return new_score > old_score * (1 + improvement_threshold)
```

**Severity**: medium. Doesn't break correctness; allows occasional weak-model promotions.

**Connection to Track 1**: this could partially explain `corr(predicted, actual) = 0.056` — if the gate has been letting through models that were merely "lucky on their own validation," the running model in production may not be the best one we've trained.

## ⚠️ LOW: SPY alignment for cross-asset features

Location: `ml_features.py:219`:
```
if spy_df is not None and "close" in spy_df.columns and len(spy_df) >= len(df):
    spy_c = spy_df["close"].iloc[-len(df):].values
```

Assumes the **last bar of SPY corresponds to the last bar of df**. True if both are pulled from the same time window, false if they're misaligned (one stale, one fresh).

The live engine pulls all bars from Alpaca at the same tick, so alignment should hold in practice. But the function lacks an explicit timestamp-equality assertion.

**Severity**: low. Worth a defensive check: assert SPY.timestamp[-1] == df.timestamp[-1] (or within 1 minute) and warn-log otherwise. **One-line guard, RC-3 candidate.**

## ⚠️ LOW: Drift detection threshold

`continuous_learner.py:227`:
```
drift_threshold: float = 0.10,    # PSI threshold for drift
```

Industry-standard PSI buckets:
- < 0.10: no drift
- 0.10 – 0.25: moderate drift, monitor
- > 0.25: significant drift, retrain

Using **0.10 as the trigger** is on the aggressive side. May cause more retrains than needed.

**Live evidence**: `learning_state.json` shows `drift_events = 0` over 124 generations / 1300 runs, suggesting drift detection is rarely if ever firing in practice. The aggressive threshold isn't actually causing problems because the feature distribution is genuinely stable on this universe over short windows.

**Severity**: low. Note for the future: if we expand to less-stable assets or longer training windows, may want to revisit.

## ⚠️ INTENTIONAL (flagged for clarity, not leakage): Cross-symbol training set

`_build_training_data` stacks all 22 symbols' bars into one matrix. The model trains on this combined matrix and learns cross-sectional patterns (e.g., "when SPY moves up, NVDA tends to follow").

**This is by design** — the platform is intentionally a cross-sectional model. But it does mean:
- Validation set contains samples from all 22 symbols at the same time periods as training samples (different periods, same calendar dates).
- The cross-sectional regime captured at training time persists into validation, which can inflate apparent generalization to genuinely new market regimes.

**Mitigation**: per-symbol temporal split is correct. The model legitimately can't see a symbol's future from any source. But the validation period is small (last 20% of each chunk = last few weeks of each symbol's data) and shares calendar time with the training data of OTHER symbols.

**Severity**: not leakage in the strict sense, but worth being aware of when interpreting validation metrics.

## Connection to user's "horrible past experiences"

User flagged past backtest pain. The most common backtest failure modes I checked for:

| Past trap | Status here |
|---|---|
| Future bars in features | ✅ Clean |
| Random train/test split on time series | ✅ Clean (per-symbol temporal split) |
| Scaler fit on full data | ✅ Clean (no scaler) |
| Survivorship bias | ✅ N/A (fixed universe) |
| Compare strategies on different time windows | ⚠️ Apples-to-oranges issue noted |
| In-sample parameter tuning | ⚠️ Acceptance gate only checks against past metrics, not concurrent holdout |
| Fitting to backtest output | ⚠️ Track 1 fixes were designed FROM live data; risk of overfit to past 12 sessions. The replay null-result actually de-risks this concern. |

## Recommendations

| Item | Priority | When |
|---|---|---|
| Same-holdout new-vs-old model comparison in `_validate_new_model` | P1 | RC-3 candidate (after RC-1.5 + RC-2 ship) |
| SPY-alignment defensive check in `ml_features.py:219` | P2 | RC-3 |
| Document drift-threshold rationale | P3 | Comment in `continuous_learner.py:227` |
| Add a unit test asserting `_build_training_data` produces no negative-shift columns | P3 | RC-3 hardening |
| **Don't add features that use `shift(-N)`, `center=True` rolling, or `iloc[i+1:]` patterns** | P0 (always) | Code review checklist |

## Verdict

**Pipeline is fundamentally sound on leakage.** No critical findings. The single medium-severity item (apples-to-oranges comparison) is a methodology improvement, not a correctness bug. Real-money readiness is not blocked by anything in this audit.
