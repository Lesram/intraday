# Strategic Recommendations for AIA Review
## Date: 2026-03-12
## Context: 2 consecutive zero-trade days, negative expectancy, 158/300 trades to evolution

---

## TRACK 1: PERFECT THE SYSTEM/MECHANISM

Priority-ordered engineering work that does NOT change strategy logic:

### 1.1 [CRITICAL] Fix trade_history.csv Data Columns
**File:** `backend/organism/live_engine.py` (brain persistence section)
**Issue:** entry_source, regime_at_entry, regime_at_exit, mfe, mae, bars_held_at_exit, time_in_trade_seconds, closed_at — ALL blank/zero for every trade
**Why it matters:** Without this data, we cannot determine which entry sources work, which regimes are profitable, or how exit timing affects outcomes. Every strategy decision is currently uninformed.
**Effort:** Medium (wire existing data into CSV write path)
**Risk:** None (additive data, no logic change)

### 1.2 [CRITICAL] Investigate Regime Detector Lag
**File:** `backend/organism/regime.py`
**Issue:** Regime shows `trending_up` while SPY is -1.52%. This blocks the inverse ETF regime-flip logic that exists in `_regime_alignment()`.
**Why it matters:** The organism has SH and PSQ in its universe specifically for down-tape protection. If the regime detector doesn't detect down tapes, these symbols are dead weight.
**Effort:** Medium (investigate lookback window, feature inputs, potentially adjust parameters)
**Risk:** Low-Medium (regime changes affect all entry decisions)

### 1.3 [HIGH] Wire Trades to realized_trades DB Table
**File:** `backend/organism/live_engine.py` (trade closing section)
**Issue:** `realized_trades` table has 0 rows despite 158 trades
**Why it matters:** Dashboard, API, and any external tool looking at the DB sees zero trade history
**Effort:** Low (add INSERT after trade close)
**Risk:** None (additive)

### 1.4 [HIGH] Scanner Sensitivity for Non-Breakout Patterns
**File:** `backend/organism/alpha_scanner.py`
**Issue:** XOM (+2.43% on 3/11, +1.29% on 3/12), SH (+1.58%), PSQ (+1.76%), CRM (+2.65%) — none produced as candidates. The breakout scanner only detects sharp intraday breakouts, missing gradual sector rotations and inverse ETF rallies.
**Why it matters:** 7/22 symbols were winners today. None were detected.
**Effort:** High (may need new scan mode for sector rotation / mean-reversion)
**Risk:** Medium (new signal source could generate noise)

### 1.5 [MEDIUM] Alpaca Connection Resilience
**File:** `backend/services/positions_service.py:115`
**Issue:** 9 disconnects in one session causing tick failures
**Fix:** Add retry with exponential backoff (3 attempts, 1s/2s/4s) around `get_all_positions()`
**Effort:** Low
**Risk:** None

### 1.6 [MEDIUM] Brain Manifest Sync
**Issue:** Manifest shows 142 trades, engine has 158. Brain persistence may skip saves.
**Effort:** Low (investigate save trigger)
**Risk:** None

---

## TRACK 2: IMPROVE THE TRADING ALGORITHM

Strategy changes that require careful evaluation. **Recommend fixing Track 1 items FIRST** so decisions are data-informed.

### 2.1 [HIGH] Fix Win/Loss Asymmetry
**Current state:** Avg win = $17.70, Avg loss = $24.86 (loss is 40% larger)
**Expected value per trade:** -$6.56 (negative)
**Possible causes and interventions:**

a) **Stops too wide** — The ATR multipliers (2.5-4.0×) may be letting losers run too far
   - Investigate: What % of losses hit the stop vs. other exit reasons?
   - Intervention: Tighten stops (e.g., 2.0-3.0× ATR) and measure impact on win rate

b) **Take-profits too tight** — Partial take-profit may be cutting winners before they run
   - Investigate: What's the MFE (max favorable excursion) of winning trades vs. take-profit level?
   - Intervention: Widen take-profit or use trailing mechanism
   - **BLOCKED BY:** trade_history.csv doesn't record MFE (DEFER-001)

