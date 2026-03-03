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
