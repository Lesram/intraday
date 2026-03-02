# INTRA ENGINE IMPROVEMENT GUIDE

> Actionable implementation plan based on external review + code-verified findings.
> Every claim below has been verified against the actual source code with exact file:line references.

---

## CURRENT STATE (as of 2026-03-01)

| Metric | Value | Problem |
|---|---|---|
| Total trades | 262 | — |
| Win rate | 43.9% (115W / 140L) | Below breakeven with 2:1 loss ratio |
| Avg win | +$19.62 | — |
| Avg loss | -$39.71 | **2x the avg win — risk/reward inverted** |
| Cumulative PnL | -$3,302.75 | Steady bleed |
| Peak equity | $112,655.91 | — |
| Current equity | $112,425.78 | -0.2% drawdown |
| Regime | high_vol (persistent) | Most of session classified as high_vol |

**The core problem**: The engine trades too often, sizes too aggressively, holds losers too long, and exits winners too early. The root causes are structural bugs in timeframe handling, not strategy logic.

---

## PHASE 1: FIX CRITICAL BUGS (deploy first, biggest impact)

These are not strategy opinions — they are mathematical errors that corrupt every downstream decision.

### 1.1 — Fix Volatility Annualization (CRITICAL)

**The bug**: Kelly sizer annualizes vol with `sqrt(252)` which assumes daily bars. On 1-min bars, this understates volatility by ~20x, making `vol_scale` hit the 2.0 cap constantly. The engine thinks every stock is low-vol and sizes up aggressively.

**Files to change**:

`backend/organism/kelly_sizer.py:250`
```python
# BEFORE (wrong for intraday):
ann_vol = float(np.std(returns, ddof=1)) * np.sqrt(252)

# AFTER (timeframe-aware):
bars_per_day = self._bars_per_day  # 390 for 1-min, 1 for daily
ann_vol = float(np.std(returns, ddof=1)) * np.sqrt(252 * bars_per_day)
```

The `_bars_per_day` value should be derived from `ORGANISM_LIVE_TIMEFRAME`:

| Timeframe | bars_per_day |
|---|---|
| 1Min | 390 |
| 5Min | 78 |
| 15Min | 26 |
| 1Hour | 6.5 |
| 1Day | 1 |

**Also fix in `backend/organism/ml_features.py:156-171`** — same `sqrt(252)` used for `realized_vol_5` and `realized_vol_20` features. These feed into ML training, so the model has been learning on mis-scaled volatility.

```python
# Lines 156-157, 163, 171 — all need the same fix:
# BEFORE:
f["realized_vol_5"] = log_ret.rolling(5, min_periods=1).std() * math.sqrt(252)
f["realized_vol_20"] = log_ret.rolling(20, min_periods=1).std() * math.sqrt(252)

# AFTER:
_ann_factor = math.sqrt(252 * bars_per_day)
f["realized_vol_5"] = log_ret.rolling(5, min_periods=1).std() * _ann_factor
f["realized_vol_20"] = log_ret.rolling(20, min_periods=1).std() * _ann_factor
```

**Expected impact**: Immediately reduces position sizes to correct levels. With proper vol estimation, `vol_scale` will range 0.3-1.5 instead of always hitting 2.0. This alone should cut average loss size significantly.

---

### 1.2 — Fix 52-Week Feature Mislabel

**The bug**: `pct_from_52w_high` and `pct_from_52w_low` use `rolling(252)` which is 252 minutes (~4.2 hours) on 1-min bars, not 52 weeks.

**File**: `backend/organism/ml_features.py:304-307`
```python
# BEFORE (wrong for intraday):
high_52w = h.rolling(252, min_periods=20).max()
low_52w = l.rolling(252, min_periods=20).min()

# AFTER — use session high/low instead (honest label):
session_window = min(len(h), bars_per_day)  # 390 for 1-min = today's session
high_52w = h.rolling(session_window, min_periods=20).max()
low_52w = l.rolling(session_window, min_periods=20).min()
f["pct_from_52w_high"] = ...  # rename to pct_from_session_high in a future cleanup
f["pct_from_52w_low"] = ...   # rename to pct_from_session_low in a future cleanup
```

