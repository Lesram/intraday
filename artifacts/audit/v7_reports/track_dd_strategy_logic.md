# V7 Track DD — Strategy Logic Correctness Audit

**Branch / commit**: `rc-1.5-curated` @ `d44eace`  
**Audit date**: 2026-05-02  
**Scope**: First-ever audit of the trading logic itself (alpha factors, regime, exits, Kelly,
ML calibration, features, risk model, fitness gating, attribution, lookahead).
V1-V6 covered infrastructure; V7-DD is correctness of the strategy.

**Method**: read each in-scope module, build a precedence/data-flow model, exercise
edge cases with synthetic OHLCV through `./venv/bin/python` probes, cross-check call
sites in `live_engine.py` and `self_evolution.py` for parity / bypass.

---

## TL;DR — Bugs Found: 11

| # | Severity | Surface | Title |
|---|---|---|---|
| DD-1 | **HIGH** | composite indicators / alpha factor | `comp_breakout_readiness` returns 0.633 on flat-price data |
| DD-2 | **HIGH** | regime detector | Default `atr_ratio = 0.02` triggers spurious `high_vol` on any feature-DataFrame missing `atr_14` |
| DD-3 | **HIGH** | feature engineering | SPY cross-asset features positionally sliced — silent misalignment when SPY/stock lengths differ |
| DD-4 | **HIGH** | Kelly sizer | Regime-stratified Kelly path bypasses the spread-cost gate, ML floor, breakout floor |
| DD-5 | **MEDIUM** | Kelly sizer | Unconditional historic Kelly fires even on zero-current-edge candidates (no `signal_kelly` floor) |
| DD-6 | **MEDIUM** | regime detector | `max(probs, key=...)` tie-break is dict-iteration-order; unstable on near-ties (e.g. flat data: chop / high_vol both 0.393) |
| DD-7 | **MEDIUM** | continuous learner | System-level anti-predictivity (memory.md: corr=−0.112) is not surfaced to the acceptance gate; only candidate-level monotonicity is gated |
| DD-8 | **MEDIUM** | live_engine attribution | `entry_source` inference at sizing-time can mis-tag pure-breakout entries as "alpha" when `predicted_return >= 0.003` |
| DD-9 | **LOW** | sector gate | Symbols missing from `SECTOR_MAP` get a free pass on sector-cap (`sector == "Unknown" → return True`) |
| DD-10 | **LOW** | Kelly drawdown | `drawdown_floor = 0.10` is unreachable in production — governance halts at 5% dd, well below the 25% cutoff |
| DD-11 | **LOW** | adaptive exits | `_compute_atr` fallback (insufficient bars) returns simple `close.diff().abs().mean()`, not a true ATR — under-estimates by ~30% on warmup |

**Single highest-impact finding**: **DD-1** — `comp_breakout_readiness` returns
**0.633** on perfectly flat-price warmup data. This composite is consumed both by
`AlphaScanner.scan` (`breakout_score = 0.6 * readiness + 0.4 * squeeze_momentum`) and
by the entry_source classifier; 0.633 is well above the 0.55 threshold for "high
breakout score" (Kelly's `_breakout_bonus` returns 1.5× at score≥0.7, but at 0.633
still gives ~1.27× via interpolation). Combined with `vol_sma_ratio=1.0` and
`gap_pct=0.0` on a flat tape, the alpha-scanner's in-play boost stays at 1.0× —
but the breakout-component fires at full strength. On a fresh symbol with a quiet
opening or any halted stock returning to trade (where 5-10 bars of identical
prints are common), this produces a synthetic high-conviction entry with **no
real edge**.

---

## Per-Component Analysis

### 1. Alpha factor correctness (`alpha_scanner.py`, `composite_indicators.py`)

**Composite score**: weighted sum of 7 sub-scores, gated `MIN_COMPOSITE = 0.15`
(0.25 in `high_vol`, 0.50 in `stress`).

**Factor-by-factor:**

