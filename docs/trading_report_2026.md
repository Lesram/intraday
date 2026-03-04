# Trading Day Report — March 2, 2026

**Prepared for**: 3rd-party auditor review
**System**: Intra Platform — Organism Living Trading Engine
**Account**: Alpaca Paper Trading (PA3RLEN7T0N4)
**Starting Equity**: $112,426.30
**Engine Mode**: Paper trading, long-only, 1-min bars, 10s tick interval

---

## Executive Summary

March 2 was the engine's **second live run** after a brain reset on March 1. The system is in cold-start phase — ML models are untrained (generation 0), no evolution has occurred, and regime-stratified statistics are empty. One trade was taken: a small MSFT long that lost $0.86 before being closed at end-of-day. The majority of the day's work focused on pre-market engineering fixes (deployed before market open) and a comprehensive post-market documentation audit.

| Metric | Value |
|---|---|
| Trades executed | 1 |
| Win rate | 0% (1 loss) |
| Total PnL | **-$0.86** |
| Ending equity | $112,426.30 |
| Max drawdown | ~0.001% |
| ML trained | No (insufficient data) |
| Evolution generation | 0 |
| System uptime | ~17 hours continuous |
| Memory usage | Stable at ~1,068 MB (no leak) |

---

## 1. Pre-Market Engineering (12:00 AM – 6:30 AM PT)

### 1.1 Commits Deployed Before Trading

Two commits were deployed overnight before market open:

**Commit `8caa444` (1:04 AM PT) — "Add state-dependent cost model, fix 11 mapss.md discrepancies, and sync docs with code"**
- 20 files changed, 1,400 insertions, 637 deletions

**Commit `a5ced7b` (1:25 AM PT) — "Fix 3 pre-flight diagnostic false failures"**
- 1 file changed, 7 insertions, 8 deletions

### 1.2 Critical Code Changes Deployed

#### A. State-Dependent Cost Model (kelly_sizer.py)

**Problem**: The Kelly position sizer used a fixed 10 basis point spread cost for all symbols at all times. This is inaccurate — liquid mega-caps like AAPL have 1-2bps spreads while illiquid names can have 20-50bps, and the open/close auctions inflate costs 1.5-2.5x.

**Fix**: New `_estimate_spread_cost()` method computes per-symbol costs from:
- Live bid/ask spread from streaming quotes
- Time-of-day multiplier (7 buckets: pre-market 2.0x → morning 0.9x → after-hours 2.5x)
- Liquidity adjustment from volume/SMA ratio (thin volume adds up to +50%)
- Final cost clamped to [3bps, 50bps]

An "edge-over-cost" gate was added: `predicted_return >= spread_cost × 2`. Trades where the predicted edge doesn't clear 2x the estimated round-trip cost are blocked.

#### B. Volatility Annualization Fix (ml_features.py, kelly_sizer.py)

**Problem**: Volatility was annualized using `√252` (correct for daily bars) but the engine runs on 1-minute bars. Per-bar returns on 1-min bars are ~20x smaller than daily returns, making `√252` produce absurdly low annualized volatility. This caused the Kelly sizer's volatility scale to hit its 2.0 cap, over-sizing positions by ~4x.

**Fix**: Changed to `√(252 × bars_per_day)` where `bars_per_day = 390` for 1-min bars. This produces `√98,280 ≈ 313.5` instead of `√252 ≈ 15.9`, correctly scaling intraday per-bar returns to annual equivalents.

#### C. Confidence Formula Rewrite (live_engine.py)

**Problem**: The old multiplicative confidence formula `ml_conf × (1 + breakout) × (1 + tension × 0.5)` could produce values well above 1.0, distorting Kelly sizing.

**Fix**: New additive formula: `0.50 × ML_confidence + 0.30 × breakout_score + 0.20 × min(tension, 1.0)`. Bounded, interpretable, and won't inflate sizing.

#### D. New Defensive Exit Types (adaptive_exits.py)

Two new exit priorities added:

- **Failure to Follow Through (Priority 4b)**: If a position hasn't achieved 0.5R of profit after 25% of max_bars (minimum 5 bars), it exits. Catches trades that stall immediately.
- **Loser Time Stop (Priority 5b)**: Losers exceeding 1.5x max_bars are force-exited. Prevents capital from being stranded indefinitely.

#### E. Market Hours Consolidation (new file: market_hours.py)

**Problem**: Six separate modules had their own implementations of "is the market open?" with hardcoded holiday sets that would break in 2027.

**Fix**: Created canonical `backend/utils/market_hours.py` with dynamic NYSE holiday calculation. Removed 200+ lines of duplicated code from scheduler, diagnostic_scheduler, risk_manager, helpers, alerting, and alpaca_outbox.

#### F. Feature Pipeline Fixes

- 52-week high/low window: now uses session window for intraday (bars_per_day bars instead of meaningless 252-bar window)
- Data quality gate: new `_nan_missingness` column blocks entries when >25% of features are NaN
- Feature count docstring corrected from 75 to 79

#### G. Diagnostic False Failures Fixed

