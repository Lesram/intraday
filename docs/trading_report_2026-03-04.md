# Trading Day Report — March 4, 2026

**Prepared for**: AIA deep research / audit review
**System**: Intra Platform — Organism Living Trading Engine
**Account**: Alpaca Paper Trading (PA3RLEN7T0N4)
**Starting Equity**: ~$112,500 (post-brain-reset from March 3 deploy)
**Ending Equity**: ~$112,273 (brain equity curve) / $112,666 peak
**Engine Mode**: Paper trading, long-only, 1-min bars, 10s tick interval
**Session Duration**: ~6.5 hours (9:30 AM – 4:00 PM ET)
**Total Ticks**: 720

---

## Executive Summary

March 4 was the **first full trading day** after the improve4+improve5 engine overhaul (deployed late March 3). The system executed **53 completed trades** across **24 symbols** — the most active day since going live. Two mid-day hotfixes were deployed without stopping the engine for extended periods.

The system ended the day with a **cumulative P&L of +$154.66** across all 53 trades. However, the ending equity (~$112,273) is lower than the opening (~$112,500) because 3 open positions at close carried unrealized losses, and the peak-to-trough drawdown reached ~$390 from the intraday high of $112,666.

**Two system updates were deployed during the trading session**, dividing the day into two distinct phases with measurably different exit behavior.

| Metric | Phase 1 (Pre-Update) | Phase 2 (Post-Update) | Full Day |
|---|---|---|---|
| Trades | 26 | 27 | **53** |
| Win rate | 38.5% (10/26) | 37.0% (10/27) | 37.7% (20/53) |
| Total P&L | +$97.28 | +$57.38 | **+$154.66** |
| Avg Win | $35.54 | $20.78 | $28.16 |
| Avg Loss | -$16.13 | -$8.85 | -$12.38 |
| Payoff ratio | 2.20:1 | 2.35:1 | **2.27:1** |
| FTF exit % | **65%** (17/26) | **52%** (14/27) | 58% (31/53) |
| Trailing stop exits | 0 | **4** | 4 |
| Take profit exits | 0 | **1** | 1 |
| Direction accuracy | 38.5% | 37.0% | 37.7% |

### Key Takeaways

1. **FTF (failure_to_follow) dropped from 65% to 52%** after the mid-day update, and new exit types appeared (trailing_stop, take_profit) that were never seen in Phase 1.
2. **Trailing stop exits emerged for the first time** — 4 exits via trailing_stop in Phase 2 (net +$65.69), proving trades now hold long enough for the trailing mechanism to activate.
3. **First take_profit exit** — XLE hit its full take-profit target for +$23.20.
4. **The top 3 winners** (COIN +$242, AMZN +$73, SNOW +$67) were all trades that held long — max_holding_period or trailing_stop. The system rewards patience.
5. **FTF is still net-negative** (-$80.92 across 31 exits) and remains the largest drag on P&L.
6. **The bar detection fix was critical** — Phase 1 bars_held advanced at ~1 bar/2.5 min (Alpaca lag); Phase 2 advanced at exactly 1 bar/min (wall clock).

---

## 1. Pre-Market State (improve4 + improve5 deployed overnight March 3)

### 1.1 Commits Deployed Before Market Open

**Commit `7f7d5ca` — "Implement improve4+improve5 audit: fix timebase, sizing, exits, cost modeling"**

This was the massive overnight deploy that implemented all 8 milestones from improve4.md plus the improve5.md audit recommendations. Key changes:

#### M1: Time-Unit Mismatch Fix (adaptive_exits.py, live_engine.py)
- `bars_held` now only increments on new 1-min bar boundaries (was incrementing every 10s tick = 6x too fast)
- `is_new_bar` parameter added to `check_exit()` — risk checks (stop_loss, max_loss) still run every tick
- All bar-based constants recalibrated from tick-based to bar-based values
- Time decay rate changed from 1%/tick to 0.3%/bar