| Factor | Weight | Source | Warmup verdict | Notes |
|---|---|---|---|---|
| `ml_score` | 0.25 (prod) / 0 (learn) | MLSignal | OK — 0 when untrained | Scaling: `eff_conf * |pred_return| * 20`, capped 1.0 |
| `breakout_score` | 0.20 / 0.40 | `comp_breakout_readiness * 0.6 + comp_squeeze_momentum * 0.4` | **BAD** — see DD-1 | |
| `inst_score` | 0.15 | `comp_institutional_acc` | OK — defaults to 0.5 | |
| `momentum_score` | 0.15 / 0.20 | cross-sectional rank of `ret_20d` | OK — NaN guarded → 0.0 | Rank ties: dict order |
| `mom_quality` | 0.10 | `comp_momentum_quality` | OK — defaults to 0.5 | |
| `volume_score` | 0.10 | `vol_sma_ratio − 1` plus divergence | OK | |
| `regime_score` | 0.05 | trend alignment | OK — see DD-6 for tie-break | |

**DD-1**: `comp_breakout_readiness` produces ~0.633 on data with constant OHLC.
Reason: `_safe_div(0, 0) = 0 / 1e-10 = 0`, so:
- `compression = (1 − atr_short/atr_long).clip(0,1) = 1.0`
- `near_resistance = (1 − dist_to_res/3).clip(0,1) = 1.0`
- `vol_buildup ≈ 0.333` (volume always near resistance because there IS no resistance)
- `adx_turning = 0`
- composite = 0.30·1.0 + 0.25·1.0 + 0.25·0.333 + 0.20·0 ≈ **0.633**

Repro:
```
flat_df = pd.DataFrame({'open':[100]*60,'high':[100]*60,'low':[100]*60,'close':[100]*60,'volume':[1e6]*60})
breakout_readiness_index(flat_df).iloc[-1]  # 0.6333...
```
File: `backend/organism/composite_indicators.py:364-421`

**Lookahead bias (factor-level)**:
- All `_safe_div`, `_sma`, `_ema`, `.rolling(...)` use trailing windows. ✅
- No `.shift(-N)` in any composite indicator. ✅
- `breakout_readiness` uses `c.shift(1)` for true-range — past-only. ✅
- `vol_buildup` uses `vol_near_res.rolling(5).mean()` — past-only. ✅
- One concern: `.replace(0, 1e-10)` on full series can use future denominator
  values when applied via `_safe_div(a, b)` — but division is element-wise, no leak.

**Cross-sectional momentum rank (`_rank_momentum`)**: the rank is positional
(`i / (n-1)`) with `n` = symbols-with-≥20-bars; symbols below the warmup
threshold are excluded from the rank but DO still get a default `0.5`
(line 171). On day 1 of a new symbol's life it ranks at neutral 0.5, which
neither helps nor hurts — sane.

### 2. Regime classification (`regime.py`)

**Two paths**: per-symbol `detect()` and aggregated `detect_market_regime()` /
`detect_cross_asset_regime()`.

**DD-2**: Default `atr_ratio = 0.02` when no `atr_14` / `atr_14_ratio` /
`ATR_ratio` column is present (line 208) is wildly inconsistent with the
intraday thresholds (`atr_high_thresh ≈ 0.002 * tf_scale = 0.002 / sqrt(390) ≈
1e-4 ... wait`, actually `0.04 * tf_scale = 0.04 / sqrt(390) = 0.00203`).
**0.02 (default) >> 0.00203 (high_vol threshold)** → regime falls through to
`high_vol` whenever the column is missing. On warmup or for a newly-added
symbol whose features haven't been computed yet, this misclassifies every tick
as `high_vol`, which (a) tightens entry thresholds (`min_threshold=0.25` instead
of 0.15), and (b) sizes positions at `regime_scale = 0.8` instead of unknown's
0.7. Net effect: **wrong regime label propagates through the entire stack until
features arrive.**

Probe:
```
det = RegimeDetector(is_intraday=True, bars_per_day=390)
det.detect(pd.DataFrame({'close':[100]*100,'high':[100]*100,'low':[100]*100,'volume':[1e6]*100}))
# atr_ratio defaults to 0.02 → atr_high_thresh=0.002 → STRESS / HIGH_VOL prob
# (ties chop in our flat probe but for a real market with vol_anomaly>0.5
#  this would tip into stress).
```
File: `backend/organism/regime.py:208-215`