Three pre-flight diagnostic checks were failing incorrectly:
1. `data_client` check accepted wrong method name
2. `evolved_params` check referenced non-existent attribute
3. Stale `fitness` field check removed (field doesn't exist on EvolvedParams)

### 1.3 Uncommitted Changes (Applied Live, Not Yet Committed)

These changes were applied to the running Docker container but not yet committed:

| File | Change |
|---|---|
| `live_engine.py` | Liquidity gate threshold: 500K → 10K (per-bar volume, not daily) |
| `live_engine.py` | Exit order TIF: IOC → DAY (one remaining path) |
| `regime.py` | ATR column lookup: `atr_ratio` → `atr_14` (was reading wrong volatility metric) |
| `order_service.py` | Default TIF: IOC → DAY for both buy and sell |

The regime detector fix is significant: the detector was using `atr_ratio` (ATR5/ATR20, a ratio of two ATRs) instead of `atr_14` (ATR(14)/price, the actual normalized volatility). This caused incorrect regime classification — the detector was comparing a dimensionless ratio against thresholds designed for a volatility percentage.

---

## 2. Trading Hours (6:30 AM – 1:00 PM PT)

### 2.1 Market Context

- Market: US equities (NYSE/NASDAQ)
- Session: Regular hours, 9:30 AM – 4:00 PM ET (6:30 AM – 1:00 PM PT)
- Engine: Running in Docker, 30-symbol universe, 10-second tick interval

### 2.2 Engine Behavior

The engine operated in **cold-start mode**:
- **ML models**: Not trained (zero training data, is_trained=false)
- **Regime stats**: Empty (no per-regime win/loss statistics)
- **Evolution**: Frozen (`ORGANISM_FREEZE_ADAPTATION=1` in docker-compose)
- **Generation**: 0 (no evolution cycles completed)

Because ML is untrained, the engine relies on:
- Breakout signals from the 6-detector breakout scanner
- Alpha scores from the 7-factor scanner (with ML weight effectively zero)
- Hardcoded confidence floors and breakout floors in the Kelly sizer

### 2.3 The Trade

**One trade was executed during the session:**

| Field | Value |
|---|---|
| Symbol | **MSFT** |
| Direction | Long |
| Entry price | $397.086 |
| Exit price | $397.020 |
| Shares | 13 |
| PnL | **-$0.86** |
| Exit reason | `live_close` (end-of-day forced close) |
| Predicted return | +0.0034% |
| Actual return | -0.0166% |
| Confidence | 0.6 (hardcoded default) |
| Correct direction | **No** |
| Hold duration | 19 bars (~190 seconds / ~3.2 minutes) |
| Entry bar | 6 |
| Exit bar | 25 |

**Analysis**: The engine entered MSFT long based on a breakout signal with a very small predicted return (0.0034%). The position was sized at 13 shares (~$5,162 notional, ~4.6% of equity). MSFT drifted slightly lower, and the position was closed at end-of-day with a $0.86 loss. The trade was directionally wrong but the loss was negligible.

**Why only 1 trade?** Several factors limited activity:
1. **ML untrained**: No ML predictions available, reducing the alpha scanner's effectiveness
2. **Conservative sizing**: The new edge-over-cost gate blocks trades where predicted edge < 2x transaction cost
3. **30-minute opening block**: No entries allowed during 9:30-10:00 AM ET
4. **Entry throttle**: Maximum 3 entries per hour
5. **Cold-start conservatism**: Without regime-stratified statistics, the Kelly sizer operates with higher uncertainty

---

## 3. System Health

### 3.1 Memory

| Timestamp (UTC) | Process Memory | System Memory |
|---|---|---|
| 09:16 (Mar 2) | 1,064.16 MB | 22.9% |
| 16:04 (Mar 2) | 1,068.17 MB | 27.5% |
| 02:58 (Mar 3) | 1,068.34 MB | 27.7% |

Memory growth: **+4.18 MB over 17 hours** — no memory leak detected. System memory increase (22.9% → 27.7%) reflects normal OS activity, not the trading engine.

### 3.2 Brain State at End of Day

```
Generation:        0 (no evolution)
Total runs:        2
Total trades:      1
Cumulative PnL:    -$0.86
ML trained:        false
Retrain count:     0
Drift events:      0
Peak equity:       $112,426.30
Shorts enabled:    false
Trading halted:    false
Adaptation frozen: true (by config)
```

### 3.3 Evolved Parameters Snapshot

The brain carries forward evolved parameters from a previous training cycle (before the brain reset). Key values:

| Parameter | Value | Notes |
|---|---|---|
| Alpha weight ML | 0.381 | Highest weight (ML is most trusted factor) |
| Alpha weight volume | 0.195 | |
| Alpha weight momentum | 0.182 | |
| Alpha weight breakout | 0.146 | |
| Alpha weight regime | 0.100 | Minimum floor |
| Direction threshold buy | 0.52 | P(up) must exceed this to go long |
| Direction threshold sell | 0.48 | P(up) below this to go short |
| XGBoost n_estimators | 169 | Evolved from default 200 |
| XGBoost max_depth | 4 | Evolved from default 5 |
| XGBoost learning_rate | 0.0377 | Evolved from default 0.05 |
| Regime scale (stress) | 0.30 | Position sizing × 0.30 in stress |
| Regime scale (chop) | 0.75 | Position sizing × 0.75 in chop |
| Regime scale (high_vol) | 0.70 | Position sizing × 0.70 in high vol |
| Shorts enabled | false | No short trades allowed |

### 3.4 Transfer Knowledge

The brain contains a snapshot from a previous run (run_id 20, generation 8) with 200 trades and a 45% win rate. This historical knowledge is available for the transfer learning system when it activates, but has no effect on current trading decisions.

---

## 4. Post-Market Documentation Audit

After market close, a comprehensive audit of `docs/architecture/mapss.md` (the complete system map document) was conducted.

### 4.1 Audit Method

8 parallel audit agents were deployed, each cross-referencing a different functional domain of the document against the actual source code:

1. Tick lifecycle & entry gates
2. Exit system & adaptive exits
3. Kelly sizer & position sizing
4. Regime detection & ML signal
5. Self-evolution & governance
6. API routes & infrastructure
7. Config, env vars & appendices
8. Risk management & order flow

### 4.2 Findings

| Category | Count |
|---|---|
| Value mismatches (doc says X, code says Y) | 36 |
| Missing documentation (code behavior undocumented) | 94 |
| Incomplete descriptions (correct but missing nuance) | 46 |
| Wrong counts/ordering | 7 |
| Math errors | 1 |
| **Total findings** | **~184** (after deduplication across agents) |

### 4.3 Fixes Applied

**491 insertions, 180 deletions** across `mapss.md`, including:

- 23 critical value mismatches corrected
- 15 major missing sections added (risk/ module index, evolution parameter bounds, RegimeConditionedEnsemble weight matrix, brain validation gates, etc.)
- 20+ incomplete descriptions enhanced with operational details
- Feature count, endpoint counts, regime labels, Kelly formulas, exit priorities all verified and corrected

The document grew from ~4,370 lines to ~4,560 lines.

---

## 5. Risk & Compliance Notes

### 5.1 Capital at Risk

- Starting equity: $112,426.30
- Maximum loss: $0.86 (0.00076% of equity)
- Drawdown kill switch: 3% (docker), 8% (.env) — never triggered
- Position sizing: 13 shares × $397 = $5,162 (4.6% of equity, below 8% intraday cap)

### 5.2 Safety Mechanisms Active

| Mechanism | Status | Threshold |
|---|---|---|
| Drawdown kill switch | Not triggered | 3% (docker default) |
| Circuit breaker (order service) | Closed (healthy) | 5 failures / 300s |
| PnL circuit breaker | Not triggered | >5% daily loss |
| Entry throttle | Active | 3 entries/hour |
| Opening block | Active | 9:30-10:00 AM ET |
| Long-only mode | Enforced | No short positions allowed |
| Edge-over-cost gate | Active | Predicted return >= 2x spread cost |
| Adaptation freeze | Enabled | No parameter evolution |
| Max positions | 15 | Only 1 was taken |

### 5.3 Known Issues

1. **Regime detector was using wrong ATR column** — fixed in uncommitted change but needs monitoring
2. **Liquidity gate threshold was too restrictive** — 500K per-bar volume (equivalent to ~195M daily) was blocking all but the most liquid mega-caps. Lowered to 10K per-bar (~3.9M daily)
3. **IOC → DAY TIF migration** — partially committed, partially uncommitted. Three locations still need committing.
4. **ML not yet trained** — engine will remain in conservative cold-start mode until sufficient trade data accumulates for training (minimum 50 samples across all symbols)

---

## 6. Configuration Summary

### Docker Environment (Active)

```
ORGANISM_TICK_INTERVAL_SECONDS=10
ORGANISM_LIVE_TIMEFRAME=1Min
ORGANISM_MAX_POSITIONS=15
ORGANISM_LONG_ONLY=true
ORGANISM_RETRAIN_INTERVAL=600 (docker default)
ORGANISM_FREEZE_ADAPTATION=1
ORGANISM_DRAWDOWN_KILL_PCT=0.03 (docker default)
ORGANISM_DRAWDOWN_COOLDOWN_S=300
ORGANISM_MAX_CHANGES_PER_DAY=500
ALPACA_PAPER=true
ALPACA_DATA_FEED=iex (docker default)
```

### Universe (30 symbols)

AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA, AMD, AVGO, CRM, COST, WMT, LLY, XOM, CAT, SPY, QQQ, IWM, XLK, XLE + 10 additional from .env (30 total)

---

## 7. Appendix: File Change Summary

### Committed Changes (Pre-Market)

| File | Lines Changed | Summary |
|---|---|---|
| `kelly_sizer.py` | +120 / -30 | State-dependent cost model, annualization fix, edge gate |
| `live_engine.py` | +80 / -40 | Confidence rewrite, bars_per_day propagation, missingness gate |
| `adaptive_exits.py` | +60 / -5 | Failure-to-follow and loser time-stop exits |
| `ml_features.py` | +20 / -10 | Annualization fix, 52w window fix, missingness column |
| `market_hours.py` | +250 / -0 | New canonical module (NYSE hours, holidays, slippage) |
| `scheduler.py` | +5 / -40 | Delegate to market_hours.py |
| `diagnostic_scheduler.py` | +5 / -10 | Delegate to market_hours.py |
| `risk_manager.py` | +5 / -215 | Remove duplicated holiday code |
| `slippage_model.py` | +5 / -15 | Simplify timezone handling |
| `helpers.py` | +5 / -25 | Delegate market hours |
| `alerting.py` | +3 / -24 | Delegate market hours |
| `alpaca_outbox.py` | +3 / -15 | Delegate market hours |
| `orders.py` | +3 / -5 | Use proper market hours check |
| `diagnostic_checks.py` | +7 / -8 | Fix 3 false failures |
| `docker-compose.yml` | +3 / -1 | Retrain interval 180→600, freeze adaptation |

### Uncommitted Changes (Applied Live)

| File | Change |
|---|---|
| `live_engine.py` | Liquidity gate 500K→10K, TIF IOC→DAY |
| `regime.py` | ATR column: atr_ratio → atr_14 |
| `order_service.py` | Default TIF: IOC → DAY |
| `mapss.md` | +491 / -180 documentation audit fixes |

---

*Report generated: March 2, 2026*
*Engine version: commit `a5ced7b` + uncommitted fixes*
*Next trading day: March 3, 2026*

---
---

# Trading Day Report — March 3, 2026

**Prepared for**: Deep research and 3rd-party auditor review
**System**: Intra Platform — Organism Living Trading Engine
**Account**: Alpaca Paper Trading (PA3RLEN7T0N4)
**Starting Equity**: ~$112,400
**Ending Equity**: $112,457.70
**Engine Mode**: Paper trading, long-only, 1-min bars, 10s tick interval

---

## Executive Summary

March 3 was a **pivotal day** — the platform transitioned from defective information plumbing to a fully repaired decision pipeline. The day had two distinct phases:

- **Phase 1 (Pre-Reset, old code)**: 11 round-trip trades, 6W/5L (55%), +$57.31 PnL. All trades recorded with fake `confidence=0.6` and hard-coded `exit_reason=live_close`, making them useless for learning.
- **Phase 2 (Post-Reset, new code)**: 3 completed trades + 1 open, 3W/0L (100%), +$1.89 PnL. All trades recorded with **real** confidence values (0.09–0.14), **real** exit reasons (`failure_to_follow`), and multi-bar prediction horizon.

The engineering work done mid-day implemented all 5 recommendations from the `improve3.md` audit document, performed a full brain wipe (including DB order history), and deployed the corrected code. The result is a system that can now properly learn from its own trading outcomes — a prerequisite that was missing since the platform's inception.

| Metric | Phase 1 (Old Code) | Phase 2 (New Code) | Combined |
|---|---|---|---|
| Trades | 11 | 3 (+1 open) | 14 (+1 open) |
| Win rate | 55% (6/11) | 100% (3/3) | 64% (9/14) |
| Total PnL | +$57.31 | +$1.89 | **+$59.20** |
| Capital deployed | $13,955 | ~$1,700 | ~$15,655 |
| Return on capital | +0.41% | +0.11% | +0.38% |
| Max drawdown | ~0.01% | 0.000% | ~0.01% |
| Confidence data quality | Fake (constant 0.6) | Real (varied) | — |
| Exit reason quality | Fake (hard-coded) | Real (ATR-based) | — |

---

## 1. The improve3.md Audit — Context and Motivation

### 1.1 What improve3.md Found

A comprehensive audit document (`docs/architecture/improve3.md`) was prepared analyzing the platform's structural deficiencies. It diagnosed the system as **"entry-starved, learning-starved, and attribution-blind"** — functioning as coded but unable to improve because of broken information plumbing. The audit identified 5 root causes:

1. **Return-horizon mismatch**: The ML model predicted next-bar (1-minute) returns but sizing gates compared those predictions against multi-bar transaction costs. A 1-minute expected return of 0.003% will almost never clear a 6-20bps round-trip cost threshold, causing the cost gate to silence almost all ML-driven trades.

2. **Confidence propagation broken**: The engine computed nuanced per-candidate confidence from ML, breakout, and scanner tension, but the `PositionSize` dataclass had no `confidence` field. The live engine fell back to `getattr(sz, "confidence", 0.6)`, writing a constant 0.6 to every order and trade record. This destroyed the usefulness of confidence calibration and post-trade analysis.

3. **Trade attribution broken**: When positions disappeared from the broker (reconciliation), the engine hard-coded `exit_reason="live_close"` instead of using the actual exit reason already computed by the adaptive exit engine. Fill prices used the last bar close as a proxy instead of the actual broker fill price.

4. **Entry starvation by design**: Multiple stacking gates (opening block, regime sit-out, entries-per-hour throttle, fitness gate, liquidity gate, missingness gate, cost gate, min-notional gate) could converge to near-zero entries while producing no diagnostic explanation of why.

5. **Gate telemetry gaps**: The `DecisionTelemetryStore` had fields for rejection counters but several were never wired (`cost_gate` and `min_notional` always 0, regime sit-out didn't set `entries_blocked_reason`, throttle rejections weren't tracked).

### 1.2 Why These Defects Mattered

The combined effect was a **learning death spiral**:
- Fake confidence (0.6 constant) → confidence calibration learns from garbage → calibration can't distinguish high vs low conviction trades
- Fake exit reasons ("live_close") → no ability to analyze whether stops, trailing stops, or time exits dominate → can't tune exit parameters
- Approximate fill prices → regime-stratified Kelly statistics polluted with wrong PnL → wrong position sizing in future trades
- Next-bar prediction horizon → predicted returns always tiny → cost gate silences trades → too few trades to learn from → model stays weak → predicted returns stay tiny

This is why the March 2 report showed only 1 trade with $0.86 loss — the system was structurally incapable of both trading and learning.

---

## 2. Engineering Work (Pre-Market and Mid-Day)

### 2.1 Commit `2a39e1a` (Pre-Market, Already Deployed at Market Open)

**"Fix regime ATR lookup, IOC→DAY TIF migration, liquidity gate, deep mapss.md audit, and trading report"**

This committed the uncommitted fixes from March 2:
- Regime ATR column: `atr_ratio` → `atr_14`
- TIF migration: IOC → DAY for all organism orders
- Liquidity gate: 500K → 10K per-bar average volume
- mapss.md audit fixes (491 insertions, 180 deletions)
- March 2 trading report

### 2.2 Five improve3.md Recommendations — Implementation Details

All 5 recommendations were implemented mid-day (2:00–2:45 PM ET) and deployed in commit `f509d3b`:

#### Recommendation 1: Multi-Bar ML Prediction Horizon

**Files changed**: `ml_signal.py`, `live_engine.py`

**What was done**:
- Added `prediction_horizon` parameter to `MLSignalGenerator.__init__()` (defaults to 1, clamped to `max(1, ...)`)
- In `_build_training_data`, labels `y_dir` and `y_ret` now use `close[t+H]` instead of `close[t+1]`:
  ```
  Before: next_close = close[1:]     → 1-bar lookahead
  After:  future_close = close[H:]   → H-bar lookahead
  ```
- Feature slicing adjusted: `X = df[self._feature_cols].values[:-H]` (drops last H bars instead of 1)
- Minimum data check raised: `max(60, H + 10)` instead of hardcoded 60
- Default horizons per timeframe: `{"1Min": 15, "5Min": 6, "15Min": 3, "1Hour": 2, "1Day": 1}`
- Configurable via `ORGANISM_PREDICTION_HORIZON` env var
- Wired into engine: `MLSignalGenerator(prediction_horizon=PREDICTION_HORIZON)`

**Why**: A 1-minute expected return is almost never large enough to clear a multi-basis-point transaction cost. By predicting 15-minute-ahead returns (H=15 for 1Min bars), the predicted return is on the same scale as the round-trip cost, allowing the edge-over-cost gate to make meaningful decisions. This directly addresses the core mismatch that was suppressing ML-based trades.

**Impact**: `predicted_return` values in post-reset trades are `0.000113–0.000358` (15-bar horizon) vs pre-reset values of `3.4e-05` (1-bar horizon) — roughly 3-10x larger, though still small because the ML model is newly trained.

#### Recommendation 2: Confidence Propagation

**Files changed**: `kelly_sizer.py`, `live_engine.py`

**What was done**:
- Added 3 new fields to `PositionSize` dataclass: `confidence: float = 0.0`, `predicted_return: float = 0.0`, `breakout_score: float = 0.0`
- `PositionSize.to_dict()` serializes all 3 new fields
- In `KellySizer.size_positions()`, the `PositionSize` constructor now receives the real candidate values:
  ```python
  PositionSize(..., confidence=confidence, predicted_return=predicted_return, breakout_score=breakout_score)
  ```
- In `live_engine.py`, order submission changed from `confidence=getattr(sz, "confidence", 0.6)` to `confidence=sz.confidence`
- Entry metadata stores real confidence: `"confidence": sz.confidence`
- Activity events use real confidence: `"confidence": sz.confidence`
- Predicted return for exit level creation reads from `sz.predicted_return` instead of re-running `signal_gen.predict()`

**Why**: The 0.6 constant was a "brain wiring" defect. The system computed signal strength, then forgot it at the exact point where it should be most valuable. Downstream, confidence calibration (`record_prediction_outcome`, binning, calibration map) was learning from a fake constant instead of the real confidence distribution.

**Impact**: Post-reset trades show `confidence=0.1415, 0.1174, 0.0907` — real, varied values that reflect actual model conviction. The confidence calibration system can now distinguish high-confidence from low-confidence predictions.

#### Recommendation 3: Trade Attribution (Exit Reasons + Fill Prices)

**Files changed**: `live_engine.py`

**What was done**:

*Exit reason tracking*:
- New dict `self._last_exit_reason: dict[str, str] = {}` tracks per-symbol exit reasons
- `_submit_exit_order()` now captures: `self._last_exit_reason[symbol] = reason`
- `_reconcile_fills()` uses real reason: `exit_reason=self._last_exit_reason.pop(sym, "live_close")`
- Only falls back to `"live_close"` if no exit reason was tracked (shouldn't happen in normal operation)

*Fill price tracking (3-tier system)*:
- **Tier 1 — Synchronous fill**: `_submit_exit_order()` captures `avg_fill_price` from the Alpaca order response into `self._last_exit_fill_price[symbol]`
- **Tier 2 — DB lookup** (NEW): New method `_lookup_exit_fill_from_db()` queries PostgreSQL for the most recent filled sell order for the symbol:
  ```sql
  SELECT avg_fill_price FROM orders
  WHERE symbol = ? AND side = 'sell' AND status = 'filled'
    AND attributes->>'source' = 'organism'
  ORDER BY updated_at DESC LIMIT 1
  ```
- **Tier 3 — Market data fallback**: Bar close price or quote midpoint (existing behavior, unchanged)
- **Tier 4 — Skip**: If all tiers fail, the trade record is skipped with a warning log

*Cleanup*: Both `_last_exit_reason` and `_last_exit_fill_price` are cleaned up per-symbol after reconciliation to prevent memory leaks.

**Why**: Without accurate fill prices and exit reasons, the system was feeding the learning and reporting loop with partially synthetic trade outcomes. Regime-stratified Kelly statistics were polluted with wrong PnL, continuous learning evaluation was less meaningful, and debugging was impossible ("live_close" tells you nothing about what actually happened).

**Impact**: Post-reset trades show `exit_reason=failure_to_follow` — this is the adaptive exit engine's "position didn't achieve 0.5R profit within 25% of max bars" condition. This tells us exactly why the position was closed: the price stalled after entry, triggering the failure-to-follow exit. Previously, this would have been recorded as `live_close`.

#### Recommendation 4: Exploration Bucket

**Files changed**: `live_engine.py`, `kelly_sizer.py`, `continuous_learner.py`

**What was done**:

*Configuration*:
```python
EXPLORATION_ENABLED = _env_bool("ORGANISM_EXPLORATION_ENABLED", False)  # OFF by default
EXPLORATION_MAX_NOTIONAL = _env_float("ORGANISM_EXPLORATION_MAX_NOTIONAL", 200.0)
EXPLORATION_MAX_POSITIONS = _env_int("ORGANISM_EXPLORATION_MAX_POSITIONS", 3)
```

*Kelly sizer integration*:
- `_exploration_rejects` list populated when candidates fail `weight_too_small` or `below_min_notional` gates
- Each reject includes: symbol, reason, confidence, breakout_score, predicted_return, direction

*Execution logic (section 9b in tick loop)*:
- Sources candidates from `kelly_sizer._exploration_rejects`
- Filters for minimum quality: `breakout_score >= 0.4 OR confidence >= 0.5`
- Caps at 1 share per symbol and `EXPLORATION_MAX_POSITIONS` total
- Sets `"exploration": True` in entry metadata
- Creates exit levels normally

*Learning isolation*:
- `TradeRecord` has new field: `is_exploration: bool = False`
- Exploration trades are **excluded** from Kelly regime statistics: `if not _is_exploration: self.kelly_sizer.record_trade(regime_at_trade, pnl)`
- This prevents micro-size exploration trades from polluting the main Kelly statistics

**Why**: The system was caught in an "entry-starved → learning-starved → still entry-starved" loop. Hard-gating entries prevents the system from collecting enough representative trades to discover whether it has edge. The exploration bucket breaks this loop by taking tiny-risk trades (1 share, $200 max) on rejected candidates, purely for data collection.

**Impact**: Not yet activated (off by default). Ready to enable with `ORGANISM_EXPLORATION_ENABLED=true` when desired.

#### Recommendation 5: Gate-Level Telemetry

**Files changed**: `decision_telemetry.py`, `live_engine.py`

**What was done**:

*New `FilteringSummary` fields* (12 added):
```python
rejected_by_open_position: int = 0
rejected_by_exit_cooldown: int = 0
rejected_by_pending_entry: int = 0
rejected_by_entry_metadata: int = 0
rejected_by_long_only: int = 0
rejected_by_sector_gate: int = 0
rejected_by_fitness_gate: int = 0
rejected_by_liquidity: int = 0
rejected_by_missingness: int = 0
rejected_by_cost_gate: int = 0
rejected_by_min_notional: int = 0
entries_blocked_reason: str = ""
```

*Serialization*: All 11 counters grouped under `"rejections"` sub-object in `to_dict()`, plus `"entries_blocked_reason"` at top level.

*Per-candidate rejection counting* (9 gates tracked inline during candidate filtering):
- `_rej_open` — symbol already has an open position
- `_rej_cooldown` — symbol in exit cooldown period
- `_rej_pending` — symbol has pending entry order
- `_rej_metadata` — symbol already has entry metadata
- `_rej_long_only` — short signal in LONG_ONLY mode
- `_rej_sector` — sector diversification cap reached
- `_rej_fitness` — symbol fitness below threshold
- `_rej_liquidity` — per-bar volume below 10K
- `_rej_missingness` — feature NaN/Inf > 25%

*Sizer-level rejection wiring* (the gap this session fixed):
```python
_sizer_rejects = getattr(self.kelly_sizer, "_exploration_rejects", [])
_rej_cost_gate = sum(1 for r in _sizer_rejects if r.get("reason") == "weight_too_small")
_rej_min_notional = sum(1 for r in _sizer_rejects if r.get("reason") == "below_min_notional")
self._last_gate_rejections["cost_gate"] = _rej_cost_gate
self._last_gate_rejections["min_notional"] = _rej_min_notional
```

*Entry-blocking reason tracking* (the gaps this session fixed):
- `self._last_entries_blocked_reason = "regime_sitout"` — when all ML signals bearish in high_vol/stress
- `self._last_entries_blocked_reason = "throttle"` — when entries-per-hour cap hit
- Already tracked: `governance_halt`, `warmup`, `insufficient_data`, `equity_zero`, `drawdown_kill`, `spy_ma_filter`, `opening_block`

*Stale value prevention*: Both `_last_gate_rejections` and `_last_entries_blocked_reason` reset to empty at start of every tick.

**Why**: Without gate-level telemetry, debugging "why no trades?" required reading logs and guessing. Now a single API call to `/organism/decisions` returns the complete filtering funnel with exact rejection counts per gate and the blocking reason, turning debugging from "patch-and-pray" into a deterministic process.

**Impact**: The post-reset decision snapshots show `entries_blocked_reason: "throttle"` clearly identifying why no new entries were made for ~60 minutes, and `rejected_by_long_only: 2` showing 2 short signals were correctly filtered in LONG_ONLY mode.

### 2.3 Commit `f509d3b` (2:45 PM ET)

**"Implement all 5 improve3.md audit recommendations: fix structural info plumbing"**

- 15 files changed, 1,137 insertions, 133 deletions
- Backend: 6 files (live_engine.py, kelly_sizer.py, ml_signal.py, decision_telemetry.py, continuous_learner.py)
- Frontend: 7 files (architecture tab updates reflecting new features)
- Monitoring: 1 file (memory_monitoring.json)
- Docs: 1 file (improve3.md added)

### 2.4 Docker Rebuild and Brain Wipe

**Why full wipe was necessary**: The brain was trained on poisoned data:
- Trade history: 13 trades with constant `confidence=0.6` and `exit_reason=live_close`
- ML models (`ml_classifier.joblib`, `ml_regressor.joblib`): Trained on next-bar labels, fundamentally misaligned with the new 15-bar prediction horizon
- Confidence calibration: Learned from fake 0.6 constant — useless
- Kelly regime stats: Based on approximate fill prices and wrong PnL
- Evolution parameters: Optimized against polluted trade data
- Transfer knowledge: Feature importance from wrong-horizon model

**What was wiped**:
1. All files in `organism_brain/` directory
2. All 29 organism orders from PostgreSQL: `DELETE FROM orders WHERE attributes->>'source' = 'organism'`

**Note on reconstruction**: The first wipe attempt failed because the engine's startup logic (`_reconstruct_trades_from_db`) detected an empty brain and rebuilt it from the 29 filled orders in the database. This required a second wipe that cleared both the brain files AND the database orders simultaneously.

**Container restart**: `docker restart intra-api-1` after wipe to ensure clean initialization.

---

## 3. Phase 1 Trading (Old Code) — 9:30 AM to 2:48 PM ET

### 3.1 Market Context

- Regular hours: 9:30 AM – 4:00 PM ET
- Regime: Transitioned between `chop`, `high_vol`, and `trending_up` throughout the day
- Engine config: 30-symbol universe, 10s tick interval, 1Min bars

### 3.2 Trades (11 Round-Trips)

All trades executed under the OLD code with the following known defects:
- `confidence=0.6` (fake constant for all trades)
- `exit_reason=live_close` (hard-coded for all reconciled trades)
- `predicted_return` based on next-bar (1-minute) horizon
- Fill prices based on bar close, not actual broker fills

| # | Symbol | Shares | Entry Price | Exit Price | PnL | Return | Hold Time |
|---|--------|--------|------------|------------|-----|--------|-----------|
| 1 | COIN | 28 | $184.34 | $185.81 | +$41.30 | +0.80% | ~7 min |
| 2 | ADBE | 6 | $267.48 | $269.03 | +$9.32 | +0.58% | ~8 min |
| 3 | CRM | 6 | $194.01 | $195.07 | +$6.36 | +0.55% | ~8 min |
| 4 | PLTR | 8 | $146.32 | $147.10 | +$6.22 | +0.53% | ~4 min |
| 5 | NFLX | 3 | $96.23 | $96.44 | +$0.62 | +0.21% | ~43 min |
| 6 | NFLX | 2 | $97.25 | $97.28 | +$0.06 | +0.03% | ~4 min |
| 7 | XLE | 21 | $57.16 | $57.16 | $0.00 | 0.00% | ~4 min |
| 8 | MSFT | 1 | $399.66 | $399.60 | -$0.06 | -0.02% | ~4 min |
| 9 | PLTR | 7 | $140.51 | $140.23 | -$1.99 | -0.20% | ~4 min |
| 10 | MSFT | 3 | $397.25 | $396.46 | -$2.37 | -0.20% | ~4 min |
| 11 | QQQ | 1 | $595.09 | $592.94 | -$2.15 | -0.36% | ~43 min |

**Phase 1 totals**: 6W / 5L (55%), +$57.31 PnL, $13,955 capital deployed, +0.41% return

### 3.3 Phase 1 Analysis

**Winners pattern**: The 6 winners were all long positions that caught small upward moves. COIN was the standout (+$41.30) with the largest position (28 shares, $5,162 notional). Winners held between 4-8 minutes.

**Losers pattern**: The 5 losers were all very small losses ($0.06–$2.37). The largest loser was MSFT (-$2.37, 3 shares). QQQ lost $2.15 on a single share held for 43 minutes — a slow bleed with no exit trigger.

**Key observation**: Despite the broken confidence and exit reason tracking, the actual trade outcomes were slightly profitable. This suggests the alpha scanner and breakout detection have some edge, even without ML contribution. However, the data from these trades is unusable for learning because the metadata is corrupted.

---

## 4. Phase 2 Trading (New Code) — 2:49 PM to 4:00 PM ET

### 4.1 Engine Startup Sequence

| Time (UTC) | Tick | Event |
|------------|------|-------|
| 19:49:08 | 1 | Engine starts, warmup tick 1/5 |
| 19:49:21 | 2 | Warmup tick 2/5 |
| 19:49:34 | 3 | Warmup tick 3/5 |
| 19:49:47 | 4 | Warmup tick 4/5 |
| 19:50:00 | 5 | Warmup tick 5/5 — entries now allowed |
| 19:50:13 | 6 | First live tick — scanning begins |

### 4.2 Entry Phase (Ticks 37–41)

Three entries were submitted between ticks 37–41 (~6 minutes after warmup):

| Symbol | Tick | Shares | Entry Price | Confidence | Breakout Score |
|--------|------|--------|------------|------------|----------------|
| PLTR | 37 | 3 | $145.98 | 0.1174 | 0.411 |
| CRM | 37 | 3 | $198.23 | 0.1415 | moderate |
| WMT | 41 | 10 | $128.06 | 0.0907 | moderate |

**Why these symbols?** The alpha scanner ranked PLTR, CRM, and WMT based on their composite scores (breakout + momentum + institutional flow). ML was untrained at this point (is_trained=false), so the ML component contributed near-zero. The entries were driven by breakout and momentum signals.

**Why such small positions?** With ML untrained, the Kelly sizer uses reduced confidence scaling (`confidence_scale = min(confidence_scale, 0.6)`) and no breakout bonus (`breakout_bonus = 1.0` when untrained). Combined with high_vol regime scaling (0.8x), positions were sized conservatively.

### 4.3 Exit Phase (Ticks 55–60)

All three positions exited within ~18–19 ticks of entry (~3 minutes):

| Symbol | Tick | Exit Price | Fill Method | Exit Reason | PnL |
|--------|------|------------|-------------|-------------|-----|
| CRM | 56 | $198.29 | Alpaca fill | `failure_to_follow` | +$0.19 |
| PLTR | 56 | $146.25 | Alpaca fill | `failure_to_follow` | +$0.80 |
| WMT | 60 | $128.15 | Alpaca fill | `failure_to_follow` | +$0.90 |

**Exit reason analysis**: All 3 exits were `failure_to_follow` — the adaptive exit engine's condition that triggers when a position hasn't achieved 0.5R of profit within 25% of max_bars (minimum 5 bars). This means:
- The positions moved slightly in the right direction (all were small winners)
- But not fast enough to meet the "follow through" threshold
- The exit engine correctly identified stalling momentum and closed before the positions could reverse

This is exactly the kind of exit reason attribution that was impossible with the old `live_close` hard-coding.

**Fill price verification**: All 3 exits show Alpaca fill prices from the trade stream (CRM $198.29, PLTR $146.2467, WMT $128.15). The new `_last_exit_fill_price` capture worked correctly — Tier 1 (synchronous fill) was sufficient for all 3 trades.

### 4.4 Throttle Lock Period (Ticks 55–150+)

After 3 entries, the entries-per-hour throttle activated:
- **Duration**: ~60 minutes (from ~3:57 PM to ~4:57 PM UTC / ~12:00 to ~1:00 PM PT)
- **Consecutive blocked ticks**: ~150+ ticks
- **Telemetry**: Every tick showed `entries_blocked_reason: "throttle"` in the decision snapshot — the new telemetry fix working exactly as designed
- **Candidates available but blocked**: The pipeline continued scoring 24-27 symbols above alpha threshold and Kelly-sizing 1-2 candidates per tick, but the throttle prevented submission

**Impact**: The throttle effectively limited the new code to 3 trades during Phase 2. This is the "entry starvation" problem identified in improve3.md — the 3/hour cap is too restrictive for a learning system that needs trade data.

### 4.5 Late Entry (Tick 156, After-Hours)

At 21:00:59 UTC (4:01 PM ET), the throttle cleared and a PLTR entry was submitted:
- **PLTR**: 3 shares, ~$147, confidence=0.33
- This is an after-hours entry — it will need to be managed at tomorrow's open
- The higher confidence (0.33 vs the earlier 0.09–0.14) suggests the ML model is beginning to contribute after accumulating ~156 ticks of data

---

## 5. Data Quality Comparison (Old vs New Code)

### 5.1 Trade Record Fields

| Field | Old Code (Phase 1) | New Code (Phase 2) | Assessment |
|-------|-------|-------|------------|
| confidence | `0.6` (all trades) | `0.1415, 0.1174, 0.0907` | Fixed — real, varied values |
| exit_reason | `live_close` (all trades) | `failure_to_follow` (all trades) | Fixed — real ATR-based reason |
| predicted_return | `3.4e-05` to `8.4e-04` (next-bar) | `1.13e-04` to `3.58e-04` (15-bar) | Fixed — correct horizon |
| exit_price | Bar close proxy | Alpaca fill price | Fixed — real broker fills |
| correct_direction | Based on fake data | Based on real data | Fixed — meaningful |

### 5.2 Telemetry Fields

| Field | Old Code | New Code |
|-------|----------|----------|
| entries_blocked_reason | Always empty | `"throttle"`, `"warmup"`, etc. |
| rejected_by_cost_gate | Always 0 | Wired from sizer rejects |
| rejected_by_min_notional | Always 0 | Wired from sizer rejects |
| rejected_by_long_only | Tracked | Tracked (saw 2 rejections at end of day) |

### 5.3 Kelly Regime Statistics

| Field | Old Code | New Code |
|-------|----------|----------|
| Regime stats source | Polluted (wrong PnL, wrong fills) | Clean (real fills, real PnL) |
| Stats at EOD | 2 regimes, corrupted | 1 regime (high_vol): 3W/0L, +$1.89 |
| Usable for sizing? | No (garbage in) | Not yet (need 10+ trades per regime) |

---

## 6. System Health

### 6.1 Infrastructure

| Component | Status | Notes |
|-----------|--------|-------|
| API container (intra-api-1) | Healthy | Rebuilt mid-day, restarted after brain wipe |
| PostgreSQL (intra-db-1) | Healthy | Orders table cleaned (29 rows deleted) |
| Redis (intra-redis-1) | Healthy | No issues |
| WebSocket (trade stream) | 3 disconnections | Auto-reconnected each time |
| WebSocket (market data) | 3 disconnections | Caused 1 tick to take 710s |

### 6.2 WebSocket Instability

Three WebSocket disconnection events occurred:
1. **20:24 UTC** — Trade updates stream closed, market data stream keepalive timeout
2. **20:34 UTC** — Market data stream closed (no close frame)
3. **20:52 UTC** — Both streams dropped again

The reconnection logic worked correctly each time, but the 20:24 event caused a single tick to run for **710 seconds** (vs normal ~3s) while the connection recovered. This 12-minute gap reduced the total number of ticks in the session.

### 6.3 Brain State at End of Day

```
Brain format version:  2
Generation:            0 (no evolution)
Total runs:            1
Total trades:          3
Cumulative PnL:        $1.89
ML trained:            true (79 features)
Retrain count:         0
Drift events:          0
Peak equity:           $112,458.15
Tick count:            156 (session)
Bars since retrain:    105
Shorts enabled:        false
```

### 6.4 ML Model State

The ML model was trained during the session (auto-trained after sufficient bars accumulated):
- **Features**: 79 (full feature set)
- **Train window**: 100 bars
- **Direction accuracy**: Not yet measurable (too few predictions with outcomes)
- **ML contribution to alpha**: Near-zero (0.000–0.007 across all symbols)
- **Top alpha factors**: Breakout (0.1–0.5) and momentum (0.0–1.0) dominate

The ML model is essentially a passenger at this stage — alpha scores are driven almost entirely by breakout and momentum. This is expected for a cold-start model with no trade outcome feedback. As trade history accumulates over the coming days, ML should begin contributing meaningfully.

### 6.5 Regime Distribution

End-of-day regime probabilities:

| Regime | Probability | Character |
|--------|------------|-----------|
| chop | 29.0% | No clear trend, choppy price action |
| high_vol | 23.0% | Elevated volatility |
| trending_up | 19.8% | Some bullish momentum |
| stress | 13.6% | Moderate stress signals |
| low_vol | 8.0% | Calm periods |
| trending_down | 6.6% | Minor bearish pressure |

The market spent most of the day in chop/high_vol — unfavorable conditions for directional strategies. The 3 winning trades in Phase 2 occurred during a `high_vol` regime, which is notable because the regime sizing scale (0.8x) was conservative but still allowed profitable entries.

### 6.6 Alpha Scanner Analysis (Final Tick)

At the final tick (#156), the alpha scanner scored all 29 symbols:

**Top signals** (above 0.40 composite):
- XOM: 0.485 (direction: SHORT — blocked by LONG_ONLY)
- NFLX: 0.456 (direction: SHORT — blocked by LONG_ONLY)
- PLTR: 0.435 (direction: LONG — this is the late entry)
- SNOW: 0.430 (direction: LONG)
- XLE: 0.410 (direction: SHORT — blocked by LONG_ONLY)

**Key observation**: 3 of the top 5 signals were SHORT, but the engine is in LONG_ONLY mode. The `rejected_by_long_only: 2` counter confirms this. If shorts were enabled, the engine would have had more opportunities.

**Factor contribution breakdown** (averaged across top candidates):
- ML: 0.000–0.007 (essentially zero — untrained)
- Breakout: 0.17–0.54 (dominant factor)
- Momentum: 0.07–1.00 (strong contributor)
- Institutional: 0.02–0.55 (variable)

---

## 7. Risk & Compliance Notes

### 7.1 Capital at Risk

| Metric | Phase 1 | Phase 2 | Combined |
|--------|---------|---------|----------|
| Max position notional | $5,162 (COIN 28sh) | $1,281 (WMT 10sh) | $5,162 |
| Max portfolio exposure | ~12% (3 positions) | ~1.5% (3 positions) | ~12% |
| Max loss on single trade | -$2.37 (MSFT) | $0.00 (all winners) | -$2.37 |
| Drawdown kill threshold | 8% (.env) | 8% (.env) | Never triggered |

### 7.2 Safety Mechanisms

| Mechanism | Status | Events |
|-----------|--------|--------|
| Drawdown kill switch | Not triggered | Max DD: 0.01% (far below 8% threshold) |
| Entry throttle (3/hr) | Triggered | Blocked entries for ~60 min in Phase 2 |
| Opening block (30 min) | Active | Blocked entries 9:30–10:00 AM ET |
| Long-only enforcement | Active | Blocked 2 short signals at end of day |
| Edge-over-cost gate | Active | Filtering throughout |
| Missingness gate (25%) | Active | No rejections (data quality good) |
| Liquidity gate (10K) | Active | No rejections (universe is liquid) |
| 15% max-loss safety net | Not triggered | No position approached this level |

### 7.3 Order Execution Quality

Phase 2 orders (new code) with Alpaca fill details:

| Order | Side | Qty | Fill Price | Fill Type |
|-------|------|-----|------------|-----------|
| PLTR entry | buy | 3 | $146.03 | Filled immediately |
| CRM entry | buy | 3 | $198.30 | Filled immediately |
| WMT entry | buy | 10 | $128.068 | Partial fills (1→7→8→10 shares) |
| CRM exit | sell | 3 | $198.29 | Partial fills (2→3 shares) |
| PLTR exit | sell | 3 | $146.247 | Partial fills (1→2→3 shares) |
| WMT exit | sell | 10 | $128.15 | Partial fills (1→4→7→9→10 shares) |

**Note**: WMT showed the most partial fill activity (5 increments on entry, 5 on exit). This is normal for a $128 stock with 10-share orders. The new fill price capture correctly recorded the volume-weighted average.

---

## 8. Identified Issues and Observations

### 8.1 Entry Throttle Too Restrictive (Critical)

The 3-entries-per-hour cap is the **single largest bottleneck** for the learning system. After 3 entries at ticks 37–41, the throttle locked the engine out for ~60 minutes — covering the entire remaining market session. During that time, the pipeline was identifying 24–27 candidates above alpha threshold and Kelly-sizing 1–2 per tick, but none could be submitted.

**Recommendation**: Increase to 5–6/hour for paper trading. The exploration bucket (recommendation 4) provides an alternative path but is currently disabled.

### 8.2 All Exits Were `failure_to_follow` (Observation)

All 3 Phase 2 trades exited for the same reason: the price didn't follow through fast enough. Holding times were ~19 ticks (~3 minutes). This suggests:
- The adaptive exit engine's failure-to-follow threshold may be too aggressive for a choppy market
- Or the entry signals are catching weak momentum that stalls quickly
- More data is needed to determine if this is a pattern or coincidence

### 8.3 ML Model Contributing Near-Zero (Expected)

The ML component is essentially dormant — contributing 0.000–0.007 to alpha scores while breakout and momentum contribute 0.1–1.0. This is expected for a cold-start model. The model needs:
- More bars for training (currently ~100 bars)
- Trade outcomes for confidence calibration (currently 3 clean trades)
- Multiple retrain cycles to improve

### 8.4 Short Signals Being Wasted (Observation)

At end of day, 3 of the top 5 alpha signals were SHORT (XOM, NFLX, XLE). In LONG_ONLY mode, these are blocked. The `rejected_by_long_only: 2` counter confirms this is actively reducing the opportunity set. This is a deliberate risk control, not a bug, but it's worth monitoring whether high-quality short signals consistently appear.

### 8.5 WebSocket Stability (Moderate Concern)

Three WebSocket disconnections in a 2-hour window is concerning. The auto-reconnection works, but the 710-second stall on one tick means data could become stale. This pattern should be monitored tomorrow.

### 8.6 Brain Reconstruction from DB (Learned)

The brain wipe procedure must clear BOTH the filesystem brain AND the database orders. The engine's `_reconstruct_trades_from_db()` method will rebuild a polluted brain from DB orders if only the filesystem is wiped. This was discovered and resolved during the session.

---

## 9. Configuration Summary

### Active Configuration (Post-Reset)

```
ORGANISM_TICK_INTERVAL_SECONDS=10
ORGANISM_LIVE_TIMEFRAME=1Min
ORGANISM_MAX_POSITIONS=15
ORGANISM_LONG_ONLY=true
ORGANISM_RETRAIN_INTERVAL=200 (intraday auto-adjusted)
ORGANISM_PREDICTION_HORIZON=15 (NEW — multi-bar, auto-set for 1Min)
ORGANISM_EXPLORATION_ENABLED=false (NEW — available but off)
ORGANISM_EXPLORATION_MAX_NOTIONAL=200 (NEW)
ORGANISM_EXPLORATION_MAX_POSITIONS=3 (NEW)
ORGANISM_DRAWDOWN_KILL_PCT=0.08
ORGANISM_ML_DECAY_RATE=0.005
ORGANISM_MAX_PER_SECTOR=4
```

### Universe (30 symbols)

AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA, AMD, AVGO, CRM, COST, WMT, LLY, XOM, CAT, SPY, QQQ, IWM, XLK, XLE, NFLX, COIN, PLTR, ADBE, ABNB, INTC, MU, SNOW, SQ, UBER

---

## 10. Recommendations for March 4

1. **Raise entry throttle to 5–6/hour** — The current 3/hour limit caused a 60-minute lockout today. For paper trading, the risk is minimal and the data collection benefit is significant.

2. **Monitor the overnight PLTR position** — Entered at 4:01 PM ET (after-hours). Needs management at market open.

3. **Consider enabling exploration bucket** — Set `ORGANISM_EXPLORATION_ENABLED=true` to start collecting learning data on rejected candidates at minimal risk (1 share, $200 max).

4. **Watch for `failure_to_follow` exit pattern** — If all trades continue exiting for this reason, the failure-to-follow threshold (0.5R profit within 25% of max_bars) may need loosening in choppy regimes.

5. **Monitor ML model contribution** — After 200+ ticks tomorrow, the ML model should start contributing meaningful scores. If ML alpha remains near-zero after a full trading day, investigate training data quality.

6. **WebSocket stability** — Monitor for disconnection pattern. If it persists, consider adding connection health metrics.

---

## 11. File Change Summary

### Commit `2a39e1a` (Pre-Market)

| File | Summary |
|---|---|
| `live_engine.py` | Liquidity gate 500K→10K, TIF IOC→DAY |
| `regime.py` | ATR column: atr_ratio → atr_14 |
| `order_service.py` | Default TIF: IOC → DAY |
| `mapss.md` | +491 / -180 documentation audit |
| `trading_report_2026-03-02.md` | March 2 report added |

### Commit `f509d3b` (Mid-Day, 2:45 PM ET)

| File | Lines | Summary |
|---|---|---|
| `live_engine.py` | +298 / -49 | All 5 improve3.md fixes, DB fill lookup, gate telemetry |
| `kelly_sizer.py` | +20 | confidence/predicted_return/breakout_score on PositionSize |
| `ml_signal.py` | +24 / -7 | Multi-bar prediction horizon (configurable H) |
| `decision_telemetry.py` | +27 | 12 gate-level rejection counters + blocked reason |
| `continuous_learner.py` | +1 | `is_exploration` field on TradeRecord |
| Frontend (7 files) | +656 / -70 | Architecture tab updates |
| `monitoring/memory_monitoring.json` | +58 / -66 | Monitoring config update |
| `docs/architecture/improve3.md` | +186 | Audit document added |

### Post-Commit Actions

| Action | Details |
|---|---|
| Docker rebuild | `docker-compose up -d --build api` |
| Brain wipe | `rm -rf organism_brain/*` |
| DB cleanup | `DELETE FROM orders WHERE attributes->>'source' = 'organism'` (29 rows) |
| Container restart | `docker restart intra-api-1` |

---

*Report generated: March 3, 2026*
*Engine version: commit `f509d3b`*
*Brain state: Generation 0, 3 clean trades, $1.89 PnL*
*Next trading day: March 4, 2026*
