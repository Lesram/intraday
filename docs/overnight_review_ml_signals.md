# Overnight Code Review: ML Signals & Position Sizing Pipeline
**Date:** 2026-02-22 | **Scope:** Pre-launch paper trading audit  
**Reviewed Files:**
- `backend/organism/ml_signal.py` (591 lines)
- `backend/organism/alpha_scanner.py` (267 lines)
- `backend/organism/breakout_scanner.py` (478 lines)
- `backend/organism/kelly_sizer.py` (391 lines)

---

## CRITICAL FINDINGS

### 1. ML SIGNAL GENERATION (`ml_signal.py`)

#### [CRITICAL] Untrained Model Prediction Returns Zero (Line 262)
**File:** `backend/organism/ml_signal.py:249-262`
```python
def predict(self, features_df: pd.DataFrame, symbol: str = "") -> MLSignal:
    if not self._is_trained:
        return MLSignal(symbol=symbol, direction=0, confidence=0, predicted_return=0)
```

**Risk:** When the engine first starts (`ml_trained=False`), ALL predictions return neutral signals (direction=0, confidence=0, predicted_return=0). This is safe for the first tick, but:
- **First tick behavior**: No ML signals generated → Alpha scanner receives empty signals → Candidates scored only on breakout + momentum
- **Expected**: Acceptable; breakout scanner provides fallback
- **Mitigation in place**: ✓ Breakout scanner independence confirmed

**Classification:** INFO (acceptable startup behavior)

---

#### [WARNING] Feature Column Mismatch Silently Degrades Predictions (Line 265-275)
**File:** `backend/organism/ml_signal.py:264-275`
```python
available_cols = [c for c in self._feature_cols if c in features_df.columns]
if not available_cols:
    return MLSignal(symbol=symbol, direction=0, confidence=0, predicted_return=0)

if len(available_cols) < len(self._feature_cols):
    logger.warning(
        "Feature column mismatch for %s: %d/%d available — predictions may degrade",
        symbol, len(available_cols), len(self._feature_cols),
    )
```

**Issue:** 
- If feature computation drops required columns (e.g., due to SPY data unavailability), model silently predicts neutral
- No exception raised; log message only (WARNING level)
- Could happen if `spy_df=None` passed to `compute_ml_features()` (lines 217-250 in ml_features.py)

**Impact:** 
- Alpha scanner receives 0-confidence ML signals for ALL symbols if 5 cross-sectional features fail
- Candidates rely entirely on breakout_score + momentum

**Recommendation:** MONITOR in production; add metric to track feature availability per symbol

**Classification:** WARNING (gracefully handled but silent degradation)

---

#### [CRITICAL] Confidence Calibration Can Over-Correct (Line 351-364)
**File:** `backend/organism/ml_signal.py:351-364`
```python
def update_calibration_map(self) -> None:
    """Recompute calibration multipliers from accumulated outcomes."""
    for i in range(5):
        total = self._calibration_counts[i][1]
        if total < 10:
            self._calibration_map[i] = 1.0  # Not enough data
            continue
        actual_rate = self._calibration_counts[i][0] / total
        bin_midpoint = (i * 0.2 + (i + 1) * 0.2) / 2
        if bin_midpoint < 0.01:
            self._calibration_map[i] = 1.0
        else:
            self._calibration_map[i] = min(actual_rate / bin_midpoint, 2.0)
```

**Issue:**
- `bin_midpoint` formula is **mathematically incorrect**
  - For bin i=0: `(0 * 0.2 + 1 * 0.2) / 2 = 0.1` ✓ (correct for [0.0-0.2] → 0.1)
  - For bin i=4: `(4 * 0.2 + 5 * 0.2) / 2 = 0.9` ✗ (should be 0.9, is actually 0.9) — ACTUALLY correct
  - **Recalculation**: The formula `(i*0.2 + (i+1)*0.2) / 2` simplifies to `(2i+1)*0.1`, which is correct

**Actual Issue Found:**
- If actual_rate > bin_midpoint (model overconfident), multiplier caps at 2.0 (line 364)
- If calibration data skewed (e.g., bin 4 had only lucky wins), multiplier → 2.0, doubling confidence
- **Example**: Bin 4 (high confidence): 8/10 correct (80%), but bin_midpoint=0.9 → multiplier = min(0.8/0.9, 2.0) = 0.889 (downweighted)
  - Safe for this case, but if 10/10 correct: multiplier = min(1.0/0.9, 2.0) = 1.111 (slightly up-weighted)

**Re-assessment:** Calibration is defensible; cap at 2.0 prevents runaway confidence boost. Acceptable.

**Classification:** INFO (correctly implemented with safety bounds)