**DD-6**: Regime tie-break is dict-iteration-order. On flat data:
```
{'trending_up': 0.053, 'trending_down': 0.053, 'chop': 0.393,
 'high_vol': 0.393, 'low_vol': 0.053, 'stress': 0.053}
```
`max(probs, key=probs.get)` returns `chop` because it's iterated first via
`_compute_probabilities`. If feature-engineering ordering or future refactor
changes that, the tie-break flips to `high_vol`. Regime hysteresis exists
(EMA smoothing) but doesn't help on a true tie. Add explicit tie-break or
always-distinct probabilities (e.g. small noise term).

**Drift detector** (PSI threshold = 0.10): the threshold appears arbitrary —
no documented calibration. Standard PSI conventions: <0.10 stable, 0.10-0.25
moderate drift, >0.25 significant. The 0.10 threshold is the *liberal* end —
common but not "calibrated for this universe."

**Pre-V3 SMA normalization regression**: confirmed fixed. `regime.py:191-196`
recomputes raw SMA from `close` (not the normalized `sma_50` feature column).
Trend-slope uses raw SMA series. ✅

### 3. Exit logic precedence (`adaptive_exits.py`, `live_engine.py`)

Built precedence table from `check_exit()` source + live_engine call site.

| Order | Exit type | Tick gate | Mode | Mutates state | Notes |
|---|---|---|---|---|---|
| 0 | `max_loss_limit` (15% absolute) | every tick | both | no | hard cap, before stop |
| 1 | `stop_loss` | every tick | both | no | direction-aware |
| 1a | min-hold suppression (H//3) | new bar | both | no | suppresses 1.5/2/3/4b/4c/5/5b only — NOT 0/1 |
| 1.5 | profit_lock (2R → stop=1R) | new bar | prod only | yes (stop) | one-shot, never returns exit |
| 2 | partial_take_profit (3R, 30%) | new bar | prod only | yes (stop→breakeven) | partial exit |
| 3 | full take_profit | new bar | prod only | no | direction-aware |
| 4 | trailing_stop | new bar | both | yes (trail level) | regime-adaptive trail distance |
| 4b | failure_to_follow (FTF) | new bar | both | yes (stop tightens in chop) | regime-gated, multi-bar momentum check |
| 4c | horizon_timeout (18 bars) | new bar | learn only | no | hard barrier |
| 5 | max_holding_period (regime cap) | new bar | both | no | only fires if profitable |
| 5b | loser_time_stop (1.5× max_bars) | new bar | both | no | only if losing |
| 6 | apply_time_decay | new bar | both | yes (stop tightens) | continuous |
| 7 | tighten_for_stress (regime flip) | new bar | both | yes (stop tightens) | one-shot |
| ext | ml_reversal (30% partial) | tick | both | no | only if `not exit_sig.should_exit` |
| ext | eod_flatten (15:58 ET) | tick | both | no | live_engine, after check_exit |
| ext | safety_net_no_features | tick | both | no | live_engine, when feat_df empty |

**Precedence is consistent and deterministic**. No path lets a "soft exit"
preempt a "hard exit". Min-hold cleanly excludes the 0/1 (max_loss/stop_loss)
gates. ✅

**Subtle observation** — partial_TP fires *before* full TP (correct: 3R
target hits 3R partial before 6R full). Partial-TP correctly preserves
profit-lock via `max(stop, breakeven)` for longs.

**One concern**: `partial_tp_r_scale` evolves up to 1.8× via
`_evolve_exit_params`, yielding `partial_tp_r = 3 × 1.8 = 5.4R`. But
`profit_lock_r = 2.0R` is fixed. Order: profit_lock → partial_tp. After
profit_lock at 2R sets stop to 1R, partial_tp at 5.4R does
`max(stop_loss, breakeven)` → `max(1R, 0R) = 1R`. **Bug-free, but partial_TP's
"breakeven move" is no-op when profit_lock already fired.** Document this.

### 4. Kelly sizing math (`kelly_sizer.py`)

**B-T-7 fix verification (V5/wave-18)**: confirmed. `_ATR_VAR_MIN = 1e-6` on
`atr_var_squared`. When ≤ floor, `signal_kelly = 0.0` instead of saturating to 1.0.
✅ But: realistic intraday `atr_pct ≈ 1e-3 to 1e-2`, so `atr_pct_horizon ≈ 4e-3 to
4e-2`, `atr_pct_horizon^2 ≈ 1.6e-5 to 1.6e-3` — well above 1e-6. The fix only
fires on truly anomalous data (`atr_pct < 2.58e-4 ≈ 2.58 bps`). Sufficient
for the saturation case but does NOT close the broader "near-zero-vol over-sizing"
risk.

**DD-4 (HIGH)**: When a regime has ≥10 closed trades and a positive Kelly
(`get_regime_kelly()` returns a non-None value), the entire production path
through lines 360-364 sets `kelly_raw = min(regime_kelly, 1.0)` and **bypasses
the spread-cost gate, ML-confidence floor, and breakout floor** that follow.
This means once a regime accumulates enough trade history, *any* candidate in
that regime sizes from `regime_kelly` regardless of:

- `predicted_return < spread_cost_pct * 2.0` (edge_clears_cost = False)
- `confidence < _ML_CONFIDENCE_MIN` (would have zeroed kelly_half)
- `breakout_score < 0.55`

File: `backend/organism/kelly_sizer.py:359-369`. The fix is to keep regime_kelly
as a *floor* but still require all gates to pass before applying it.

**DD-5 (MEDIUM)**: When `regime_kelly` is None (sparse regime data) AND
`signal_kelly = 0` (zero-vol or `predicted_return ≤ 0`), the code falls back to
`unconditional_kelly = mean_r / var_r` from **historic returns**, NOT from the
candidate's signal:
```python
unconditional_kelly = min(mean_r / var_r, 1.0)  # if mean_r > 0 and var_r > 1e-8
kelly_raw = min(max(signal_kelly, unconditional_kelly), 1.0)
```
A zero-edge candidate (no breakout, no ML, no MR) can still get `kelly_raw =
unconditional_kelly` from positive historic mean-return — i.e., **sized from
the symbol's prior trend, not the current signal**. Combined with DD-1 (a flat
tape that scores breakout=0.633), this could fire.