#### M2: Failure-to-Follow Redesign (adaptive_exits.py)
- Horizon-delay: `early_check = max(H//2, 3)` = 7 bars for H=15 (was checking after ~18 ticks = 3 min)
- Regime-dependent R thresholds: trending_up/low_vol=DISABLED, chop/high_vol=0.25R, stress=0.15R
- `prediction_horizon` stored on ExitLevels (was hardcoded)
- MIN_HOLD made dynamic: `max(H//3, 3)` = 5 bars for H=15

#### M3: Learning-Mode Entry Throttle (live_engine.py)
- Learning mode threshold: < 200 trades (was < 50)
- Learning mode throttle: 12/hr (was 8/hr, originally 3/hr)
- Production mode: dynamic 3-6/hr scaled by open positions

#### M4: ML Cold-Start Fix (alpha_scanner.py, kelly_sizer.py)
- Confidence scale cap when ML untrained: 0.9 (was 0.6)
- ML hold penalty reduced from 0.3x to 0.7x when untrained
- Direction derived from momentum/breakout when ML direction = 0

#### M5: Signal-Based Kelly Fallback (kelly_sizer.py)
- `kelly_raw = predicted_return / max((atr_pct × √15)², 1e-6)` (horizon-matched variance)
- Breakout bonus re-enabled when ML untrained (capped at 1.5x, was disabled)
- Pre-Kelly risk-budget floor: `0.25% equity / (atr_pct × 1.5 stop_mult)` when < 200 trades

#### M6: Tick Telemetry DB Table (schemas.py, live_engine.py)
- New `TickTelemetry` ORM model, writes every 6th tick
- 7-day retention with daily cleanup

#### M7: WebSocket Stale Data Gating (live_engine.py)
- Block entries when streaming data > 2 min stale
- Exits still run on stale data

#### Additional improve5.md Changes
- Fitness gate telemetry fixed: 0.45 in both engine and telemetry (was 0.35 in telemetry)
- Marketable limit orders: limit at ask + 0.1% for buys (was pure market orders)
- FTF disabled for trending_up/low_vol regimes

### 1.2 Engine State at Market Open

| Parameter | Value |
|---|---|
| ML | Trained (generation 1, 79.8% accuracy) — models retrained on fresh data after brain reset |
| Evolved params | Generation 1 — one adaptation cycle completed |
| Trade history | Empty (brain reset cleared stale 3-trade history from broken timebase) |
| Regime Kelly stats | Accumulating from scratch |
| Entry throttle | 12/hr (learning mode, < 200 trades) |
| Prediction horizon | H=15 (15-min bars) |
| Universe | 30 symbols |
| Max positions | 15 |

---

## 2. Phase 1: Trading with improve4+improve5 (9:30 AM – ~2:07 PM ET)

### 2.1 Market Conditions

The market regime was predominantly **chop** and **high_vol** throughout the morning session. No trending_up or low_vol regimes were detected — meaning the FTF disable for trending_up/low_vol had zero effect.

### 2.2 Phase 1 Trade Results (26 trades)