---

#### [WARNING] Ensemble Blend Failure Silent (Line 297-305)
**File:** `backend/organism/ml_signal.py:297-305`
```python
if self._ensemble is not None and self._ensemble.is_trained:
    try:
        ens_p_up, ens_ret = self._ensemble.predict(X)
        p_up = 0.6 * p_up + 0.4 * ens_p_up
        pred_return = 0.6 * pred_return + 0.4 * ens_ret
    except Exception:
        pass  # Fall back to primary model
```

**Issue:**
- Exception in ensemble prediction silently ignored (bare `except Exception`)
- Could hide:
  - Shape mismatches in ensemble input
  - Model corruption
  - Memory issues
- No logging; silent fallback to primary model

**Impact:** Model degradation undetected in production

**Recommendation:** Add `logger.warning()` to ensemble failure

**Classification:** WARNING (silent failure detection gap)

---

#### [INFO] Training Data Lookahead Correctly Prevented (Line 454-475)
**File:** `backend/organism/ml_signal.py:437-492`

✓ **Correctly implemented:**
- Features use only bars [:-1] (current bar only, next bar is target)
- Per-symbol temporal split prevents cross-symbol leakage
- Next-bar close used for target (correct lookahead window)
- Extreme returns clipped to [-0.5, 0.5] to prevent outlier distortion

**No issues found**

---

#### [INFO] Time-Decay Weighting Correct (Line 390-402)
**File:** `backend/organism/ml_signal.py:389-402`

✓ **Correctly implemented:**
- Exponential decay: `w_i = exp(-decay_rate * (n - 1 - i))`
- Normalized by mean (preserves effective sample size)
- Monotonically increasing weights (newest bars highest)
- Test coverage confirms 2-5x weight ratio for 250-bar window

**No issues found**

---

#### [WARNING] Direction Probability Edge Case (Line 284-289)
**File:** `backend/organism/ml_signal.py:283-289`
```python
dir_proba = self._clf.predict_proba(X)[0]
# dir_proba = [P(down), P(up)]
p_up = dir_proba[1] if len(dir_proba) > 1 else dir_proba[0]
```

**Issue:**
- Assumes 2-class output; if model predicts only 1 class (e.g., only saw "up" moves during training), `dir_proba` has length 1
- Fallback to `dir_proba[0]` would give P(down) = 100%, forcing direction = -1.0
- Unlikely but possible in early training with limited data

**Impact:** Forced short signal if training data is one-sided; would violate LONG_ONLY=true constraint downstream

**Recommendation:** Add explicit guard:
```python
if len(dir_proba) != 2:
    logger.warning("Model returned %d class probabilities — defaulting to neutral", len(dir_proba))
    p_up = 0.5
else:
    p_up = dir_proba[1]
```

**Classification:** WARNING (edge case in early training)

---

---

## ALPHA SCANNER (`alpha_scanner.py`)

### [INFO] Weight Sum Verification (Line 68-74)
**File:** `backend/organism/alpha_scanner.py:68-74`
```python
WEIGHT_ML = 0.25
WEIGHT_BREAKOUT = 0.20
WEIGHT_INSTITUTIONAL = 0.15
WEIGHT_MOMENTUM = 0.15
WEIGHT_MOM_QUALITY = 0.10
WEIGHT_VOLUME = 0.10
WEIGHT_REGIME = 0.05
```

**Verification:** 0.25 + 0.20 + 0.15 + 0.15 + 0.10 + 0.10 + 0.05 = **1.0** ✓

**Classification:** INFO (weights correctly sum to 1.0)

---

### [CRITICAL] Composite Score Can Exceed 1.0 (Line 169-188)
**File:** `backend/organism/alpha_scanner.py:169-188`
```python
composite = (
    self.WEIGHT_ML * ml_score
    + self.WEIGHT_BREAKOUT * breakout_score
    + self.WEIGHT_INSTITUTIONAL * inst_score
    + self.WEIGHT_MOMENTUM * momentum_score
    + self.WEIGHT_MOM_QUALITY * mom_quality
    + self.WEIGHT_VOLUME * volume_score
    + self.WEIGHT_REGIME * regime_score
)

# If ML says hold, penalize heavily
if direction == 0:
    composite *= 0.3

# Symbol fitness: evolved from historical performance
if hasattr(self, "_symbol_fitness") and self._symbol_fitness:
    fitness = self._symbol_fitness.get(symbol, 0.5)
    # Scale: 0.5 = neutral, >0.5 = boost, <0.5 = penalize
    composite *= 0.5 + fitness  # range [0.6, 1.45]
```