**Half-Kelly applied uniformly**: ✅ `kelly_half = kelly_raw * 0.5` consistently.

**Per-position cap enforced after Kelly stack**: ✅ line 487. But the
multiplicative stack (`kelly_half * dd * vol * regime * conf * breakout`) can
exceed 3.6× before clamping; the cap at 10% is the binding constraint.

**H1 production-mode dollar-risk cap (line 547)**: ✅ `_RISK_BUDGET_PER_TRADE
= 0.0025` (0.25% equity). Computed via `atr_pct * 1.5 * current_price`. This
caps shares post-Kelly. Implementation looks correct.

**Correlation adjustment**: NOT done. The sizer treats each candidate
independently. With sector-cap `MAX_PER_SECTOR=4`, gross correlation exposure
is partially capped, but no explicit correlation reduction in size.

**Drawdown scaling — DD-10**: `drawdown_floor=0.10` at `max_drawdown_cutoff=0.25`.
But `governance.py` halts trading at `DEFAULT_DRAWDOWN_KILL_PCT = 0.05`.
Trading halt occurs at 5% dd, so the Kelly drawdown_scale linear range
1.0 → 0.10 is effectively only used in the 0–5% dd zone, where scale spans
1.0 → ~0.82. The 0.82 → 0.10 range is dead code in production. Consider
aligning `max_drawdown_cutoff` with governance's kill threshold (or remove
it).

**Confidence scaling**: `0.3 + min(eff_conf, 1.0) * 1.2`. Linear in confidence.
At `eff_conf=0.5` (min ML threshold), scale = 0.9 — almost neutral.
At `eff_conf=1.0`, scale = 1.5. Reasonable.

### 5. ML calibration logic (`continuous_learner.py`, `ml_signal.py`)