**Why not true 52-week?** Our lookback is only 500 bars (configurable). For true 52-week data on 1-min bars we'd need ~98,280 bars — impossible with current data fetch. Using session high/low is honest and still useful as a feature (measures where price sits within today's range).

**Note**: Don't rename the feature columns yet — that would break any persisted ML models. The fix is to make the computation meaningful, not to rename. Rename can happen after a full retrain cycle.

---

### 1.3 — Scale Regime Vol Thresholds for Intraday

**The bug**: Regime detection lookback periods ARE already scaled 4x for intraday (`is_intraday=True` in `live_engine.py:319`), but the vol/stress classification thresholds are NOT. On 1-min bars, `atr_ratio > 0.04` and `returns_vol > 0.03` are much harder to hit in a single bar, causing the engine to misclassify most of the session.

**File**: `backend/organism/regime.py:265-280`
```python
# Current thresholds (hardcoded, designed for daily):
if atr_ratio > 0.04:
    scores[RegimeLabel.HIGH_VOL] += 2.0
elif atr_ratio < 0.015:
    scores[RegimeLabel.LOW_VOL] += 1.5

if returns_vol > 0.03:
    scores[RegimeLabel.HIGH_VOL] += 1.0
```

**Fix**: Scale these thresholds by `sqrt(1/bars_per_day)` for intraday, or make them constructor parameters that `live_engine.py` can pass based on timeframe.

```python
# In __init__, add timeframe scaling for thresholds:
tf_scale = 1.0 / math.sqrt(bars_per_day) if is_intraday else 1.0
self._atr_high_threshold = 0.04 * tf_scale    # ~0.002 for 1-min
self._atr_low_threshold = 0.015 * tf_scale     # ~0.00076 for 1-min
self._returns_vol_threshold = 0.03 * tf_scale   # ~0.0015 for 1-min
self._vol_anomaly_threshold = 0.5              # volume-based, no scaling needed
```

Also scale the `pct_above` threshold at line 257 (currently hardcoded 0.02):
```python
self._pct_above_threshold = 0.02 * tf_scale  # price vs SMA distance
```

**Expected impact**: Regime detection becomes meaningful for intraday. The engine will actually distinguish between trending/chop/high_vol instead of classifying everything as high_vol (which is what the tick history shows — persistent high_vol for the entire session).

---

## PHASE 2: FIX STRATEGY LOGIC (deploy after Phase 1 is stable)

These are design flaws, not bugs. Each one independently costs PnL.

### 2.1 — Add Loser Time-Stop (Fix Exit Asymmetry)

**The problem**: Time-based exit (Priority 5) only exits profitable positions. Losers can linger indefinitely past `max_bars`, tying up capital and creating fat left-tail losses. This is confirmed at `adaptive_exits.py:382-388`:

```python
# Current code — only exits winners:
if max_bars > 0 and levels.bars_held >= max_bars:
    pnl_dir = (current_price - levels.entry_price) * direction
    if pnl_dir > 0:  # <-- losers skip this entirely
        return ExitSignal(True, "max_holding_period", current_price)
```

**Fix**: Add a separate loser time-stop with a buffer (e.g., 1.5x max_bars):

```python
if max_bars > 0 and levels.bars_held >= max_bars:
    pnl_dir = (current_price - levels.entry_price) * direction
    if pnl_dir > 0:
        return ExitSignal(True, "max_holding_period", current_price)

# NEW: Losers get extra time but not infinite time
loser_max = int(max_bars * 1.5) if max_bars > 0 else 0
if loser_max > 0 and levels.bars_held >= loser_max and pnl_dir <= 0:
    return ExitSignal(True, "loser_time_stop", current_price)
```

**Also add a "failure to follow through" rule** — if price hasn't moved favorably by 0.5R within the first N bars (e.g., `max_bars // 4`), exit early:

```python
# NEW: Early exit if trade isn't working
early_check = max(max_bars // 4, 5) if max_bars > 0 else 0
if early_check > 0 and levels.bars_held >= early_check:
    favorable_move = pnl_dir / max(levels.initial_risk, 0.01)
    if favorable_move < 0.5:  # hasn't made half an R in 25% of max time
        return ExitSignal(True, "failure_to_follow", current_price)
```

**Expected impact**: Directly addresses the avg_loss ($39.71) being 2x avg_win ($19.62). Losers get cut faster, capital recycles sooner, left tail shrinks.

---

### 2.2 — Replace Multiplicative Confidence with Additive Blend

**The problem**: At `live_engine.py:1468-1480`, confidence is computed as:
```python
confidence = ML_conf * (1 + breakout_score) * (1 + tension * 0.5)
```
Capped at 1.0. This:
- Saturates many candidates at 1.0 (destroys ranking quality for Kelly)
- Double-counts correlated signals (breakout and tension overlap)
- Defaults to 0.5 when ML signal is None (too generous)

**Fix**: Replace with weighted additive blend:

```python
# BEFORE:
confidence = (
    (c.ml_signal.confidence if c.ml_signal else 0.5)
    * (1.0 + breakout_score)
    * (1.0 + tension * 0.5)
)
cand_dicts.append({...  "confidence": min(confidence, 1.0), ...})

# AFTER — additive, preserves granularity:
ml_conf = c.ml_signal.confidence if c.ml_signal else 0.0  # no free baseline
confidence = (
    0.50 * ml_conf
    + 0.30 * breakout_score
    + 0.20 * min(tension, 1.0)
)
# No cap at 1.0 needed — weighted sum of [0,1] inputs stays in [0,1]
cand_dicts.append({... "confidence": confidence, ...})
```

**Weight rationale**: ML signal gets highest weight (50%) because it's the most differentiated signal. Breakout (30%) is a composite of 6 detectors. Tension (20%) is a scanner-derived score that overlaps with breakout components, so it gets the lowest weight.

**Expected impact**: Kelly's confidence scaling (`0.3 + conf * 1.2`) will now produce a meaningful range [0.3, 0.9] instead of mostly [0.9, 1.5]. Candidates will be properly ranked, and the engine will size best ideas bigger and mediocre ideas smaller.

---

### 2.3 — Convert Kelly Floors to Trade Blockers

**The problem**: At `kelly_sizer.py:206-236`, when Kelly returns near-zero (meaning backward-looking evidence says no edge), two floors force trades anyway:

```python
# Breakout floor: forces 0.7% position when Kelly says 0
if kelly_half < 0.005 and breakout_score >= 0.55:
    kelly_half = max(kelly_half, 0.01 * breakout_score)

# ML floor: forces up to 5.6% position when Kelly says 0
if kelly_half < 0.005 and confidence >= 0.5 and _regime_has_edge:
    ml_floor = 0.08 * confidence   # 0.08 * 0.7 = 0.056
    kelly_half = max(kelly_half, ml_floor)
```

**Fix**: Instead of overriding Kelly, require the edge-over-cost gate (Phase 2.4) to pass. If it doesn't, skip the trade. If you want non-dormant behavior, use a much smaller floor:

```python
# BEFORE: force trades through
if kelly_half < 0.005 and breakout_score >= 0.55:
    kelly_half = max(kelly_half, 0.01 * breakout_score)

# AFTER: only allow if edge clears cost threshold
if kelly_half < 0.005:
    if breakout_score >= 0.55 and edge_clears_cost:
        kelly_half = max(kelly_half, 0.003 * breakout_score)  # smaller floor
    else:
        kelly_half = 0.0  # skip — no edge
```

Similarly for the ML floor — halve it and require `edge_clears_cost`:
```python
if kelly_half < 0.005 and confidence >= 0.5 and _regime_has_edge and edge_clears_cost:
    ml_floor = 0.04 * confidence  # halved from 0.08
    kelly_half = max(kelly_half, ml_floor)
```

**Expected impact**: Fewer trades, but each one has positive expected edge. Trade count drops, average quality rises, PnL/trade improves.

---

### 2.4 — Add Edge-Over-Cost Gate