**Issue:**
- If all 7 factors = 1.0, composite = 1.0 ✓
- Symbol fitness multiplier: `0.5 + fitness`
  - If fitness=1.0 (best symbol), multiplier=1.5 → composite can reach **1.5** (50% over cap)
  - If fitness=0.0 (worst symbol), multiplier=0.5 → composite can reach **0.5**
- **Risk**: Scores >1.0 violate semantic assumption of [0,1] range
- Passed to Kelly sizer's `breakout_score` field; no clip at upper bound

**Impact:**
- Kelly sizer receives `breakout_bonus(1.5)` → returns 2.0 (max bonus)
- Position sizes up to **2.0x** half-Kelly (vs expected 1.5x cap)

**Recommended fix:**
```python
composite = min(composite, 1.0)  # After fitness multiplier
```

**Classification:** CRITICAL (violates scoring invariant, can cause oversizing)

---

### [CRITICAL] NaN Guard Incomplete on `institutional_score` (Line 162)
**File:** `backend/organism/alpha_scanner.py:160-166`
```python
ml_score = ml_score if np.isfinite(ml_score) else 0.0
breakout_score = breakout_score if np.isfinite(breakout_score) else 0.0
inst_score = inst_score if np.isfinite(inst_score) else 0.5  # <-- DEFAULT 0.5
momentum_score = momentum_score if np.isfinite(momentum_score) else 0.5
mom_quality = mom_quality if np.isfinite(mom_quality) else 0.5
volume_score = volume_score if np.isfinite(volume_score) else 0.0
regime_score = regime_score if np.isfinite(regime_score) else 0.5
```

**Issue:**
- `inst_score` defaults to **0.5** (neutral), but other scores default to 0.0 or 0.5 inconsistently
- If `comp_institutional_acc` missing from row (line 132), defaults to 0.5
- **Why inconsistent?** Unclear intent; should all score-generating features have same default policy

**Impact:** Candidates with missing institutional data get boosted by 0.15 * 0.5 = 0.075 automatically

**Recommended fix:**
```python
# All missing score factors should default to 0.5 (neutral)
inst_score = inst_score if np.isfinite(inst_score) else 0.5
ml_score = ml_score if np.isfinite(ml_score) else 0.5  # was 0.0
volume_score = volume_score if np.isfinite(volume_score) else 0.5  # was 0.0
```

**Classification:** CRITICAL (inconsistent handling of missing data)

---

### [INFO] Symbol Fitness Edge Case Handled (Line 185-188)
**File:** `backend/organism/alpha_scanner.py:185-188`
```python
if hasattr(self, "_symbol_fitness") and self._symbol_fitness:
    fitness = self._symbol_fitness.get(symbol, 0.5)
    composite *= 0.5 + fitness  # range [0.6, 1.45]
```

**Verification:**
- If `_symbol_fitness` not set, fitness defaults to 0.5 (neutral multiplier 1.0) ✓
- If symbol not in fitness dict, defaults to 0.5 ✓
- Graceful fallback confirmed

**Classification:** INFO (correctly handled)

---

### [INFO] Momentum Ranking Edge Case (Line 238-240)
**File:** `backend/organism/alpha_scanner.py:219-240`
```python
sorted_syms = sorted(mom_values.keys(), key=lambda s: mom_values[s])
n = len(sorted_syms)
return {sym: (i / max(n - 1, 1)) for i, sym in enumerate(sorted_syms)}
```

**Edge case: All symbols identical returns**
- Example: All symbols have `ret_20d = 0.05`
- After sorting, ranking is arbitrary (depends on dict sort order)
- Each symbol still gets unique rank in [0, 1]
- **Safe**: No division by zero; no NaN production

**Classification:** INFO (safe edge case handling)

---

---

## BREAKOUT SCANNER (`breakout_scanner.py`)

### [WARNING] Volume Surge Division-by-Zero Risk Mitigated But Unclear (Line 275-297)
**File:** `backend/organism/breakout_scanner.py:275-297`
```python
def _volume_surge(self, volume: np.ndarray) -> tuple[float, float]:
    vol_period = self.VOL_AVG_PERIOD
    needed = vol_period + 5
    if len(volume) < needed:
        return 0.0, 1.0
    
    avg_vol = np.mean(volume[-needed:-5])  # N-bar avg excluding last 5
    if avg_vol < 1:
        return 0.0, 1.0
    
    recent_max_vol = np.max(volume[-3:])
    vol_ratio = float(recent_max_vol / avg_vol)
    
    score = min(max((vol_ratio - 1.0) / 4.0, 0.0), 1.0)
    return score, vol_ratio
```