**Acceptance gate**: hard-coded threshold `MIN_CALIBRATION_SAMPLES_FOR_ACCEPTANCE
= 30`. Score = `hit_rate*0.4 + accuracy*0.3 + max(direction_acc-0.5, 0)*0.6`.
Quality constraints:
1. `effective_mean_pred_return > 0`
2. `precision >= 0.45`
3. If `cand_cal_samples >= 30` and not monotonic → reject
4. If `cand_cal_samples >= 30` and `cand_cal_err >= 0.25` → reject

**Score threshold**: 0.25 if both system and candidate are mature; else 0.35.
Improvement over prior model: 5% min. ✅ All looks defensible.

**Calibration math**: `_compute_psi`, reliability bins of 5 are simple but
adequate. Bins are equal-width (0.2 each), so very-high-confidence bin (0.8-1.0)
is calibrated against midpoint 0.9.

**DD-7**: Memory.md notes `corr(confidence, correct_direction) = -0.112` —
i.e., the SYSTEM is anti-predictive. The `acceptance_gate` checks
**candidate-level** monotonicity from validation predictions, not the system's
historical anti-predictivity. So the gate can keep accepting models even when
the live calibration map shows inverted bins. The `update_calibration_map()`
*corrects* confidence by per-bin multiplier, but doesn't *reject* a model.
There is no surface that says "stop using this model — system corr is
negative." Add a guard to the `acceptance_gate` that reads
`generator.calibration_quality()` and rejects if not monotonic with sufficient
samples.

**Confidence anti-predictivity post-Ferrari-v1**: cannot directly measure on
disk; would need a fresh sweep over `trade_history.csv`. The mechanism that
*should* close the negative-corr loop is (a) `_compute_effective_confidence`
caps confidence by empirical precision, (b) `_compute_effective_predicted_return`
damps by `min(1, samples/30) * eff_conf`. Both are passive corrections — they
shrink size, not reject.

### 6. Feature engineering correctness (`ml_features.py`)

**78 features** in `FEATURE_COLUMNS` plus `_nan_missingness`. Reviewed each
feature for lookahead bias.

**No `.shift(-N)` anywhere in `ml_features.py` or composite_indicators**. ✅

**Bar-aligned features**: all use `c.shift(1)` (past close), `.rolling(N)`
ending at current bar, or `.pct_change(N)` (uses past N bars). ✅

**DD-3 (HIGH)**: Cross-sectional features against SPY use **positional
slicing** rather than timestamp join:
```python
# ml_features.py:269-271
spy_c = spy_df["close"].iloc[-len(df):].values
spy_ret = pd.Series(spy_c).pct_change().values
```
If `len(spy_df) > len(df)` (e.g., halt in stock but not SPY), SPY's last
`len(df)` bars correspond to *different timestamps* than stock's bars. The
resulting `rel_strength_spy`, `beta_20d`, `corr_to_market`, `idio_vol` are
silently misaligned. Same issue at lines 287-288 and 307-308 inside the loop
(`mr = spy_ret[max(0, len(spy_ret)-len(stock_rets)+i-20):...]`).

Fix: timestamp-merge SPY onto stock's index via `pd.merge_asof` before
computing.

**`_nan_missingness`**: a constant per-call ratio of NaN cells in last row vs
total columns — exposes data-completeness as a feature. Sane.

**Feature scale / standardization**: no explicit standardization in feature
engineering. Models (XGBoost) are tree-based, so absolute scales matter less
— but the **threshold-based features** (e.g. `vol_regime` 0/1/2 from rolling
percentile) and the **ratio features** (already O(1)) are not standardized.
This is fine for tree models but would fail in linear/NN models.

**Categorical encoding**: `vol_regime` and `regime_encoded` are integer-cast
floats (0.0/1.0/2.0). For trees, this works; for one-hot consumers it's
ambiguous.

**NaN handling**: `f.fillna(0.0, inplace=True)` (line 458). Replacing all NaN
with 0 is **NOT a benign default** for many features:
- `rsi_14 = 0` means "fully oversold" (true RSI=0)
- `bb_position = 0` means "at lower BB" (true BB position 0)
- `z_score_20 = 0` means "at the mean" (median value)
- `momentum_score = 0.5` after sentinel → neutral