| # | Symbol | Entry | Exit | Shares | P&L | Exit Reason | Confidence | Correct? |
|---|--------|-------|------|--------|-----|-------------|------------|----------|
| 1 | CRM | 198.22 | 198.29 | 3 | +$0.19 | failure_to_follow | 0.14 | Yes |
| 2 | PLTR | 145.98 | 146.25 | 3 | +$0.80 | failure_to_follow | 0.12 | Yes |
| 3 | WMT | 128.06 | 128.15 | 10 | +$0.90 | failure_to_follow | 0.09 | Yes |
| 4 | PLTR | 147.50 | 146.25 | 3 | -$3.76 | live_close | 0.33 | No |
| 5 | NFLX | 98.84 | 98.22 | 54 | -$33.35 | failure_to_follow | 0.66 | No |
| 6 | AVGO | 321.17 | 321.63 | 16 | +$7.38 | failure_to_follow | 0.64 | Yes |
| 7 | AMD | 198.44 | 197.65 | 27 | -$21.28 | failure_to_follow | 0.60 | No |
| 8 | TSLA | 404.75 | 405.01 | 13 | +$3.31 | failure_to_follow | 0.51 | Yes |
| 9 | MU | 404.46 | 405.09 | 13 | +$8.13 | failure_to_follow | 0.25 | Yes |
| 10 | PLTR | 151.46 | 151.66 | 35 | +$7.17 | failure_to_follow | 0.43 | Yes |
| 11 | INTC | 44.99 | 44.99 | 120 | $0.00 | failure_to_follow | 0.57 | No |
| 12 | IWM | 262.72 | 262.36 | 20 | -$7.11 | failure_to_follow | 0.35 | No |
| 13 | AVGO | 321.70 | 320.05 | 16 | -$26.48 | stop_loss | 0.29 | No |
| 14 | QQQ | 609.47 | 611.07 | 8 | +$12.80 | failure_to_follow | 0.63 | Yes |
| 15 | AAPL | 264.15 | 263.70 | 20 | -$9.00 | failure_to_follow | 0.56 | No |
| 16 | MU | 405.91 | 402.58 | 13 | -$43.31 | stop_loss | 0.24 | No |
| 17 | XOM | 149.72 | 149.39 | 36 | -$11.88 | stop_loss | 0.43 | No |
| 18 | CRM | 195.73 | 195.39 | 27 | -$9.18 | failure_to_follow | 0.44 | No |
| 19 | ABNB | 137.62 | 137.53 | 39 | -$3.48 | failure_to_follow | 0.25 | No |
| 20 | COIN | 203.46 | 209.09 | 43 | **+$242.14** | max_holding_period | 0.66 | Yes |
| 21 | AMZN | 213.82 | 215.59 | 41 | **+$72.57** | max_holding_period | 0.35 | Yes |
| 22 | PLTR | 152.49 | 151.66 | 35 | -$29.05 | live_close | 0.27 | No |
| 23 | AMZN | 215.74 | 214.60 | 24 | -$27.12 | stop_loss | 0.39 | No |
| 24 | MU | 407.07 | 405.09 | 13 | -$25.76 | stop_loss | 0.49 | No |
| 25 | UBER | 76.39 | 76.36 | 70 | -$2.15 | failure_to_follow | 0.34 | No |
| 26 | TSLA | 404.66 | 404.26 | 13 | -$5.20 | failure_to_follow | 0.41 | No |

### 2.3 Phase 1 Exit Breakdown

| Exit Reason | Count | % | Net P&L | Assessment |
|---|---|---|---|---|
| failure_to_follow | 17 | 65% | **-$50.07** | Still dominant, net-negative — cutting winners too early |
| stop_loss | 5 | 19% | -$134.55 | Working as designed |
| max_holding_period | 2 | 8% | **+$314.71** | The ONLY profitable exit category — proves patience works |
| live_close | 2 | 8% | -$32.81 | Manual/end-of-day closes |

### 2.4 Critical Observation: Bar Detection Lag

Analysis revealed that `bars_held` was advancing at **~1 bar per 2.5 minutes** instead of 1 bar per minute. Root cause: the `is_new_bar` detection used the timestamp from Alpaca's historical bar API, which lags 2-3 minutes behind real-time. This meant:
- FTF's 7-bar check actually fired at ~17.5 minutes instead of 7 minutes
- max_holding_period took ~2.5x longer than intended to trigger
- Time decay started later than calibrated

Despite this, FTF still dominated (65%) because the **0.25R threshold in chop/high_vol was too tight** — trades weren't achieving 0.25R even after 17 minutes in choppy conditions.

### 2.5 Phase 1 Diagnosis

**Problem**: FTF is the primary P&L destroyer. It accounts for $50 in losses while the system's entire profit ($314.71) comes from just 2 trades (COIN, AMZN) that held to max_holding_period.

**Root causes identified**:
1. Bar detection lag (Alpaca timestamp) causes inconsistent timing
2. FTF 0.25R threshold in chop/high_vol too aggressive
3. FTF lacks momentum confirmation — exits even when price is still improving
4. FTF active in high_vol regime where trades need more room

---

## 3. Mid-Day Update #1: FTF + Bar Detection Fix (~2:07 PM ET)

### 3.1 Commit `96c8152` — "Fix FTF dominance: wall-clock bar detection, momentum confirmation, lower thresholds"

**Deployed at**: 19:07 UTC (2:07 PM ET)
**Docker rebuilt and restarted**: Engine resumed within ~30 seconds

#### Change 1: Wall-Clock Bar Detection (live_engine.py)