**Issue:**
- Guard against `avg_vol < 1` (line 287) prevents division by zero ✓
- But comment says "N-bar avg excluding last 5" — why exclude last 5 bars?
  - Intent seems to be: avoid recency bias by using historical avg vs very recent surge
  - But if last 3 bars have surge AND last 5 bars excluded, ratio can be artificially high
  - Example: avg_vol from bars 1-20 = 1M, recent max (bars -3 to -1) = 5M → ratio = 5.0 (max score = 1.0)

**Clarity**: Logic is sound (intentional lag to avoid false signals), but comment needs clarification

**Classification:** INFO (safe but could use clarification)

---

### [CRITICAL] Squeeze Detector False Positives Possible (Line 265-273)
**File:** `backend/organism/breakout_scanner.py:232-273`
```python
squeeze_fired = was_squeezed and is_expanding and percentile < 0.35
```

**Conditions for `squeeze_fired = True`:**
1. `was_squeezed = bb_width[-5] < kc_width[-5]` (5 bars ago)
2. `is_expanding = bb_width[-1] > bb_width[-3]` (now expanding vs 3 bars ago)
3. `percentile < 0.35` (current width in lowest 35% historically)

**Issue:**
- Conditions 1 & 2 use different lookback windows (5 bars vs 3 bars vs 120-bar history)
- `percentile < 0.35` means "tightest 35% of recent widths" — NOT the absolute tightest squeeze
- **False positive scenario:**
  - Volatility regime shift: BBands widen, then contract back to "normal" (35th percentile)
  - Market sees this as squeeze firing → breakout expected
  - But it's just mean reversion to normal regime

**Impact:** Can generate false squeeze signals in choppy/range-bound markets

**Mitigation in place:**
- Squeeze weight = 25% of composite (line 73)
- Squeeze must combine with volume surge + pivot breakout to generate candidate
- MIN_SQUEEZE_FIRE threshold (line 81)

**Recommendation:** Add regime check — only fire squeeze in trending regimes (ADX > 25)

**Classification:** WARNING (false positive risk, partially mitigated by composite scoring)

---

### [INFO] Range Contraction Correctly Bounded (Line 299-318)
**File:** `backend/organism/breakout_scanner.py:299-318`
```python
def _range_contraction(self, high: np.ndarray, low: np.ndarray, close: np.ndarray) -> float:
    atr_short = self._atr(high, low, close, self.ATR_SHORT)
    atr_long = self._atr(high, low, close, self.ATR_LONG)
    
    if atr_long < 1e-10:
        return 0.0
    
    ratio = atr_short / atr_long
    score = max(1.0 - ratio, 0.0)
    
    return min(score, 1.0)
```

**Verification:**
- Score = 1 - (ATR_SHORT / ATR_LONG), always in [0, 1] ✓
- Guards against atr_long < 1e-10 ✓
- No risk of negative or NaN values

**Classification:** INFO (correctly implemented)

---

### [CRITICAL] Relative Strength Ranking Identical Returns Edge Case (Line 381-400)
**File:** `backend/organism/breakout_scanner.py:381-400`
```python
def _compute_rs_ranks(self, data_by_symbol: dict[str, pd.DataFrame]) -> dict[str, float]:
    """Cross-sectional relative strength rank [0,1]."""
    returns_nd: dict[str, float] = {}
    rs_lb = self.RS_PERIOD
    
    for symbol, df in data_by_symbol.items():
        if symbol == "SPY" or len(df) < rs_lb + 5:
            continue
        close = df["close"].values
        ret = (close[-1] - close[-(rs_lb + 1)]) / close[-(rs_lb + 1)] if close[-(rs_lb + 1)] > 0 else 0
        returns_nd[symbol] = ret
    
    if not returns_nd:
        return {}
    
    sorted_syms = sorted(returns_nd.keys(), key=lambda s: returns_nd[s])
    n = len(sorted_syms)
    return {sym: i / max(n - 1, 1) for i, sym in enumerate(sorted_syms)}
```

**Edge case: All symbols identical returns**
- If all returns = 0.05, sorted order is arbitrary (stable sort on dict keys)
- Each symbol gets unique rank, but ranking is non-deterministic
- **Example**: Symbols [AAPL, MSFT, TSLA] all return 5%
  - AAPL → rank 0 (0.0)
  - MSFT → rank 1 (0.5)
  - TSLA → rank 2 (1.0)
  - Or vice versa (depends on dict iteration order, Python 3.7+ insertion order)

**Impact:**
- When market is sideways (all symbols similar returns), RS scores are arbitrary
- Could favor alphabetically-first symbols over fundamentally better ones
- All get breakout candidates generated stochastically

**Recommendation:** Add tie-breaking by volume or volatility for identical returns

**Classification:** WARNING (non-deterministic ranking in tied scenarios)