**The problem**: The engine places MARKET+IOC entries (`live_engine.py:2384-2385`) without checking whether the expected move can clear the spread + slippage. For intraday liquid equities, the spread is often a significant portion of the edge.

**Implementation**: Add a cost gate check before Kelly sizing. This can be simple:

```python
# In kelly_sizer.py, within the per-candidate loop:

# Estimate round-trip cost (entry spread + exit spread + slippage)
# Conservative: assume 2 * half-spread + 5bps slippage
spread_cost_pct = 0.0010  # 10bps round-trip for liquid large-cap
# Could be made per-symbol using ATR proxy: spread ~ ATR * 0.02

# Expected edge
expected_edge_pct = abs(predicted_return)

# Gate: edge must be at least 2x the cost
COST_MULTIPLIER = 2.0
edge_clears_cost = expected_edge_pct >= spread_cost_pct * COST_MULTIPLIER

if not edge_clears_cost:
    # Log it for telemetry but skip the trade
    kelly_half = 0.0
```

**For now, use a simple fixed cost estimate**. The infrastructure for real-time spread data exists (streaming quotes, slippage model in services) but wiring it in is a separate task. A fixed 10bps round-trip cost is conservative for the universe (AAPL, MSFT, AMZN, etc. typically have 1-3bps spreads, but slippage on market orders adds more).

**Expected impact**: The biggest single factor in improving Sharpe. Eliminates the "death by a thousand cuts" pattern where many small negative-expectancy trades bleed the account.

---

### 2.5 — Tighten Safety Net from 15% to 8%

**Current state**: `adaptive_exits.py` has a 15% max loss safety net (Priority 0). For an intraday strategy on liquid equities, a 15% per-position loss is extreme — it means the stop system completely failed.

**Fix**: Lower to 8% and add an intermediate alert at 5%:

```python
# BEFORE:
MAX_LOSS_PCT = 0.15

# AFTER:
MAX_LOSS_PCT = 0.08         # hard exit
MAX_LOSS_WARN_PCT = 0.05    # log warning + tighten stop by 30%
```

This aligns the per-position safety net with the portfolio-level drawdown kill (also 8%).

---

## PHASE 3: OPERATIONAL IMPROVEMENTS (deploy after Phase 2 is validated)

### 3.1 — Freeze Evolution During Structural Fixes

Before deploying Phase 1+2, set:
```env
ORGANISM_FREEZE_ADAPTATION=1
```

This prevents the evolution engine from drifting parameters while we change the foundation underneath it. After the fixes are deployed and running for 2-3 days with positive or flat PnL, re-enable evolution.

**Already supported** — no code changes needed, just the env var.

### 3.2 — Increase Retrain Interval for Intraday Stability

**Current**: `ORGANISM_RETRAIN_INTERVAL=200` ticks = ~33 minutes at 10s ticks.

For intraday on 1-min bars, this is too frequent. The model retrains before it has enough new data to meaningfully improve. During a 6.5-hour session, the model retrains ~12 times.

**Recommendation**: Increase to 600 ticks (~100 minutes, ~4 retrains/session) or 1000 ticks (~2.8 hours, ~2 retrains/session).

```env
ORGANISM_RETRAIN_INTERVAL=600
```

### 3.3 — Limit Order for Entries (Future)

Moving from MARKET+IOC to marketable limit orders caps worst-case slippage. This requires:
1. Computing a limit price: `current_price * (1 + max_slippage_bps / 10000)`
2. Changing `order_type="market"` to `order_type="limit"` with `limit_price`
3. Keeping TIF as IOC (unfilled portion cancels)

**Defer this** until the cost gate (2.4) is in place and we can measure actual slippage from telemetry. The cost gate provides 80% of the benefit with 20% of the implementation risk.

---

## IMPLEMENTATION ORDER