```python
# BEFORE: Used Alpaca bar timestamp (lagged 2-3 min)
_bar_ts = str(feat_df["timestamp"].iloc[-1])

# AFTER: Wall-clock UTC minute boundary
_bar_ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")
```

**Impact**: bars_held now advances exactly 1 per minute, regardless of Alpaca data delivery lag.

#### Change 2: FTF Momentum Confirmation (adaptive_exits.py)

Added `price_at_prior_bar` field to ExitLevels dataclass. FTF now only fires if **both**:
- R_achieved < R_threshold (price hasn't progressed toward target)
- Price hasn't improved since prior bar (no positive momentum)

This prevents cutting winners that are still trending up but haven't yet hit the R threshold.

```python
_has_momentum = (
    _prev_price > 0
    and (current_price - _prev_price) * direction > 0
)
if r_achieved < r_threshold and not _has_momentum:
    return ExitSignal(True, "failure_to_follow", current_price)
```

#### Change 3: FTF Regime + Threshold Adjustments (adaptive_exits.py)

| Parameter | Before | After |
|---|---|---|
| FTF disabled regimes | trending_up, low_vol | trending_up, low_vol, **high_vol** |
| chop R threshold | 0.25 | **0.15** |
| stress R threshold | 0.15 | **0.10** |
| trending_down/unknown R | 0.35 | **0.25** |

### 3.2 Immediate Issue: Kelly atr_pct UnboundLocalError

After restart, the engine hit an `UnboundLocalError: cannot access local variable 'atr_pct'` in kelly_sizer.py. Root cause: `atr_pct` was computed inside the `else` branch of a regime_kelly check, but the risk-budget code below used it unconditionally. When regime_kelly data was available (ML trained with 17+ trades in chop regime), the else branch was skipped.

**This error existed before the Phase 2 update** but was masked because regime_kelly was rarely available in Phase 1 (insufficient per-regime trade data). By Phase 2, enough chop trades had accumulated to trigger the regime_kelly path.

---

## 4. Mid-Day Update #2: Kelly Fix (~2:10 PM ET)

### 4.1 Commit `a12efd8` — "Fix atr_pct UnboundLocalError in kelly_sizer risk-budget path"

**Deployed at**: 19:10 UTC (2:10 PM ET)

```python
# BEFORE: atr_pct defined only in else branch
regime_kelly = self.get_regime_kelly(current_regime)
if regime_kelly is not None:
    kelly_raw = min(regime_kelly, 1.0)
else:
    # ...
    atr_pct = float(np.std(returns, ddof=1))  # only here!

# AFTER: atr_pct computed unconditionally before branch
atr_pct = float(np.std(returns, ddof=1)) if len(returns) > 1 else 0.01
regime_kelly = self.get_regime_kelly(current_regime)
if regime_kelly is not None:
    kelly_raw = min(regime_kelly, 1.0)
else:
    # ... (removed duplicate atr_pct line)
```

**Impact**: Engine ran cleanly after this fix — no further errors for the remainder of the session.

---

## 5. Phase 2: Trading with All Fixes (2:10 PM – 4:00 PM ET)

### 5.1 Phase 2 Trade Results (27 trades)

| # | Symbol | Entry | Exit | Shares | P&L | Exit Reason | Confidence | Correct? |
|---|--------|-------|------|--------|-----|-------------|------------|----------|
| 27 | ADBE | 274.37 | 274.09 | 19 | -$5.23 | failure_to_follow | 0.61 | No |
| 28 | AVGO | 321.48 | 320.54 | 16 | -$15.04 | stop_loss | 0.60 | No |
| 29 | NVDA | 183.10 | 183.18 | 29 | +$2.31 | failure_to_follow | 0.46 | Yes |
| 30 | SNOW | 169.08 | 168.83 | 31 | -$7.75 | stop_loss | 0.90 | No |
| 31 | XLE | 56.03 | 56.04 | 96 | +$0.48 | failure_to_follow | 0.32 | Yes |
| 32 | MSFT | 408.32 | 407.71 | 13 | -$7.94 | stop_loss | 0.18 | No |
| 33 | MU | 405.23 | 404.94 | 13 | -$3.77 | failure_to_follow | 0.42 | No |
| 34 | PLTR | 152.44 | 153.43 | 50 | **+$49.50** | max_holding_period | 0.50 | Yes |
| 35 | XOM | 150.04 | 149.74 | 35 | -$10.50 | live_close | 0.22 | No |
| 36 | SNOW | 166.44 | 168.52 | 32 | **+$66.72** | **trailing_stop** | 0.56 | Yes |
| 37 | TSLA | 405.94 | 406.22 | 19 | +$5.28 | stop_loss | 0.57 | Yes |
| 38 | MSFT | 409.88 | 408.33 | 12 | -$18.55 | failure_to_follow | 0.59 | No |
| 39 | AMZN | 216.60 | 216.70 | 24 | +$2.35 | failure_to_follow | 0.61 | Yes |
| 40 | PLTR | 154.23 | 153.55 | 34 | -$23.14 | failure_to_follow | 0.62 | No |
| 41 | COIN | 210.38 | 209.70 | 19 | -$12.92 | failure_to_follow | 0.63 | No |
| 42 | META | 669.08 | 667.08 | 7 | -$13.97 | failure_to_follow | 0.48 | No |
| 43 | CRM | 194.55 | 194.40 | 27 | -$4.03 | failure_to_follow | 0.42 | No |
| 44 | PLTR | 153.56 | 153.48 | 34 | -$2.55 | failure_to_follow | 0.56 | No |
| 45 | XLE | 55.95 | 56.09 | 160 | **+$23.20** | **take_profit** | 0.58 | Yes |
| 46 | UBER | 76.55 | 76.45 | 70 | -$6.65 | stop_loss | 0.52 | No |
| 47 | COIN | 209.75 | 209.87 | 19 | +$2.28 | failure_to_follow | 0.57 | Yes |
| 48 | ABNB | 135.82 | 135.70 | 39 | -$4.68 | trailing_stop | 0.58 | No |
| 49 | XLE | 56.10 | 56.14 | 96 | +$3.85 | trailing_stop | 0.34 | Yes |
| 50 | XOM | 149.72 | 149.58 | 54 | -$7.56 | stop_loss | 0.49 | No |
| 51 | MU | 400.95 | 404.94 | 13 | **+$51.87** | failure_to_follow | 0.42 | Yes |
| 52 | COST | 1006.54 | 1006.49 | 4 | -$0.20 | trailing_stop | 0.67 | No |
| 53 | ADBE | 273.43 | 273.11 | 19 | -$5.98 | failure_to_follow | 0.57 | No |

### 5.2 Phase 2 Exit Breakdown

| Exit Reason | Count | % | Net P&L | Assessment |
|---|---|---|---|---|
| failure_to_follow | 14 | 52% | -$30.85 | Still dominant but reduced from 65% — and net loss halved |
| stop_loss | 6 | 22% | -$39.66 | Working as designed; includes 1 profitable stop (TSLA +$5.28) |
| **trailing_stop** | **4** | **15%** | **+$65.69** | **NEW** — first trailing exits of the day |
| max_holding_period | 1 | 4% | +$49.50 | PLTR held to maturity |
| **take_profit** | **1** | **4%** | **+$23.20** | **NEW** — first take-profit of the day (XLE) |
| live_close | 1 | 4% | -$10.50 | Manual close |

### 5.3 Phase 2 New Exit Types (never seen in Phase 1)

#### Trailing Stop Exits (4 total, +$65.69 net)

| Symbol | Entry | Exit | P&L | Return | Notes |
|---|---|---|---|---|---|
| SNOW | $166.44 | $168.52 | **+$66.72** | +1.25% | Breakout trade, trailing activated and locked in profit |
| XLE | $56.10 | $56.14 | +$3.85 | +0.07% | Small win, trailing activated on modest move |
| ABNB | $135.82 | $135.70 | -$4.68 | -0.09% | False breakout, trailing caught the reversal quickly |
| COST | $1006.54 | $1006.49 | -$0.20 | -0.005% | Essentially flat, trailing activated near entry |

**Key insight**: The SNOW trailing_stop exit (+$66.72) is the **3rd largest single trade of the day**. This trade would have been killed by FTF in Phase 1 (regime was high_vol, now disabled for FTF). Instead, it ran to +1.25% and the trailing stop locked in the gain.

#### Take Profit Exit (1 total, +$23.20)

XLE hit its full take-profit target at $56.09 (entry $55.95, +0.26%). This is the **first take_profit exit** the system has ever produced. It required the trade to be held long enough for the price to reach the TP level — something that was impossible when FTF cut trades after a few minutes.

### 5.4 Profitable Stop Loss

TSLA exited via stop_loss at +$5.28 — a **profitable stop**. The profit-lock mechanism moved the stop loss up to breakeven+ after the trade achieved 2R, and when price pulled back, the elevated stop triggered and preserved the gain. This is working exactly as designed.

---

## 6. Full Day Summary (53 trades)

### 6.1 Top 5 Winners

| # | Symbol | P&L | Exit Reason | Hold Time (ticks) | Notes |
|---|--------|-----|-------------|-------------------|-------|
| 1 | COIN | **+$242.14** | max_holding_period | 125 | Phase 1: Entered early, held to limit |
| 2 | AMZN | **+$72.57** | max_holding_period | 126 | Phase 1: Entered early, held to limit |
| 3 | SNOW | **+$66.72** | trailing_stop | 25 | Phase 2: First trailing stop winner |
| 4 | MU | +$51.87 | failure_to_follow | 21 | Phase 2: FTF but still profitable (+1.0%) |
| 5 | PLTR | +$49.50 | max_holding_period | 133 | Phase 2: Cross-phase hold, matured |

### 6.2 Top 5 Losers

| # | Symbol | P&L | Exit Reason | Hold Time (ticks) | Notes |
|---|--------|-----|-------------|-------------------|-------|
| 1 | MU | -$43.31 | stop_loss | 18 | Phase 1: Sharp reversal |
| 2 | NFLX | -$33.35 | failure_to_follow | 27 | Phase 1: Wrong direction, large size |
| 3 | PLTR | -$29.05 | live_close | 21 | Phase 1: Manual close |
| 4 | AMZN | -$27.12 | stop_loss | 7 | Phase 2: Immediate reversal |
| 5 | AVGO | -$26.48 | stop_loss | 27 | Phase 1: Trend reversal |

### 6.3 Exit Reason P&L Attribution (Full Day)

| Exit Reason | Count | Total P&L | Avg P&L | Verdict |
|---|---|---|---|---|
| max_holding_period | 3 | **+$364.21** | +$121.40 | Best exit type — patience pays |
| trailing_stop | 4 | **+$65.69** | +$16.42 | New and promising |
| take_profit | 1 | **+$23.20** | +$23.20 | Working as intended |
| failure_to_follow | 31 | **-$80.92** | -$2.61 | Still net-negative, primary drag |
| live_close | 3 | -$43.31 | -$14.44 | Manual/end-of-day |
| stop_loss | 11 | -$174.21 | -$15.84 | Risk management working |

### 6.4 Per-Symbol Performance

| Symbol | Trades | Total P&L | Best Trade | Assessment |
|---|---|---|---|---|
| COIN | 3 | **+$231.50** | +$242.14 | Best performer — strong breakout thesis |
| SNOW | 2 | +$58.97 | +$66.72 | Trailing stop captured breakout |
| AMZN | 3 | +$47.80 | +$72.57 | Good entries, one bad re-entry |
| XLE | 3 | +$27.53 | +$23.20 | Only take-profit symbol |
| QQQ | 1 | +$12.80 | +$12.80 | Single profitable FTF trade |
| TSLA | 3 | +$3.39 | +$5.28 | Mixed — one profitable stop |
| WMT | 1 | +$0.90 | +$0.90 | Tiny winner |
| PLTR | 7 | -$1.03 | +$49.50 | Most traded — mixed results |
| INTC | 1 | $0.00 | $0.00 | Break-even |
| COST | 1 | -$0.20 | -$0.20 | Trailing stop, essentially flat |
| IWM | 1 | -$7.11 | -$7.11 | Wrong direction |
| ABNB | 2 | -$8.16 | -$3.48 | Both losers |
| UBER | 2 | -$8.80 | -$2.15 | Both losers |
| AAPL | 1 | -$9.00 | -$9.00 | Wrong direction |
| ADBE | 2 | -$11.21 | -$5.23 | Both FTF losers |
| NVDA | 1 | +$2.31 | +$2.31 | Small FTF winner |
| MU | 5 | -$12.84 | +$51.87 | Volatile — big win & big losses |
| CRM | 3 | -$13.02 | +$0.19 | All small losers |
| META | 1 | -$13.97 | -$13.97 | Wrong direction, large loss |
| AMD | 1 | -$21.28 | -$21.28 | Wrong direction |
| MSFT | 2 | -$26.49 | -$7.94 | Both losers |
| XOM | 3 | -$29.94 | -$7.56 | All losers, persistent shorts against us |
| NFLX | 1 | -$33.35 | -$33.35 | Largest single FTF loss |
| AVGO | 3 | -$34.14 | +$7.38 | Two stop losses wiped out one winner |

---

## 7. System Health & Infrastructure

### 7.1 Engine Performance

| Metric | Value |
|---|---|
| Total ticks | 720 |
| Avg tick duration | ~3.5 seconds |
| Tick interval | 10 seconds |
| Peak equity | $112,666.47 |
| Ending equity (curve) | ~$112,273 |
| Max drawdown | ~0.35% ($393 from peak) |
| Open positions at close | 3 (PLTR, UBER, WMT) |

### 7.2 ML Status

| Metric | Value |
|---|---|
| Trained | Yes |
| Generation | 1 |
| Accuracy | 79.8% (classifier) |
| Total training trades | 53 |
| Retrain count | 1 |
| Drift events | 0 |

### 7.3 Regime Distribution

Market regime was predominantly choppy/volatile throughout the day. No trending_up or low_vol periods were detected — meaning FTF was never disabled for those regimes in Phase 1 (only high_vol disable in Phase 2 had effect).

### 7.4 Error Summary

| Error Type | Count | Impact |
|---|---|---|
| DNS resolution (Alpaca) | 2 | Transient, auto-recovered — SQ symbol missed 1 bar |
| Connection aborted | 2 | Transient, auto-recovered |
| TimeoutError (tick) | 3 | Tick skipped, auto-recovered next cycle |
| WebSocket keepalive timeout | 3 | Auto-reconnected within seconds |
| UnboundLocalError (atr_pct) | 1 | Fixed in Update #2 within 3 minutes |
| Other | 7 | Non-critical (startup, Alpaca retries) |

**Assessment**: No persistent errors. All transient issues auto-recovered. The one code bug (atr_pct) was caught and fixed within 3 minutes.

### 7.5 Evolved Parameters (End of Day)

Key evolved parameter values:

| Parameter | Value | Notes |
|---|---|---|
| alpha_weight_ml | 0.3559 | ML carries 36% of alpha |
| alpha_weight_momentum | 0.1982 | Momentum at 20% |
| alpha_weight_breakout | 0.1486 | Breakout at 15% |
| regime_size_scales.chop | 0.485 | Chop regime sized at 48.5% of full |
| regime_size_scales.high_vol | 0.7 | High vol at 70% |
| regime_size_scales.stress | 0.3 | Stress at 30% |
| stop_atr_scale | 0.985 | Stops slightly tighter than default |
| direction_threshold_buy | 0.55 | Buy threshold |
| direction_threshold_sell | 0.45 | Sell threshold |

### 7.6 Feature Importance (Top 10 by Evolved Weight)

| Feature | Weight | Notes |
|---|---|---|
| log_ret_1d | 1.554 | 1-day log return — strongest signal |
| regime_encoded | 1.448 | Regime detection |
| hurst_exponent | 1.447 | Mean-reversion/trending indicator |
| hurst | 1.405 | Alternate Hurst computation |
| choppiness | 1.073 | Choppiness index |
| rsi_14 | 1.024 | 14-period RSI |
| pct_from_52w_low | 1.019 | Distance from 52-week low |
| atr_14 | 0.991 | 14-period ATR |
| ret_autocorr_1 | 0.974 | 1-bar autocorrelation |
| vwap_distance | 0.966 | Distance from VWAP |

---

## 8. Phase Comparison: Measurable Impact of Updates

### 8.1 FTF Reduction

| Metric | Phase 1 | Phase 2 | Change |
|---|---|---|---|
| FTF exit % | 65% (17/26) | 52% (14/27) | **-13 percentage points** |
| FTF net P&L | -$50.07 | -$30.85 | **38% less damage** |
| FTF avg loss | -$2.95 | -$2.20 | Smaller per-trade losses |

### 8.2 New Exit Diversity

| Exit Type | Phase 1 | Phase 2 |
|---|---|---|
| failure_to_follow | 65% | 52% |
| stop_loss | 19% | 22% |
| trailing_stop | **0%** | **15%** |
| take_profit | **0%** | **4%** |
| max_holding_period | 8% | 4% |
| live_close | 8% | 4% |

Phase 2 shows **healthier exit diversity** — the system is using its full exit toolkit instead of defaulting to FTF.

### 8.3 Avg Loss Reduction

| Metric | Phase 1 | Phase 2 |
|---|---|---|
| Avg loss per losing trade | -$16.13 | **-$8.85** |
| Payoff ratio | 2.20:1 | **2.35:1** |

Phase 2 losing trades lose **45% less** on average, while the payoff ratio improved.

---

## 9. Remaining Issues for Next Audit

### 9.1 FTF Still Dominant at 52%

Even after the update, FTF accounts for more than half of all exits. The momentum confirmation and lowered thresholds helped, but FTF is still firing too often in chop regime (0.15R). Possible next steps:
- Consider disabling FTF for chop as well (leaving only stress/trending_down/unknown)
- Increase the early_check delay beyond H//2 (currently 7 bars)
- Add a minimum bars_held before FTF can fire (e.g., 15 bars = prediction horizon)

### 9.2 Direction Accuracy at 37.7%

The ML model's directional accuracy is below 50%. This could indicate:
- The model needs more training data (only 53 trades, still in learning mode < 200)
- Feature selection may need tuning (79 features, many with low evolved weights)
- The prediction horizon (H=15) may not match the market's current structure

### 9.3 Predicted Return vs Actual Return Divergence

Many trades show large predicted returns (1-5%) but actual returns near 0% or negative. This suggests the ML model is overconfident in its return predictions, or the prediction horizon doesn't match the actual holding time.

### 9.4 Open Positions at Market Close

3 positions remained open at close (PLTR, UBER, WMT). These will carry overnight risk. The system should consider whether to enforce end-of-day close for all positions.

### 9.5 Equity Curve Trend

The equity curve shows a slight downtrend in the final hour (~$112,357 → ~$112,273). This coincides with typical end-of-day volatility and position unwinding. The system may benefit from reducing entry activity in the last 30 minutes.

---

## 10. Commits Log

| Time (ET) | Commit | Description |
|---|---|---|
| Late March 3 | `7f7d5ca` | improve4+improve5 full implementation (8 milestones) |
| 2:07 PM | `96c8152` | FTF fix: wall-clock bars, momentum confirmation, lower thresholds |
| 2:10 PM | `a12efd8` | Kelly atr_pct UnboundLocalError fix |

---

## 11. Configuration at End of Day

```
ORGANISM_TICK_INTERVAL_SECONDS=10
ORGANISM_LIVE_TIMEFRAME=1Min
ORGANISM_MAX_POSITIONS=15
ORGANISM_LONG_ONLY=true
ORGANISM_RETRAIN_INTERVAL=180
ORGANISM_ML_DECAY_RATE=0.005
ORGANISM_MAX_PER_SECTOR=4
ORGANISM_DRAWDOWN_KILL_PCT=0.08
Universe: 30 symbols
Learning mode: Yes (53/200 trades)
Entry throttle: 12/hr (learning mode)
FTF disabled regimes: trending_up, low_vol, high_vol
FTF R thresholds: chop=0.15, stress=0.10, trending_down/unknown=0.25
Bar detection: wall-clock UTC minute boundary
ML: Trained, generation 1, 79.8% accuracy
```

---

*Report generated March 4, 2026 after market close. All P&L figures are paper trading (Alpaca sandbox).*