So a warm-up bar gets a **synthetic "fully oversold + at-mean + at-lower-BB"
profile** — a strong mean-reversion long signal. With `comp_breakout_readiness
= 0.633` from DD-1, the alpha scanner could fire the ML+breakout+MR triple
boost with zero real signal.

### 7. Risk model sanity (`live_engine.py`, `governance.py`)

**`MAX_DAILY_LOSS`**: Env-driven, default `$1500`. Per `live_engine.py`:
`_DAILY_MAX_LOSS_USD`. Defensible — about 1.3% of $111k equity.

**Drawdown limit (5%)**: governance. ✅ env-overridable; startup logs
resolved value + source.

**Per-symbol consecutive-loss threshold** (V4 Q-Q1): `_symbol_stop_loss_times`
tracks 30-min rolling; ban condition is dollar-loss-based (line 5188 mentions
`$%.2f`). Reset path looks correct.

**Sector cap**: Per `sector_map.py`, includes XLK/XLE/SH/PSQ explicitly
(V6 wave-16a fix). SPY/QQQ/IWM in their own "Index" bucket — also defensible.
**DD-9**: `if sector == "Unknown": return True` — symbols missing from the
map get a free pass on sector-cap enforcement. With universe = 30 symbols all
mapped, this isn't currently exploited, but adding a new symbol without
updating `SECTOR_MAP` silently breaks the gate.

### 8. Walk-forward fitness gating (`walk_forward.py`)

Note: walk_forward is **OFFLINE-ONLY**, not used for live promotion (live
uses `acceptance_gate`).

**B-T-5 fix verification**: ✅ `result.sharpe = 0.0` when `len(daily_pnls) <=
1` (refuses to grade) instead of synthesizing a fake Sharpe via std=1.0
fallback. Sister consumer in `continuous_learner.py:414` uses `>1e-8` floor.

**Look-back window**: `train_window_days=60`, `test_window_days=10`,
`step_days=5`. With paper trading at ~16 trades/day, 60 train days = ~960
trades — adequate. 10 test days = ~160 — defensible.

**Apples-to-apples comparison**: `evaluate()` runs both candidate AND
baseline on identical windows (lines 200-225) — ✅ correct. `_baseline_sharpe`
is mean across windows, used for improvement gate.

**`min_improvement_pct = 0.05`**: candidate must beat baseline by 5% relative
Sharpe. The compare line 471: `improvement = (mean_sharpe - baseline)/abs(baseline)`
when baseline > 0; otherwise `mean_sharpe - baseline_sharpe` (additive).
Discontinuous at baseline=0 — borderline cases get either ratio or delta
treatment. Minor, but worth noting.

**`regression_threshold=0.95`**: I do not see a `regression_threshold` in
walk_forward.py. The prompt mentions it; possibly exists elsewhere or is
deprecated. Not found in `acceptance_gate` either — only `improvement_threshold
= 0.05`.

### 9. Performance attribution

**Three sources of truth for trade attribution**:
1. `TradeRecord` (continuous_learner.py:177-209) — has `entry_source`,
   `regime_at_entry/exit`, `mfe`, `mae`, `bars_held_at_exit`.
2. `_save_trade_history` / trade_history.csv — disk artifact.
3. `_entry_metadata` dict (live_engine.py:3735) — includes `entry_source`.

**DD-8 (MEDIUM)**: `entry_source` inference at sizing-time (`live_engine.py:3722-3734`):
```python
if _entry_source_override:           # set by ORB/EOD/MR scanners
    _entry_source = _entry_source_override
else:
    _entry_source = "alpha"          # default
    if sz.breakout_score >= 0.55 and (
        not hasattr(sz, 'predicted_return') or abs(sz.predicted_return) < 0.003
    ):
        _entry_source = "breakout"
    elif sz.breakout_score >= 0.4:
        _entry_source = "alpha+breakout"
```
A pure-breakout-path entry (lines 2998-3008, no `entry_source_override`) with
`predicted_return >= 0.003` (now common post-Ferrari) gets tagged
**"alpha+breakout"** when its actual provenance is the pure-breakout fallback
path. Memory.md flagged this: *"Historical entry_source tags pre-2026-05-01 are
corrupted: pre-fix `predicted_return` was floored to 0.003 → 80%+ of past
"alpha+breakout" trades were really pure-breakout mis-tagged."* Going forward
the tag is *less* corrupted but still ambiguous when `predicted_return >= 0.003`.