| Step | Change | File(s) | Risk | Dependencies |
|---|---|---|---|---|
| 0 | Freeze evolution | `.env` / `docker-compose.yml` | None | — |
| 1 | Fix vol annualization | `kelly_sizer.py`, `ml_features.py` | Low | None |
| 2 | Fix 52-week features | `ml_features.py` | Low | None |
| 3 | Scale regime thresholds | `regime.py` | Medium | None |
| 4 | Add loser time-stop | `adaptive_exits.py` | Low | None |
| 5 | Replace confidence formula | `live_engine.py` | Medium | None |
| 6 | Add edge-over-cost gate | `kelly_sizer.py` | Medium | None |
| 7 | Convert Kelly floors | `kelly_sizer.py` | Medium | Step 6 |
| 8 | Tighten safety net | `adaptive_exits.py` | Low | None |
| 9 | Increase retrain interval | `.env` / `docker-compose.yml` | None | — |
| 10 | Unfreeze evolution | `.env` / `docker-compose.yml` | None | Steps 1-9 stable |

Steps 1-3 are bug fixes — deploy together as one commit.
Steps 4-8 are strategy improvements — deploy together as a second commit.
Steps 0, 9, 10 are config changes — no code, just env vars.

---

## TESTING & VALIDATION

### Before deploying

1. **Unit tests**: Run the full backend test suite after each change:
   ```bash
   ./venv/bin/python -m pytest tests/ --timeout=15 -q --tb=line
   ```
   All 7,080+ tests must pass.

2. **Replay comparison**: Run the replay simulator on the same date range with and without changes:
   ```bash
   python -m backend.organism.replay_simulator \
     --symbols AAPL,MSFT,TSLA,AMD,NVDA,SPY \
     --start 2026-02-20 --end 2026-02-28 \
     --slippage_bps 5
   ```
   Compare: trade count, win rate, avg win/loss ratio, Sharpe, max drawdown.

3. **Spot-check**: After vol annualization fix, manually verify that `vol_scale` on a typical 1-min return series gives a sane value (should be 0.3-1.5, not always 2.0).

### After deploying (live paper trading)

Monitor for 2-3 trading days:

| Metric | Before (baseline) | Target |
|---|---|---|
| Trades/day | ~15-20 | 5-10 (fewer, higher quality) |
| Win rate | 43.9% | > 48% |
| Avg win / Avg loss | 0.49 (inverted) | > 0.8 (approaching 1.0) |
| Daily PnL | negative drift | flat to slightly positive |
| Regime distribution | mostly high_vol | varied across session |

### Telemetry to watch

Use `/organism/decisions/history` and `/organism/diagnostics/history` to check:
- Are Kelly `vol_scale` values now spread across [0.3, 1.5] instead of pinned at 2.0?
- Are regime labels rotating during the session instead of stuck on high_vol?
- Are fewer candidates passing the edge-over-cost gate?
- Are loser positions being time-stopped instead of lingering?

---

## WHAT WE CHOSE NOT TO IMPLEMENT (and why)

| Suggestion | Decision | Rationale |
|---|---|---|
| Passive limit orders | DEFER | Requires spread data plumbing; cost gate gives 80% of benefit |
| Shadow mode comparison | DEFER | Good idea but not blocking — we can compare via replay |
| Broker-native stops | DEFER | Alpaca paper doesn't fully support bracket orders for IOC entries |
| Remove all Kelly floors | PARTIAL | We halved them and tied to cost gate instead of removing — keeps engine non-dormant while preventing forced bad trades |
| True 52-week from daily data | DEFER | Requires separate daily bar fetch pipeline; session high/low is honest and useful for now |

---

## FILES CHANGED SUMMARY

| File | Changes |
|---|---|
| `backend/organism/kelly_sizer.py` | Fix annualization, add `bars_per_day` param, add cost gate, halve floors |
| `backend/organism/ml_features.py` | Fix annualization in vol features, fix 52-week rolling window |
| `backend/organism/regime.py` | Scale vol/stress thresholds for intraday timeframe |
| `backend/organism/adaptive_exits.py` | Add loser time-stop, failure-to-follow exit, tighten safety net |
| `backend/organism/live_engine.py` | Replace multiplicative confidence with additive blend |
| `.env` / `docker-compose.yml` | Freeze evolution, increase retrain interval |