---

### [INFO] Pivot Breakout ATR Guard (Line 340-342)
**File:** `backend/organism/breakout_scanner.py:320-361`
```python
atr = self._atr(high, low, close, 14)
if atr < 1e-10:
    return 0.0, 0.0
```

✓ **Guards against division by zero correctly**

**Classification:** INFO (safe)

---

### [WARNING] Insufficient Historical Data Grace Period (Line 162-163)
**File:** `backend/organism/breakout_scanner.py:162-163`
```python
if len(close) < 50:
    return None
```

**Issue:**
- Requires 50 bars minimum for scoring
- But BB period = 20, ATR periods = 10/50, pivot lookback = 20
- **First 60+ ticks** (10 minutes @ 1-min bars) — no breakout candidates generated
- Safe for production (intraday shouldn't trade in first 10 min of market open anyway)

**No critical risk, but could add startup logging**

**Classification:** INFO (acceptable warmup period)

---

---

## KELLY SIZER (`kelly_sizer.py`)

### [CRITICAL] Zero Predicted Return + Breakout Score Creates Ambiguity (Line 141-145)
**File:** `backend/organism/kelly_sizer.py:141-145`
```python
# Floor predicted_return: when ML is untrained, breakout signals
# arrive with predicted_return=0. Use a conservative default so
# the sizer can still allocate based on breakout score + confidence.
if predicted_return < 1e-6 and breakout_score > 0:
    predicted_return = 0.01  # 1% conservative estimate
```

**Issue:**
- If ML model untrained (predicted_return=0) AND breakout detected (breakout_score>0):
  - Forced to use 1% as predicted return
  - This is not informed by actual data; purely a fallback
- **Inconsistent**: If ML trained but pessimistic (predicted_return=0.001) AND breakout_score>0.7:
  - Keeps 0.001, NOT floored to 0.01
  - Creates cliff at 1e-6 boundary

**Impact:** Position sizes differ dramatically based on ML training state, not candidate quality

**Recommended fix:**
```python
# Use predicted_return or breakout_score for Kelly if ML signal weak
if predicted_return < 1e-6:
    # ML untrained or pessimistic; use breakout score as proxy
    predicted_return = 0.005 + breakout_score * 0.01  # [0.5%, 1.5%]
```

**Classification:** CRITICAL (creates cliff in sizing logic)

---

### [CRITICAL] Kelly Calculation Can Fail Silently on Edge Cases (Line 183-189)
**File:** `backend/organism/kelly_sizer.py:183-189`
```python
if var_r < 1e-8 or mean_r <= 0 or not math.isfinite(mean_r) or not math.isfinite(var_r):
    kelly_raw = 0.0
else:
    kelly_raw = min(mean_r / var_r, 1.0)  # Cap raw Kelly at 100%
```

**Edge cases:**

1. **Zero-variance returns** (same return every bar)
   - `var_r < 1e-8` → sets `kelly_raw = 0.0` ✓
   - But if mean_r > 0 (all wins), should size aggressively!
   - Instead returns 0.0 → no position

2. **Zero win rate** (all losses)
   - `mean_r <= 0` → sets `kelly_raw = 0.0` ✓
   - Correct behavior

3. **High variance, positive mean** (occasional large wins)
   - Example: returns = [-5%, -5%, -5%, +50%]
   - mean_r = 8.75%, var_r = 0.00302
   - kelly_raw = 8.75 / 0.00302 = 2.9 → capped to 1.0
   - Intended behavior (aggressive) ✓

**Issue in case 1:**
- Perfect win rate (variance=0) should indicate high confidence, not zero sizing
- Real-world: Historical backtest shows +0.5% every bar 100% win rate
  - Kelly formula undefined (0/0 case)
  - Falls through to `kelly_raw=0.0` → **no position placed**

**Recommended fix:**
```python
if var_r < 1e-8:
    # Zero variance — all same return
    if mean_r > 0:
        # Perfect win rate: use 50% of returns as Kelly proxy
        kelly_raw = 0.5
    else:
        kelly_raw = 0.0
else:
    kelly_raw = min(mean_r / var_r, 1.0)
```

**Classification:** CRITICAL (corner case breaks Kelly logic)

---

### [WARNING] Regime-Stratified Kelly Returns None Too Easily (Line 352-365)
**File:** `backend/organism/kelly_sizer.py:352-365`
```python
def get_regime_kelly(self, regime: str) -> float | None:
    """Compute Kelly fraction for a specific regime.
    
    Returns None if insufficient data (< 10 trades in regime).
    """
    stats = self._regime_stats.get(regime)
    if not stats:
        return None
    total = stats["wins"] + stats["losses"]
    if total < 10:
        return None
    win_rate = stats["wins"] / total
    if stats["losses"] == 0 or stats["total_loss_pnl"] < 1e-8:
        return None
    avg_win = stats["total_win_pnl"] / max(stats["wins"], 1)
    avg_loss = stats["total_loss_pnl"] / max(stats["losses"], 1)
    payoff_ratio = avg_win / avg_loss
    # Kelly: W - (1-W)/B
    kelly = win_rate - (1 - win_rate) / payoff_ratio
    return max(kelly, 0.0)
```

**Issues:**

1. **Perfect win rate** (no losses)
   - `stats["losses"] == 0` → returns None (line 364)
   - Kelly formula would be: W=1.0, B=∞ → kelly=0 (conservative)
   - But returning None falls back to global Kelly (discards regime data)
   - **Should return 0.0** (break-even scaling, since formula yields 0)

2. **Few wins, many losses**
   - Example: 2 wins, 8 losses → total=10, allowed
   - If avg_win=$100, avg_loss=$10 → payoff=10
   - kelly = 0.2 - 0.8/10 = 0.12 (12% fraction)
   - Could be correct, but with only 2 data points, confidence is low

**Recommendation:** Add minimum data threshold for each outcome type
```python
if stats["wins"] < 5 or stats["losses"] < 5:
    return None  # Need at least 5 of each outcome
```

**Classification:** WARNING (incomplete edge case handling for perfect records)

---

### [CRITICAL] Confidence Scale Can Go Below 0 After NaN Guard (Line 148-156, 208-209)
**File:** `backend/organism/kelly_sizer.py:148-156`
```python
if (
    direction == 0
    or predicted_return < 1e-6
    or math.isnan(direction)
    or math.isnan(predicted_return)
    or math.isinf(direction)
    or math.isinf(predicted_return)
):
    continue
```

**Issue:**
- Skips candidate if `predicted_return < 1e-6` AND `direction != 0`
- But confidence scaling (line 209) applies AFTER this guard:
```python
confidence_scale = 0.3 + min(confidence, 1.0) * 1.2
```
- Range: [0.3, 1.5] (lower bound 0.3, achievable only if confidence=0)
- But if `confidence=0`, candidate already filtered upstream in alpha_scanner (MIN_COMPOSITE=0.15)

**No actual violation found** — confidence is always >0 after filtering

**Mitigation verified:** ✓ Downstream filters prevent invalid confidences

**Classification:** INFO (safe after upstream filtering)

---

### [WARNING] Portfolio Cap Enforcement Rounding Error (Line 234-235)
**File:** `backend/organism/kelly_sizer.py:234-235`
```python
if total_weight + target_weight > self.max_portfolio_pct:
    target_weight = max(0.0, self.max_portfolio_pct - total_weight)
```

**Issue:**
- If `total_weight=0.93` and `max_portfolio_pct=0.95`, next candidate gets max 0.02 weight
- After 3 positions: 0.12 + 0.34 + 0.47 = 0.93, then 0.02 → total = 0.95 ✓
- But with shares rounding (line 250): `shares = int(notional / current_price)`
- Actual weight may be slightly less than calculated weight

**Impact:** Portfolio may never reach max_portfolio_pct due to share rounding

**Example:**
- Portfolio=$100K, target_weight=0.05 → notional=$5K → shares=100 (if price=$50)
- Actual notional=$5K ✓
- But if price=$51 → shares=98, notional=$4,998 → actual_weight=0.04998
- Over 15 positions, rounding can lose 0.5-1% of portfolio capacity

**Recommendation:** Recalculate actual_weight BEFORE summing (line 255 already does this ✓)

**Classification:** INFO (correctly mitigated by actual_weight recalculation)

---

### [INFO] Drawdown Scale Function Monotonic (Line 275-286)
**File:** `backend/organism/kelly_sizer.py:275-286`

✓ **Correctly implemented linear interpolation**
- 0% drawdown → 1.0
- max_drawdown_cutoff (25%) → drawdown_floor (0.1)
- Linear between

**No issues found**

---

### [INFO] Regime Scale Defaults Reasonable (Line 288-311)
**File:** `backend/organism/kelly_sizer.py:288-311`

✓ **Regime scales reviewed:**
- trending_up: 1.2 (aggressive in bull)
- trending: 1.0 (neutral)
- normal: 0.85 (slightly conservative)
- trending_down: 0.6 (risk-off)
- chop: 0.5 (avoid mean-reversion chop)
- high_vol: 0.7 (reduce in vol spikes)
- stress: 0.3 (defensive)
- crisis: 0.1 (quasi-offline)

**Scaling makes sense for intraday HFT**

**Classification:** INFO (well-calibrated)

---

### [INFO] Breakout Bonus Formula Correct (Line 313-332)
**File:** `backend/organism/kelly_sizer.py:313-332`

✓ **Verified piecewise linear interpolation:**
- breakout_score < 0.5 → 1.0 (no bonus)
- 0.5 to 0.7 → 1.0 to 1.5 (linear)
- 0.7 to 0.85 → 1.5 to 2.0 (linear)
- ≥ 0.85 → 2.0 (max bonus)

**Test case:** breakout_score=0.75
- Interpolate 0.7 → 0.85, 1.5 → 2.0
- bonus = 1.5 + (0.75 - 0.7) / 0.15 * 0.5 = 1.5 + 0.1667 = 1.6667 ✓

**No issues found**

---

---

## CROSS-CUTTING CONCERNS

### [WARNING] Position Sizing Over-Allocation in Bull Case (Line 221-228)
**File:** `backend/organism/kelly_sizer.py:221-228`

Given parameters:
- half_kelly = 0.05 (from regime Kelly with 0.5 payoff ratio, 60% win rate)
- drawdown_scale = 1.0 (no drawdown)
- vol_scale = 1.5 (realized vol < target vol)
- regime_scale = 1.2 (trending_up)
- confidence_scale = 1.5 (perfect confidence)
- breakout_bonus = 2.0 (strong breakout)

**Calculation:**
target_weight = 0.05 * 1.0 * 1.5 * 1.2 * 1.5 * 2.0 = **0.54 (54% per position!)**

With max_position_pct = 0.12, capped to 12% ✓

**But across 5 positions:**
- Pos 1: 12% → total 12%
- Pos 2: 12% → total 24%
- Pos 3: 12% → total 36%
- Pos 4: 12% → total 48%
- Pos 5: 12% → total 60%
- Pos 6: min(12%, 95% - 60%) = 12% → total 72%
- Pos 7: 12% → total 84%
- Pos 8: min(12%, 95% - 84%) = 11% → total 95%

**Result:** 8 positions at max cap = 95% portfolio

**Risk:** With each position at 12%, a 8% loss on any position = -0.96% portfolio loss (acceptable), but 2 positions hit stop-loss simultaneously = -1.92% (approaching 2% drawdown trigger threshold?)

**Assessment:** Acceptable but aggressive for intraday. Mitigated by:
1. Adaptive exits (stop-loss at 2% per position)
2. Sector gate (max 4 per sector)
3. Portfolio-level max (95%)

**Classification:** INFO (extreme case unlikely, but possible in strong bull regime)

---

### [CRITICAL] ML Signals Empty → Alpha Scanner Behavior Undefined (Line 116)
**File:** `backend/organism/alpha_scanner.py:87-217`

**Scenario:** First tick, ml_trained=False
- `ml_signals = {}` (empty dict)
- Alpha scanner processes all symbols
- For each symbol: `ml_sig = ml_signals.get(symbol)` → None
- ML score computed (line 119-124):
  ```python
  ml_score = 0.0
  direction = 0.0
  if ml_sig and ml_sig.direction != 0:
      ml_score = ml_sig.confidence * abs(ml_sig.predicted_return) * 20
      ml_score = min(ml_score, 1.0)
      direction = ml_sig.direction
  ```

**Result:** 
- All candidates get direction=0
- Composite *= 0.3 (line 180-181) — heavy penalty
- Candidates essentially filtered to breakout-only mode

**Impact:** First tick uses ONLY breakout scanner + breakout bonus sizing. No ML signals.

**Assessment:**
- Acceptable startup behavior (breakout scanner independent)
- But could be surprising if not documented

**Recommendation:** Add startup log message: "ML model untrained; using breakout signals only"

**Classification:** INFO (safe fallback, could use visibility)

---

### [WARNING] Composite Score Calculation Missing Intermediate Bounds Check (Line 169-177)
**File:** `backend/organism/alpha_scanner.py:169-177`

Individual factors can be NaN after guard (line 160-166), but NO bounds check BEFORE composing.

**Scenario:**
- All 7 factors pass NaN guard (become 0.0 or 0.5)
- But what if a factor is somehow negative?

**Example:** If `breakout_score` calculated as -0.1 (shouldn't happen, but code not defensive):
- Would pass `np.isfinite()` check
- Would contribute negative to composite
- Composite could go negative

**Assessment:** Unlikely but not impossible if feature computation returns unexpected values

**Recommendation:** Add explicit bounds checks on each factor:
```python
for factor in [ml_score, breakout_score, ...]:
    assert 0.0 <= factor <= 1.0, f"Factor {factor} out of bounds"
```

**Classification:** WARNING (defensive programming gap)

---

---

## SUMMARY TABLE

| File | Line(s) | Issue | Type | Severity |
|------|---------|-------|------|----------|
| ml_signal.py | 249-262 | Untrained model returns zero | Behavior | INFO |
| ml_signal.py | 265-275 | Feature mismatch silent degradation | Transparency | WARNING |
| ml_signal.py | 297-305 | Ensemble failure no logging | Observability | WARNING |
| ml_signal.py | 284-289 | Single-class probability edge case | Edge case | WARNING |
| alpha_scanner.py | 169-188 | Composite score >1.0 possible | Invariant | **CRITICAL** |
| alpha_scanner.py | 160-166 | Inconsistent NaN defaults | Data handling | **CRITICAL** |
| breakout_scanner.py | 232-273 | Squeeze false positives in chop | Signal quality | WARNING |
| breakout_scanner.py | 381-400 | Non-deterministic ranking ties | Determinism | WARNING |
| kelly_sizer.py | 141-145 | Predicted return cliff at 1e-6 | Logic cliff | **CRITICAL** |
| kelly_sizer.py | 183-189 | Zero variance edge case | Kelly formula | **CRITICAL** |
| kelly_sizer.py | 352-365 | Perfect win rate returns None | Edge case | WARNING |
| kelly_sizer.py | 234-235 | Portfolio cap rounding loss | Precision | INFO |
| kelly_sizer.py | 221-228 | Over-allocation in bull case | Risk | INFO |

---

## IMMEDIATE ACTION ITEMS (Pre-Launch)

### CRITICAL (Fix Before Launch)
1. **Alpha Scanner**: Add `composite = min(composite, 1.0)` after fitness multiplier (line 188)
2. **Alpha Scanner**: Change NaN defaults: `ml_score → 0.5`, `volume_score → 0.5` (line 160, 165)
3. **Kelly Sizer**: Fix predicted_return floor logic (line 141-145) — use graduated floor based on breakout_score
4. **Kelly Sizer**: Handle zero-variance case in Kelly calculation (line 183-189)

### WARNING (Monitor & Fix in v1.1)
1. **ML Signal**: Add logging to ensemble failure (line 305)
2. **ML Signal**: Add guard for single-class probabilities (line 284)
3. **Breakout Scanner**: Add regime filter to squeeze detection (line 271)
4. **Breakout Scanner**: Add tie-breaking to RS ranking (line 398)
5. **Kelly Sizer**: Fix perfect win-rate handling in regime Kelly (line 364)

### INFO (Document for Operators)
1. Log "ML untrained — breakout-only mode" on first tick
2. Document regime scaling rationale in production runbook
3. Add metric for feature availability per symbol
4. Monitor composite score distribution for values >1.0 (should be 0 after fix)

---

## TEST COVERAGE RECOMMENDATIONS

Add to test suite:
```python
def test_composite_score_never_exceeds_one():
    """Composite must stay in [0,1] after fitness multiplier."""
    alpha = AlphaScanner()
    alpha._symbol_fitness = {"TEST": 1.0}  # Maximum fitness
    # Construct row with all perfect scores
    row = pd.Series({...all factors = 1.0...})
    score = compute_composite_score(row)
    assert score <= 1.0

def test_kelly_sizing_zero_variance():
    """Zero variance returns should scale aggressively, not to zero."""
    sizer = KellySizer()
    candidates = [{..., predicted_return=0.005, confidence=0.9...}]
    # Backtest with constant returns
    features = {"TEST": df_with_zero_variance}
    sizes = sizer.size_positions(candidates, 100000, 0.0, features)
    assert len(sizes) > 0  # Should not skip zero-variance

def test_predicted_return_floor_smooth():
    """Predicted return should scale smoothly, no cliff."""
    sizer = KellySizer()
    # Test candidates with predicted_return near 1e-6 boundary
    sizes1 = size_for(predicted_return=1e-7)  # Below floor
    sizes2 = size_for(predicted_return=1e-6)  # At boundary
    # Both should produce reasonable sizes, not cliff
    assert abs(sizes1.target_weight - sizes2.target_weight) < 0.02
```

---

## DEPLOYMENT READINESS: APPROVED (with fixes)

**Status:** Pre-launch audit complete  
**Blockers:** 4 CRITICAL findings must be fixed before live trading  
**Warnings:** 5 non-blocking issues recommend monitoring  
**Timeline:** Fixes estimated 2-3 hours development + 1 hour testing

**Recommendation:** Deploy after applying CRITICAL fixes + running test suite.

---

*Report generated: 2026-02-22 06:30 UTC*  
*Reviewer: Overnight Code Audit*