The fix: pure-breakout path (lines 2998-3008) should set
`"entry_source_override": "breakout"` directly, instead of relying on
inference at line 3728.

**Direction-adjusted returns**: ✅ `correct_direction` property handles
shorts correctly: `(direction>0 AND actual_return>0) OR (direction<0 AND
actual_return<0)`.

### 10. Lookahead bias systematic scan

**grep results** for the 12 in-scope files + composite_indicators:

```
$ grep -rE "shift\(-[1-9]" backend/organism/*.py
(no results)
```
✅ No negative-shift in feature engineering.

```
$ grep -rE "iloc\[i\+|\.shift\(\-" backend/organism/*.py
backend/organism/live_engine.py:800:  avg_vol = float(df["volume"].iloc[-20:].mean())
backend/organism/ml_signal.py:432:    row = features_df[available_cols].iloc[-1:]
```
Both benign — `iloc[-20:]` is trailing tail; `iloc[-1:]` is current bar.

**Training labels** (`ml_signal._build_training_data`, line 700-720): ✅
- `X = features.values[:-H]` — drops last H bars where target is unknown.
- `y_dir = (close[t+H] > close[t]).astype(int)` — uses future close[t+H]
  which is correct (it's the LABEL).
- The label uses `close[H:] vs close[:-H]` aligned to features at `[:-H]` —
  no leak.

**Per-symbol temporal split** (`_temporal_split`): ✅ each symbol's chunk is
split independently into train/val with `(1-val_ratio)` train. No
cross-symbol leak.

**One subtle issue**: `predict()` runs on `features_df.iloc[-1]` which may
be an in-progress bar (live), not a closed bar. This isn't strictly
lookahead — it's "use available data" — but does mean live predictions
operate on partially-formed feature values (especially OHLC: open is set
but high/low/close evolve). Documented limitation, not a bug.

**Cross-asset SPY alignment**: see DD-3 — silent corruption when lengths
differ.

**Composite indicators**: re-checked, all use trailing windows. ✅

---

## Edge-case Verdicts

| Edge case | Verdict |
|---|---|
| Constant-price warmup | ❌ DD-1: `comp_breakout_readiness=0.633` (false positive) |
| Single-bar / zero-volume | OK — features default to 0 / 1 (vol_sma_ratio=1) |
| Zero-variance returns | ❌ DD-2: regime falls back to default 0.02 atr_ratio when col missing |
| All-NaN feature row | OK in main path — `_nan_missingness=1.0` exposed; but `fillna(0)` synthesizes meaningful-looking values |
| Insufficient bars for ATR | LOW DD-11: `_compute_atr` falls back to `close.diff().abs().mean()` instead of true TR |
| Tiny `predicted_return` (`< 1e-6`) | OK — Kelly skips via `predicted_return < 1e-6` guard |
| Zero-vol bar (`atr_pct → 0`) | ✅ V5 B-T-7 fix: `signal_kelly = 0`, falls through to unconditional. DD-5: but unconditional can still size from history. |
| Halt / stale bar (timestamp gap) | ❌ DD-3: SPY positional alignment misaligns features |
| Borderline regime threshold | OK — EMA smoothing prevents single-bar flip |
| Truly tied regime probabilities | ❌ DD-6: dict-iteration-order tie-break |
| Tiny ATR (low-priced low-vol) | ✅ MR scanner has `min_stop_bps=5.0` floor; EOD has same |
| Brain-restored params before 300 trades | OK — H4 freeze gate prevents apply |
| Regime with all losses (`get_regime_kelly`) | ✅ Returns None when `payoff_ratio <= 0` |
| Regime with no losses (W=10/10) | OK — Returns None (`losses == 0`) |
| Regime with 10 small wins + 10 huge losses | Kelly = max(neg, 0) = 0; OK |

---

## Lookahead Bias Scan Summary

| Pattern | Files searched | Hits | Verdict |
|---|---|---|---|
| `.shift(-N)` | all backend/organism/*.py | 0 | ✅ |
| `iloc[i+1:]` in per-bar loop | all | 0 | ✅ |
| Future-close in feature def | reviewed each feature | 0 | ✅ |
| Future labels (`y[t+H]`) | ml_signal.py | yes | ✅ correct usage (labels, not features) |
| Cross-asset positional align | ml_features.py | yes | ❌ DD-3 |

---

## Cross-Cutting Observations

### Same-symbol cross-source dedup
- Pure-breakout path: ✅ `if bs.symbol in alpha_syms: continue` (line 2941)
- ORB path: ✅ `if _orb_sym in _existing_syms: continue` (line 3049)
- EOD path: ✅ `_existing_syms` checked (line 3187)
- MR path: ✅ `_existing_syms` checked (line 3352)

But: `_passes_entry_gates` has NO direct check for `symbol in
planned_entries`. Each scanner does its own dedup. The `_planned_entries` set
is consumed only by `sector_gate_allows`. **If a future scanner is added and
forgets the `_existing_syms` pattern, the same symbol would be added twice.**
Consider centralizing in `_passes_entry_gates`.

### Static / pre-decided constants
- `_HORIZON_TIMEOUT_BARS = 18` — magic constant in `adaptive_exits.py:509`.
  Not overridable.
- `_CHOP_MIN_HOLD_BARS = 10` — magic in `live_engine.py:2572`.
- `_EXP4_CHOP_TRAIL_ATR = 5.0` — magic in `adaptive_exits.py:658`.

These are evolution dead-zones — they don't get learned even though they're
strategy-critical.

### Evolution feedback isolation
- Stops widening on too-many-stop-loss-exits (`_evolve_exit_params` line 451).
- Trailing-distance widens when avg trail PnL is high.
- Symbol fitness EMA-updated, decay-toward-neutral for unprofitable.
- Direction threshold calibrated from confidence buckets.

But: **alpha_weight_ml is held fixed in `_normalize_alpha_weights` (lines
1141-1156)**. Comment explains: "no explicit ML attribution signal on trade
records." Result: ML weight only changes via direct edits, not via outcome
feedback. Defensible given the anti-predictivity finding, but means evolution
can't downweight ML if it stays bad.

---

## Conclusions

This is the first audit of the trading logic itself, and we found **11
issues** spread across factor correctness, regime classification, sizing
math, and attribution. The strongest findings are concentrated in the
"warm-up / edge-case" surface — which is exactly where infrastructure
audits don't reach. The Kelly + regime classifier + breakout-readiness
combination has multiple mechanisms that can silently amplify a *flat,
no-edge market state* into a high-conviction sized entry: DD-1 produces a
0.633 breakout-readiness score on flat OHLC, DD-2 misclassifies that flat
state as `high_vol`, DD-4 lets regime-Kelly bypass the cost gate, DD-5
sizes from historic Kelly even when current signal is zero, and DD-3
silently corrupts cross-asset features whenever SPY length differs from
the stock's. The single highest-impact strategy-logic finding is **DD-1**:
the breakout-readiness composite — which weights 0.6 inside the alpha
scanner's breakout score (a 20%-weighted factor in the composite, scaled
to 40% in learning mode) and feeds a 1.0× → 1.5× → 2.0× Kelly bonus —
returns 0.633 on perfectly flat data, meaning a halted stock or a quiet
warmup bar produces a **synthetic high-breakout signal with no real edge**.
The fix is a one-line guard in `composite_indicators.py:breakout_readiness_index`
to return 0.0 when `(atr_long < 1e-9)` or `(h.rolling(20).max() == c)` for
the trailing window — recognizing that "compression" and "near-resistance"
are meaningless when there's no price action to compress or no resistance
above current price.