c) **Entry quality** — 57% of trades are losers
   - Investigate: Which symbols/regimes have highest win rates?
   - **BLOCKED BY:** trade_history.csv doesn't record regime or entry_source (DEFER-001)

### 2.2 [HIGH] Solve the Starvation Problem
**Current state:** 2 consecutive zero-trade days. Need 142 more trades to reach evolution threshold.
**Risk:** If confidence scores remain near-zero, the organism may go days/weeks without trading, never reaching 300 trades, and never evolving.

**Options (ranked by risk):**
1. **Wait and observe** (lowest risk) — Market conditions may produce higher breakout scores naturally. Cost: slow learning, may take months.
2. **Lower confidence floor in learning mode** (medium risk) — Drop from 0.25 to 0.15 with halved position sizes. Cost: more losing trades, faster learning.
3. **Add time-based exploration** (higher risk) — Take small random positions to gather data. Cost: guaranteed random losses, but rapid data accumulation.
4. **Restructure confidence formula** (highest risk) — The formula `0.65×breakout + 0.35×tension` may systematically produce low scores. Need to understand why.

**Recommendation:** Option 2, but ONLY after DEFER-001 is fixed so we can measure impact.

### 2.3 [MEDIUM] Enable Inverse ETF Trading
**Current state:** SH and PSQ are in the universe but never trade. The organism has regime-flip logic in `_regime_alignment()` that swaps trending_up/trending_down for inverse ETFs.
**Problem:** The regime detector rarely reports trending_down (see 1.2), and the breakout scanner doesn't produce these as candidates.
**Fix requires:**
1. Fix regime detection (Track 1, item 1.2)
2. Add scanner support for inverse ETF patterns (Track 1, item 1.4)
3. Validate that regime-flip logic works correctly

### 2.4 [MEDIUM] Add Sector Rotation Detection
**Today's example:** Tech sold off, defensives rallied. CRM +2.65%, WMT +1.49%, COST +1.12%.
**Current gap:** The breakout scanner looks for volume spikes and price breakouts, not relative strength across sectors.
**Possible approach:** Add a "relative strength" signal that detects when a symbol is outperforming SPY by >1% on the day. This is not a breakout — it's a rotation signal.
**Risk:** New signal type needs separate validation.

### 2.5 [LOW] Improve ML Training Path
**Current state:** 21 training attempts, all rejected. Latest: accuracy 58.4%, calibration error 34.5%, non-monotonic.
**Root cause:** 158 trades is likely insufficient for a well-calibrated model. Also, with all 6 columns blank (entry_source, regime, etc.), the model has less informative features.
**Path forward:**
1. Fix data quality (Track 1, item 1.1)
2. Accumulate to 300+ trades
3. Retrain with richer features
4. If still failing, evaluate simpler models (logistic regression instead of current approach)

---

## PRIORITY EXECUTION ORDER

```
Phase 1 (This Week — No Strategy Changes):
  1. DEFER-001: Fix trade_history.csv columns
  2. INV-003: Investigate regime detector
  3. DEFER-002: Wire realized_trades to DB
  4. INV-004: Add Alpaca retry logic

Phase 2 (Next Week — Informed Strategy Tuning):
  5. Analyze trade data with fixed columns
  6. Determine win/loss asymmetry root cause
  7. Decide on starvation solution (lower gate vs. wait)
  8. Scanner sensitivity improvements

Phase 3 (Week 3+ — New Capabilities):
  9. Inverse ETF activation
  10. Sector rotation signal
  11. ML model retraining with richer features
```

---

## KEY PRINCIPLE

**Do not change strategy logic until the data tells you what's broken.**

Right now, we know:
- Expectancy is negative (-$6.56/trade)
- Win rate is 43%
- Losses are 40% larger than wins

We do NOT know:
- Which entry source works best (blank column)
- Which regimes are profitable (blank column)
- What the actual MFE/MAE distribution looks like (blank columns)
- Whether the stop levels are optimal (no MFE/MAE data)

Fix the data first. Then let the data guide the strategy changes.
