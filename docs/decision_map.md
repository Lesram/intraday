# ORGANISM TRADING ENGINE — COMPLETE DECISION MAP

> Every process, every filter, every threshold, every decision path from raw market data to trade execution.

---

## TABLE OF CONTENTS

1. [Tick Lifecycle Overview](#1-tick-lifecycle-overview)
2. [Phase 0: Preamble & Housekeeping](#2-phase-0-preamble--housekeeping)
3. [Phase 1: Governance Gate](#3-phase-1-governance-gate)
4. [Phase 2: Data Acquisition & Feature Engineering](#4-phase-2-data-acquisition--feature-engineering)
5. [Phase 3: Regime Detection](#5-phase-3-regime-detection)
6. [Phase 4: Portfolio State & Drawdown](#6-phase-4-portfolio-state--drawdown)
7. [Phase 5: Exit Decisions (ALWAYS runs)](#7-phase-5-exit-decisions)
8. [Phase 6: Pyramid Checks (entries-gated)](#8-phase-6-pyramid-checks)
9. [Phase 7: New Entry Scanning (entries-gated)](#9-phase-7-new-entry-scanning)
10. [Phase 8: Kelly Position Sizing (entries-gated)](#10-phase-8-kelly-position-sizing)
11. [Phase 9: Order Submission (entries-gated)](#11-phase-9-order-submission)
12. [Phase 10: Fill Reconciliation (ALWAYS runs)](#12-phase-10-fill-reconciliation)
13. [Phase 11: Retrain & Evolve (entries-gated)](#13-phase-11-retrain--evolve)
14. [Phase 12: Brain Persistence (ALWAYS runs)](#14-phase-12-brain-persistence)
15. [ML Signal Generation Deep Dive](#15-ml-signal-generation-deep-dive)
16. [Feature Engineering Deep Dive (79 Features)](#16-feature-engineering-deep-dive)
17. [Alpha Scanner Deep Dive](#17-alpha-scanner-deep-dive)
18. [Breakout Scanner Deep Dive](#18-breakout-scanner-deep-dive)
19. [Kelly Sizer Deep Dive](#19-kelly-sizer-deep-dive)
20. [Adaptive Exit Engine Deep Dive](#20-adaptive-exit-engine-deep-dive)
21. [Regime Detector Deep Dive](#21-regime-detector-deep-dive)
22. [Self-Evolution Deep Dive](#22-self-evolution-deep-dive)
23. [Universe & Sector Management](#23-universe--sector-management)
24. [Background Training & Transfer Learning](#24-background-training--transfer-learning)
25. [Configuration Reference](#25-configuration-reference)
26. [Known Regime-Label Mismatches](#26-known-regime-label-mismatches)

---

## 1. TICK LIFECYCLE OVERVIEW

```
┌─────────────────────────────────────────────────────────────────────┐
│                        TICK BEGINS (~10s)                           │
│                                                                     │
│  ┌──── ALWAYS ─────────────────────────────────────────────────┐   │
│  │  [0] Housekeeping: expire cooldowns, stream health          │   │
│  │  [1] Governance halt check → entries_blocked?               │   │
│  │  [2] Fetch data + compute 79 features per symbol            │   │
│  │  [3] Detect market regime (3-tier priority)                 │   │
│  │  [4] Get positions + equity, drawdown kill check            │   │
│  │  [5] EXIT CHECKS for all open positions                     │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌──── IF entries NOT blocked ─────────────────────────────────┐   │
│  │  [6] Pyramid checks on existing positions                   │   │
│  │  [7] Scan new entries: Alpha + Breakout + ML                │   │
│  │  [8] Kelly position sizing                                  │   │
│  │  [9] Submit entry orders                                    │   │
│  │  [11] Retrain ML + evolve parameters                        │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌──── ALWAYS ─────────────────────────────────────────────────┐   │
│  │  [10] Reconcile fills (detect closed + orphaned positions)  │   │
│  │  [12] Brain save (every 50 ticks, with walk-forward gate)   │   │
│  │  [POST] Equity curve, Prometheus, telemetry, invariants     │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│                         TICK ENDS                                   │
└─────────────────────────────────────────────────────────────────────┘
```

**Critical insight**: Exits ALWAYS run, even when governance has halted trading. Only new entries are blocked.

---

## 2. PHASE 0: PREAMBLE & HOUSEKEEPING

```
START TICK
  │
  ├── Acquire async tick lock (serializes execution)
  ├── Increment _tick_count
  │
  ├── Expire cooldowns:
  │   ├── _exit_cooldown:   symbols older than 3 ticks removed
  │   ├── _pending_entry:   symbols older than 15 ticks removed
  │   └── _pending_exit:    symbols older than 3 ticks removed
  │
  └── Stream health check (every 30 ticks ≈ 5 min):
      └── IF streaming provider active:
          └── check_and_recover_stale_stream()
```

### Cooldown Constants

| Cooldown | Ticks | Real Time (~10s ticks) | Purpose |
|---|---|---|---|
| `_EXIT_COOLDOWN_TICKS` | 3 | ~30s | Prevents re-entering a recently exited symbol |
| `_PENDING_ENTRY_TICKS` | 15 | ~2.5 min | Prevents duplicate entry submissions |
| `_PENDING_EXIT_TICKS` | 3 | ~30s | Prevents duplicate exit submissions |

---

## 3. PHASE 1: GOVERNANCE GATE

```
GOVERNANCE CHECK
  │
  ├── Is trading halted?
  │   ├── Manual halt (ORGANISM_HALT_TRADING=1 or /halt endpoint)
  │   ├── Drawdown kill active (cooldown not expired)
  │   │   └── Adaptive cooldown: base_1hr × (1 + min(2, excess/0.05))
  │   │       ├── At 8% limit exactly → 1 hour cooldown
  │   │       ├── 3% over limit (11%) → 1.6 hours
  │   │       ├── 5% over (13%) → 2 hours
  │   │       └── 10%+ over (18%) → 3 hours (max)
  │   └── Auto-resumes when cooldown expires
  │
  ├── IF halted → entries_blocked = True
  │   └── Exits STILL run. Only entries blocked.
  │
  ├── Is adaptation frozen? (ORGANISM_FREEZE_ADAPTATION=1)
  │   └── Blocks parameter evolution, NOT trading
  │
  ├── Change budget exhausted? (default 100/day, resets midnight UTC)
  │   └── Blocks evolution parameter changes, NOT trading
  │
  └── Strategy disabled? (ORGANISM_DISABLED_STRATEGIES=...)
      └── Per-strategy disable (not currently used in tick loop)
```

### Governance Environment Variables

| Variable | Default | Production | Effect |
|---|---|---|---|
| `ORGANISM_DRAWDOWN_KILL_PCT` | 0.05 | **0.08** | Drawdown % that triggers kill switch |
| `ORGANISM_DRAWDOWN_COOLDOWN_S` | 3600 | 3600 | Base cooldown after kill (1 hour) |
| `ORGANISM_MAX_CHANGES_PER_DAY` | 100 | 100 | Daily evolution budget |
| `ORGANISM_HALT_TRADING` | 0 | 0 | Manual trading halt |
| `ORGANISM_FREEZE_ADAPTATION` | 0 | 0 | Freeze all adaptation |

---

## 4. PHASE 2: DATA ACQUISITION & FEATURE ENGINEERING

```
FETCH DATA
  │
  ├── Fetch SPY first (always needed for cross-asset features)
  │
  ├── For each symbol in universe (parallelized, semaphore=10):
  │   ├── Priority 1: Streaming provider (fast-path)
  │   │   └── Falls through to REST if unavailable or < MIN_BARS
  │   ├── Priority 2: REST API (get_historical_bars_df or get_historical_data)
  │   │
  │   ├── Minimum bars check:
  │   │   └── IF len(bars) < MIN_BARS (50 for intraday) → SKIP symbol
  │   │
  │   └── Compute features (79 total):
  │       ├── compute_ml_features(raw_df, spy_df)  → 75 base features
  │       ├── add_multi_timeframe_features()         → additional MTF features
  │       └── NaN/Inf → 0.0 (global safety net)
  │
  ├── Also fetch features for open positions NOT in universe
  │   └── (symbols rotated out but still held — exits must still work)
  │
  └── IF fewer than 3 symbols have features:
      └── entries_blocked = True (but exits still run via broker price fallback)
```

### Data Pipeline Config

| Parameter | Default | Intraday Override |
|---|---|---|
| `LIVE_LOOKBACK` | 500 bars | — |
| `LIVE_TIMEFRAME` | `"1Day"` | `"1Min"` in production |
| `MIN_BARS` | 200 | **50** (auto-adjusted for intraday) |
| `RETRAIN_INTERVAL` | 60 | **200** (auto-adjusted for intraday) |

---

## 5. PHASE 3: REGIME DETECTION

```
DETECT REGIME (only if features sufficient)
  │
  ├── Priority 1: Cross-Asset Regime
  │   ├── Needs sector ETF features (XLK, XLE, XLF, XLV, XLI, XLU, XLP, XLY, XLB, XLRE)
  │   ├── Each ETF must have >= 10 bars of features
  │   ├── Computes per-sector regimes, then breadth conditioning:
  │   │   ├── breadth_up > 0.5 → boost trending_up × (1 + 0.3 × breadth_up)
  │   │   ├── breadth_down > 0.5 → boost trending_down × (1 + 0.3 × breadth_down)
  │   │   └── stress_pct > 0.4 → boost stress × (1 + 0.5 × stress_pct)
  │   └── Re-normalize probabilities
  │
  ├── Priority 2: SPY-Based
  │   └── detect(spy_features) — needs SPY with >= 10 bars
  │
  └── Priority 3: Market Aggregate
      └── Average regime probabilities across all symbols
```

### Regime Classification Logic

From feature data, 4 signals are extracted:

| Signal | Source | Decision |
|---|---|---|
| Trend slope | SMA slope over 10 bars | > 0.02 → trending_up(+2), < -0.02 → trending_down(+2), else → chop(+1.5) |
| Price vs SMA | (close - SMA) / SMA | > 0.02 → trending_up(+1), < -0.02 → trending_down(+1), else → chop(+0.5) |
| Volatility | ATR ratio + returns vol | ATR > 0.04 → high_vol(+2), ATR < 0.015 → low_vol(+1.5), ret_vol > 0.03 → high_vol(+1) |
| Stress | Volume anomaly + ATR | vol_anomaly > 0.5 AND ATR > 0.04 → stress(+2) |

Scores → softmax → EMA smoothing (α=0.3) → argmax = primary regime.

### Regime Labels Produced

`trending_up`, `trending_down`, `chop`, `high_vol`, `low_vol`, `stress`, `unknown`

---

## 6. PHASE 4: PORTFOLIO STATE & DRAWDOWN

```
GET POSITIONS + EQUITY
  │
  ├── Fetch all positions from broker
  ├── Fetch equity (portfolio value, fallback to buying power, fallback to 0)
  │
  ├── Equity-Zero Resilience:
  │   ├── equity > 0 → reset counter, update peak
  │   └── equity == 0 →
  │       ├── Increment _consecutive_equity_zero
  │       ├── IF >= 3 consecutive zeros → entries_blocked = True
  │       └── ELSE → warning, skip drawdown check this tick
  │
  ├── Drawdown Check (if peak > 0 AND equity > 0):
  │   ├── drawdown = (peak - equity) / peak
  │   ├── governance.trigger_drawdown_kill(drawdown)
  │   └── IF drawdown >= 8% → kill switch fires → entries_blocked
  │
  └── Propagate existing halt:
      └── IF governance already halted → entries_blocked = True
```

---

## 7. PHASE 5: EXIT DECISIONS

**This is the most critical phase. It ALWAYS runs, even when entries are blocked.**

```
FOR EACH OPEN POSITION:
  │
  ├── FILTER: LONG_ONLY and side != "long" → SKIP (artifact short)
  ├── FILTER: sym in _pending_exit → SKIP (exit already submitted)
  │
  ├── PATH A: No features available for this symbol
  │   ├── Get broker_price and avg_entry from position data
  │   ├── Compute pnl_pct = (broker_price - entry) / entry × direction
  │   ├── IF pnl_pct <= -15% → SAFETY NET EXIT
  │   │   └── Submit full exit, reason: "safety_net_no_features"
  │   └── ELSE → no action (can't evaluate without features)
  │
  ├── PATH B: Features available but NO exit_levels for this symbol
  │   ├── Get avg_entry from position data
  │   ├── Compute pnl_pct
  │   ├── IF pnl_pct <= -15% → SAFETY NET EXIT
  │   │   └── Submit full exit, reason: "max_loss_safety_net"
  │   └── ELSE → no action (position adopted mid-session, exits will be created)
  │
  └── PATH C: Normal exit check (features + exit_levels both available)
      │
      ├── Run adaptive exit engine: check_exit(exit_levels, price, regime)
      │   │
      │   ├── Priority 0: 15% MAX LOSS safety net
      │   │   └── pnl_pct <= -0.15 → EXIT, reason: "max_loss_limit"
      │   │
      │   ├── Priority 1: HARD STOP LOSS
      │   │   ├── Long: price <= stop_loss → EXIT
      │   │   └── Short: price >= stop_loss → EXIT
      │   │
      │   ├── Priority 2: PARTIAL TAKE PROFIT (3R, fires once)
      │   │   ├── Long: price >= partial_tp → SELL 30%
      │   │   ├── Short: price <= partial_tp → COVER 30%
      │   │   └── Side effect: move stop to BREAKEVEN
      │   │
      │   ├── Priority 3: FULL TAKE PROFIT
      │   │   └── price crosses TP level → EXIT
      │   │
      │   ├── Priority 4: ATR TRAILING STOP
      │   │   ├── Activates when price moves 3.0× ATR from entry
      │   │   ├── Trail distance: ATR × regime_trail_atr_mult
      │   │   ├── Ratchet: only tightens, never loosens
      │   │   ├── Long trail floor: never below entry price
      │   │   └── price crosses trail → EXIT
      │   │
      │   ├── Priority 5: TIME-BASED EXIT (regime-adaptive)
      │   │   ├── max_bars varies by regime (0=disabled for trending)
      │   │   └── Only exits positions IN PROFIT (losers stay)
      │   │
      │   ├── Priority 6: TIME DECAY (non-exiting, tightens stop)
      │   │   ├── After decay_start bars: stop tightens 1%/bar
      │   │   └── Maximum tightening: 40%
      │   │
      │   └── Priority 7: STRESS REGIME TIGHTENING (one-time)
      │       ├── Fires if regime changes to stress/crisis mid-trade
      │       └── Tightens stop by 40% immediately
      │
      ├── ML Reversal Check (if exit engine says NO exit):
      │   ├── Condition: ML trained AND signal flips direction AND confidence > 0.3
      │   └── IF reversal detected → PARTIAL EXIT (50%)
      │       └── reason: "ml_reversal"
      │
      └── IF exit signal fired:
          ├── Compute shares to sell (full or partial)
          ├── Submit exit order
          └── Set cooldowns (_exit_cooldown, _pending_exit)
```

### Exit Regime Parameters

| Regime | Stop ATR | TP R-Multiple | Trail ATR | Max Bars | Decay Start |
|---|---|---|---|---|---|
| `trending_up` | 2.0 | 6.0 | 3.5 | ∞ | none |
| `trending` | 1.8 | 5.0 | 3.0 | ∞ | none |
| `normal` | 1.5 | 4.0 | 2.5 | 40 | bar 30 |
| `trending_down` | 1.3 | 3.0 | 2.0 | 30 | bar 20 |
| `chop` | 1.2 | 2.5 | 1.5 | 25 | bar 15 |
| `high_vol` | 1.0 | 3.0 | 2.0 | 30 | bar 20 |
| `stress` | 0.9 | 2.0 | 1.5 | 20 | bar 10 |
| `crisis` | 0.8 | 1.5 | 1.0 | 15 | bar 8 |

---

## 8. PHASE 6: PYRAMID CHECKS

**Only runs if entries NOT blocked.**

```
FOR EACH OPEN POSITION WITH PYRAMID TRACKER:
  │
  ├── SKIP if no features or no pyramid position
  │
  ├── Compute R-multiple: (favorable_move) / ATR_at_entry
  │
  ├── ANTI-PYRAMID (loss cutting, checked first):
  │   ├── R <= -1.0 → CLOSE FULL position (reason: "cut_full")
  │   └── R <= -0.7 AND only 1 layer → CUT 50% (reason: "cut_partial")
  │
  ├── AT MAX LAYERS (3):
  │   └── R > 3.0 → Tighten trail to peak - 2×ATR
  │
  ├── LAYER 1 ADD (at +1.5R):
  │   ├── Must have exactly 1 layer
  │   ├── Add 30% of target shares
  │   └── Move stop to BREAKEVEN
  │
  ├── LAYER 2 ADD (at +3.0R):
  │   ├── Must have exactly 2 layers
  │   ├── Add 10% of target shares
  │   └── Trail stop to price - 1.5×ATR
  │
  └── PROFIT TIGHTENING (fallthrough):
      └── R > 2.0 AND >= 2 layers → trail to peak - 2.5×ATR
```

### Pyramid Layer Allocation

| Layer | % of Target | R Threshold | Stop Action |
|---|---|---|---|
| 0 (initial) | 60% | at entry | Initial ATR stop |
| 1 (first add) | 30% | +1.5R | Move to breakeven |
| 2 (second add) | 10% | +3.0R | Trail at price - 1.5×ATR |

---

## 9. PHASE 7: NEW ENTRY SCANNING

**Only runs if entries NOT blocked.**

```
ENTRY SCANNING PIPELINE
  │
  ├── [7a] BREAKOUT SCAN
  │   ├── Filter: symbols with >= 20 bars of features
  │   ├── 6 detectors scored and weighted (see §18)
  │   └── Returns top-8 BreakoutSignals with composite >= 0.20
  │
  ├── [7b] ML PREDICTIONS
  │   ├── Batch predict on all symbols with features
  │   └── Returns MLSignal per symbol: direction, confidence, predicted_return
  │
  ├── [7c] ALPHA SCAN
  │   ├── Combines ML + 6 other factors (see §17)
  │   └── Returns top-5 AlphaCandidates with composite >= 0.15
  │
  ├── [7d] FILTER CANDIDATES (7 gates):
  │   │
  │   │  For each AlphaCandidate:
  │   ├── Gate 1: Already have position? → REJECT
  │   ├── Gate 2: In exit cooldown? → REJECT (wash trade prevention)
  │   ├── Gate 3: Pending entry order? → REJECT (duplicate prevention)
  │   ├── Gate 4: Already in entry_metadata? → REJECT
  │   ├── Gate 5: LONG_ONLY and direction < 0? → REJECT
  │   ├── Gate 6: Sector gate (max 4 per sector)? → REJECT
  │   └── Gate 7: Symbol fitness < 0.35? → REJECT (chronic loser gate)
  │
  │   IF passes all 7 gates:
  │   ├── Compute blended confidence:
  │   │   confidence = ML_confidence × (1 + breakout_score) × (1 + tension × 0.5)
  │   │   capped at 1.0
  │   └── Add to candidate list
  │
  ├── [7e] PURE BREAKOUT ADDITIONS (not in alpha candidates):
  │   ├── Same 7 gates PLUS:
  │   │   ├── composite_score >= 0.55
  │   │   ├── fitness >= 0.35
  │   │   └── ML direction not negative (don't fight ML)
  │   ├── Forced direction = +1.0 (always long)
  │   └── predicted_return floor = max(ml_return, 0.01)
  │
  └── [7f] SORT + TRUNCATE
      ├── Sort by breakout_score × confidence (descending)
      └── Truncate to: MAX_POSITIONS - current_positions
```

### Entry Filter Funnel (Typical Numbers)

```
30 symbols in universe
  → ~25 with sufficient features
    → ~5 pass alpha threshold (0.15)
      → ~3-4 pass all 7 gates
        → ~2-3 after Kelly sizing
          → ~1-2 orders submitted
```

---

## 10. PHASE 8: KELLY POSITION SIZING

**Only runs if entries NOT blocked and candidates exist.**

```
KELLY SIZING PIPELINE
  │
  ├── PORTFOLIO-LEVEL GATES:
  │   ├── equity <= 0 → SKIP ALL
  │   └── drawdown >= 25% → SKIP ALL (full risk-off)
  │
  ├── Sort candidates by conviction: abs(predicted_return) × confidence
  │
  ├── FOR EACH CANDIDATE:
  │   │
  │   ├── PER-CANDIDATE GUARDS:
  │   │   ├── direction == 0 → SKIP
  │   │   ├── predicted_return < 1e-6 (after floor) → SKIP
  │   │   ├── Features < 30 rows → SKIP
  │   │   └── < 20 usable returns → SKIP
  │   │
  │   ├── STEP 1: Raw Kelly
  │   │   ├── Preferred: Regime-stratified Kelly (if >= 10 trades in regime)
  │   │   │   └── Kelly = win_rate - (1 - win_rate) / payoff_ratio
  │   │   └── Fallback: Global Kelly = mean_return / variance_return
  │   │
  │   ├── STEP 2: Half-Kelly + Floors
  │   │   ├── kelly_half = kelly_raw × 0.5
  │   │   ├── Breakout floor: if kelly < 0.005 AND breakout >= 0.55
  │   │   │   └── kelly_half = max(kelly, 0.01 × breakout_score)
  │   │   └── ML floor: if trained AND kelly < 0.005 AND confidence >= 0.5
  │   │       └── kelly_half = max(kelly, 0.08 × confidence)
  │   │
  │   ├── STEP 3: Drawdown Scaling
  │   │   └── Linear: 1.0 at 0% drawdown → 0.1 at 25% drawdown
  │   │
  │   ├── STEP 4: Volatility Targeting
  │   │   └── vol_scale = 0.15 / annualized_vol (capped at 2.0)
  │   │
  │   ├── STEP 5: Regime Scaling
  │   │   ├── trending_up: 1.20    stress: 0.30
  │   │   ├── trending: 1.00       crisis: 0.10
  │   │   ├── normal: 0.85         chop: 0.50
  │   │   └── trending_down: 0.60  high_vol: 0.50→0.70
  │   │
  │   ├── STEP 6: Confidence Scaling
  │   │   ├── scale = 0.3 + confidence × 1.2 → range [0.3, 1.5]
  │   │   └── IF ML untrained: capped at 0.6
  │   │
  │   ├── STEP 7: Breakout Bonus
  │   │   ├── < 0.50: ×1.0    0.70-0.85: ×1.5-2.0
  │   │   ├── 0.50-0.70: ×1.0-1.5   >= 0.85: ×2.0
  │   │   └── IF ML untrained: forced ×1.0
  │   │
  │   ├── COMBINE:
  │   │   target_weight = kelly_half × dd_scale × vol_scale
  │   │                   × regime_scale × conf_scale × brk_bonus
  │   │
  │   ├── CAPS + FILTERS:
  │   │   ├── Per-position cap: 10% of equity
  │   │   ├── Portfolio cap: running total cannot exceed 95%
  │   │   ├── Minimum weight: 0.1%
  │   │   ├── Minimum notional: $2,000
  │   │   └── Minimum shares: 1
  │   │
  │   └── CONVERT TO SHARES:
  │       └── shares = int(equity × target_weight / current_price)
  │
  └── INTRADAY SEASONALITY FILTER:
      ├── First 15 min (9:30-9:45 ET): ALL sizes × 0.60 (40% reduction)
      └── Last 15 min (3:45-4:00 ET): ALL sizes × 0.60 (40% reduction)
```

---

## 11. PHASE 9: ORDER SUBMISSION

```
SUBMIT ENTRY ORDERS
  │
  ├── Re-fetch positions from broker (catch partial fills)
  │
  ├── FOR EACH SIZED POSITION:
  │   ├── Already have position at broker? → SKIP
  │   │
  │   ├── Pyramid initial sizing: shares × 0.60 (layer 0)
  │   │   └── Fallback: full shares if pyramid < 1
  │   │
  │   ├── Submit order:
  │   │   ├── Type: MARKET
  │   │   ├── TIF: IOC (Immediate-Or-Cancel)
  │   │   ├── Idempotency key: organism_{sym}_{date}_{session}_{tick}
  │   │   └── Attributes: source=organism, reason, confidence, tick
  │   │
  │   ├── POST-ORDER SETUP (if features available):
  │   │   ├── Create ExitLevels (stop, TP, trailing, partial TP)
  │   │   ├── Create PyramidPosition (layer 0, target = shares/0.6)
  │   │   └── Create _entry_metadata record
  │   │
  │   └── Set _pending_entry[sym] cooldown
  │
  └── EXIT ORDER FLOW:
      ├── Type: MARKET
      ├── TIF: DAY
      ├── LONG_ONLY safety: verify broker position before selling
      │   ├── No position → BLOCKED
      │   ├── Not long → BLOCKED
      │   ├── Clamp shares to actual broker qty
      │   └── Broker check fails → BLOCKED
      └── Idempotency key: organism_exit_{sym}_{date}_{session}_{tick}
```

---

## 12. PHASE 10: FILL RECONCILIATION

**ALWAYS runs, even when entries blocked.**

```
RECONCILE FILLS
  │
  ├── DETECT CLOSED POSITIONS:
  │   ├── tracked_symbols = symbols in _entry_metadata
  │   ├── broker_symbols = symbols at broker
  │   ├── candidates = tracked - broker (gone from broker)
  │   │
  │   ├── Grace period: skip if held < 3 ticks (may still be settling)
  │   │
  │   └── FOR EACH confirmed closed:
  │       ├── Pop _entry_metadata[sym]
  │       ├── Get exit price (features fallback to entry price)
  │       ├── Get shares (pyramid layers fallback to filled_shares)
  │       ├── Compute PnL = (exit - entry) × shares × direction
  │       ├── Create TradeRecord
  │       ├── Record to continuous_learner
  │       ├── Record to kelly_sizer (regime-stratified)
  │       ├── Record to signal_gen calibration
  │       └── Clean up _exit_levels, _pyramid_positions
  │
  └── DETECT ORPHANED POSITIONS (at broker but no metadata):
      ├── SKIP if in _exit_levels (actively managed)
      ├── SKIP if qty <= 0 or avg_entry <= 0
      ├── SKIP if LONG_ONLY and not long
      │
      └── ADOPT:
          ├── Create _entry_metadata stub
          ├── Create exit levels (if features available)
          ├── Create pyramid position
          └── Log adoption
```

---

## 13. PHASE 11: RETRAIN & EVOLVE

```
RETRAIN + EVOLVE (every RETRAIN_INTERVAL ticks, or 30 ticks if untrained)
  │
  ├── Background Training Path (primary):
  │   ├── Submit to ProcessPoolExecutor (separate CPU)
  │   ├── Stuck detection: if running > 30 ticks → force-reset, fall back to sync
  │   ├── On completion:
  │   │   ├── Accepted → atomically swap model weights + evolved params
  │   │   └── Rejected → fall back to synchronous retrain
  │   └── Training includes: ML fit + evolution step (all 10 sub-steps)
  │
  ├── Synchronous Fallback:
  │   ├── learner.retrain(features) → (accepted, metrics)
  │   ├── Update ML calibration
  │   ├── Evolution (on last 200 trades):
  │   │   └── 10 evolution sub-steps (see §22)
  │   └── Universe rotation
  │
  └── Validation Gate (continuous_learner):
      ├── Composite score = hit_rate×0.4 + accuracy×0.3 + (dir_acc-0.5)×0.6
      ├── No old model: accept if score > 0.25
      └── Old model exists: accept if improvement >= 5% OR
          (score >= 0.40 AND hit_rate >= 0.48)
```

---

## 14. PHASE 12: BRAIN PERSISTENCE

```
BRAIN SAVE (every 50 ticks ≈ 8 min)
  │
  ├── Walk-forward gate:
  │   ├── Checks last 100 trades (needs >= 10)
  │   ├── Regression threshold: 0.95
  │   └── IF gate rejects → DO NOT SAVE (prevents persisting regression)
  │
  ├── Full save:
  │   ├── ML models (classifier + regressor + ensemble)
  │   ├── Learning state + trade history + equity curve
  │   ├── Evolved params + governance state + regime detector
  │   ├── Exit levels, entry metadata, Kelly regime stats
  │   ├── Universe selector state
  │   └── ML calibration data
  │
  └── Transfer learning:
      └── Record run snapshot for cross-run knowledge transfer
```

---

## 15. ML SIGNAL GENERATION DEEP DIVE

### Dual-Model Architecture

```
Features (79)
  │
  ├── XGBClassifier → P(up) ∈ [0, 1]
  │   └── Time-decay weighted: newest sample ≈ 3.5× oldest (decay_rate=0.005)
  │
  ├── XGBRegressor → predicted_return ∈ [-0.5, 0.5]
  │   └── Same time-decay weighting
  │
  ├── Optional Ensemble (40% blend):
  │   ├── Random Forest (30% weight within ensemble)
  │   ├── LightGBM (25% weight, if installed)
  │   └── XGBoost (45% weight)
  │
  └── Final blend:
      ├── p_up = 0.6 × primary + 0.4 × ensemble
      └── pred_return = 0.6 × primary + 0.4 × ensemble
```

### Direction Decision

| P(up) | Direction | Meaning |
|---|---|---|
| > 0.52 | +1.0 (BUY) | Model is bullish |
| < 0.48 | -1.0 (SELL) | Model is bearish |
| 0.48 — 0.52 | 0.0 (HOLD) | Dead zone, no signal |

Note: Thresholds are evolved by the evolution engine. Range [0.50, 0.70] for buy.

### Confidence Calibration

```
raw_confidence = abs(p_up - 0.5) × 2     # [0, 1]
bin_idx = int(raw_confidence × 5)          # 5 bins: [0-0.2, 0.2-0.4, ...]
multiplier = actual_accuracy / bin_midpoint # capped at 2.0
calibrated = raw_confidence × multiplier   # capped at 1.0
```

Requires 10+ predictions per bin before adjusting.

### Training Data Requirements

- Minimum 50 total samples across all symbols
- Per-symbol: >= 60 bars required
- Feature selection: features with evolved weight < 0.20 dropped (floor: 15 features minimum)
- Temporal split: 80% train, 20% validation (per-symbol to avoid cross-contamination)

---

## 16. FEATURE ENGINEERING DEEP DIVE

### 79 Features Organized by Category

**Price Action (15):** ret_1d, ret_2d, ret_3d, ret_5d, ret_10d, ret_20d, log_ret_1d, momentum_accel, close_to_high, close_to_low, range_pct, gap_pct, body_ratio, upper_shadow, lower_shadow

**Trend (8):** sma_5, sma_10, sma_20, sma_50 (all as ratio to price), macd, macd_signal, macd_hist (all normalized), adx_14

**Mean Reversion (8):** rsi_14, rsi_5, bb_position, bb_width, z_score_20, z_score_50, stoch_k, stoch_d

**Volatility (10):** atr_14, atr_ratio, realized_vol_5, realized_vol_20, vol_ratio_5_20, parkinson_vol, garman_klass_vol, vol_regime, bb_squeeze, vol_expansion

**Volume (8):** vol_sma_ratio, obv_slope, vol_momentum_5, vol_momentum_10, mfi_14, vwap_distance, volume_breakout, pv_divergence

**Cross-Sectional (5, requires SPY):** rel_strength_spy, beta_20d, corr_to_market, idio_vol, sector_momentum

**Microstructure (5):** spread_proxy, price_impact, tick_direction, close_location, true_range_pct

**Temporal (5):** day_of_week, month_sin, month_cos, pct_from_52w_high, pct_from_52w_low

**Regime (4):** trend_strength, choppiness, hurst, regime_encoded

**Momentum Persistence (4):** ret_autocorr_1, ret_autocorr_5, ret_autocorr_10, hurst_exponent

**Composite Indicators (7):** comp_squeeze_momentum, comp_vol_price_div, comp_trend_alignment, comp_institutional_acc, comp_mean_rev_extreme, comp_breakout_readiness, comp_momentum_quality

### Global NaN Safety

All features: `inf → NaN → 0.0` (at the end of compute_ml_features)

---

## 17. ALPHA SCANNER DEEP DIVE

### 7-Factor Weighted Score

```
COMPOSITE = 0.25 × ml_score
          + 0.20 × breakout_score
          + 0.15 × institutional_score
          + 0.15 × momentum_score (cross-sectional rank)
          + 0.10 × momentum_quality
          + 0.10 × volume_score
          + 0.05 × regime_alignment
```

### Factor Details

| Factor | Weight | Computation | Score Range |
|---|---|---|---|
| ML Score | 0.25 | `confidence × abs(predicted_return) × 20`, cap 1.0 | [0, 1] |
| Breakout | 0.20 | `breakout_readiness × 0.6 + squeeze_momentum × 0.4` | [0, 1] |
| Institutional | 0.15 | `comp_institutional_acc` composite | [0, 1] |
| Momentum | 0.15 | Cross-sectional percentile rank of ret_20d | [0, 1] |
| Mom Quality | 0.10 | `comp_momentum_quality` composite | [0, 1] |
| Volume | 0.10 | `0.5 × vol_surge + 0.5 × vol_price_div` | [0, 1] |
| Regime | 0.05 | Regime-direction alignment table | [0.2, 1.0] |

### Modifiers

- **ML Hold penalty**: direction == 0 → composite × 0.30 (70% penalty)
- **Symbol fitness**: composite × (0.5 + fitness) → range [0.6×, 1.45×]
- **NaN guard**: each factor individually checked; NaN → default (0.0 or 0.5)

### Selection Gate

- Minimum composite: **0.15** (HFT-tuned, was 0.25)
- Minimum bars: 50
- Top-N: 5 candidates

---

## 18. BREAKOUT SCANNER DEEP DIVE

### 6-Detector Weighted Score

```
COMPOSITE = 0.25 × squeeze
          + 0.25 × volume_surge
          + 0.15 × range_contraction
          + 0.15 × relative_strength
          + 0.15 × pivot_breakout
          + 0.05 × institutional_flow
```

### Detector Details

| Detector | Weight | Key Threshold | Signal |
|---|---|---|---|
| Squeeze | 0.25 | BB inside KC, width < 35th pctile, expanding | [0, 1] + fired bool |
| Volume Surge | 0.25 | (max_3bar / avg_20bar - 1) / 4 | [0, 1] + ratio |
| Range Contraction | 0.15 | 1 - ATR_10 / ATR_50 | [0, 1] |
| Relative Strength | 0.15 | Cross-sectional return rank | [0, 1] |
| Pivot Breakout | 0.15 | Price vs 20-bar high/low | [0, 1] + direction |
| Institutional Flow | 0.05 | Bars with volume > 5× median / 3 | [0, 1] |

### Bonuses and Gates

- **Squeeze + Volume fired** (vol_ratio > 1.5): composite × 1.30 (30% bonus)
- **Trend-fighting penalty**: shorting a stock with RS > 0.5 → squeeze & pivot halved
- **Pre-filter**: composite < 0.15 → not created
- **Post-filter**: composite < 0.20 → filtered out
- **Top-N**: 8 breakout signals

---

## 19. KELLY SIZER DEEP DIVE

### Complete Sizing Formula

```
target_weight = (kelly_raw × 0.5)                    # Half-Kelly
              × drawdown_scale(dd)                     # [0.1, 1.0]
              × vol_scale(stock_vol)                   # [0, 2.0]
              × regime_scale(regime)                    # [0.1, 1.2]
              × confidence_scale(conf, ml_trained)     # [0.3, 1.5]
              × breakout_bonus(brk_score, ml_trained)  # [1.0, 2.0]
```

### Example Calculation

```
Scenario: stress regime, 5% drawdown, stock vol 20%, ML confidence 0.6,
          breakout score 0.4, regime Kelly = 0.12

kelly_raw = 0.12
kelly_half = 0.06
dd_scale = 1.0 - (0.05/0.25) × 0.9 = 0.82
vol_scale = min(0.15/0.20, 2.0) = 0.75
regime_scale = 0.30 (stress)
conf_scale = 0.3 + 0.6 × 1.2 = 1.02
brk_bonus = 1.0 (< 0.5)

target_weight = 0.06 × 0.82 × 0.75 × 0.30 × 1.02 × 1.0 = 0.0113 (1.13%)

On $112K equity: notional = $1,265
→ SKIP: below $2,000 minimum
```

---

## 20. ADAPTIVE EXIT ENGINE DEEP DIVE

### Exit Level Creation from Entry

```
entry_price = $150.00
ATR(14) = $3.00
regime = "normal"

risk_distance = $3.00 × 1.5 (normal stop ATR) = $4.50

stop_loss     = $150.00 - $4.50 = $145.50
take_profit   = $150.00 + $4.50 × 4.0 (normal TP R) = $168.00
partial_tp    = $150.00 + $4.50 × 3.0 = $163.50
trailing_stop = $145.50 (starts at stop loss)
trailing_activation = $150.00 + $3.00 × 3.0 = $159.00
```

### Trailing Stop Mechanics

```
When price reaches $159 (3 ATR above entry):
  → trailing_active = True

At peak $165 (regime still "normal"):
  trail_distance = $3.00 × 2.5 = $7.50
  new_trail = $165 - $7.50 = $157.50
  trailing_stop = max($145.50, $157.50) = $157.50  ← RATCHETED UP

If price drops to $157.50 → EXIT via trailing stop
```

---

## 21. REGIME DETECTOR DEEP DIVE

### Feature Extraction → Probability → Smoothing → Label

```
Raw Data → 4 Signals:
  ├── Trend slope (SMA slope over 10 bars)
  ├── Price vs SMA distance
  ├── ATR ratio + returns vol
  └── Volume anomaly

Signals → Raw Scores (additive):
  ├── trending_up: +2 (strong trend) or +1 (above SMA)
  ├── trending_down: +2 or +1
  ├── chop: +1.5 (no trend) or +0.5 (near SMA)
  ├── high_vol: +2 (high ATR) or +1 (high returns vol)
  ├── low_vol: +1.5 (low ATR)
  └── stress: +2 (vol anomaly + high ATR) or +1 (extreme vol anomaly)

Scores → Softmax → Probabilities (sum to 1.0)

Probabilities → EMA Smoothing (α=0.3) → prevent whipsaw

Smoothed → argmax → Primary Regime Label
```

### Churn Detection

- Window: 20 labels. Changes / (window - 1) = churn rate.
- Not directly used for gating but available for monitoring.

---

## 22. SELF-EVOLUTION DEEP DIVE

### 10 Evolution Sub-Steps (per epoch)

```
EVOLUTION (requires >= 8 trades)
  │
  ├── Step 1: Signal Weight Adaptation
  │   ├── High-conf vs low-conf win rate comparison
  │   ├── ML weight boost if high-conf outperforms by 5%+
  │   ├── Momentum boost/cut based on direction accuracy
  │   └── Normalize 5 weights to sum = 1.0
  │
  ├── Step 2: Exit Parameter Tuning
  │   ├── Stop too tight? (>45% stopped out) → widen ×1.10
  │   ├── Stop too loose? (<15% stopped out) → tighten ×0.95
  │   ├── Trail profitable? → widen trail for bigger captures
  │   └── Partial TP calibration based on full TP comparison
  │
  ├── Step 3: Regime-Size Scaling
  │   ├── Profitable regime → scale up ×1.08
  │   └── Losing regime → scale down ×0.90
  │
  ├── Step 4: Feature Selection/Weighting
  │   ├── Trust = f(direction_accuracy)
  │   ├── Important features → weight up to 2.0
  │   └── Unimportant features → gradually decay toward 0.3
  │
  ├── Step 5: Symbol Fitness
  │   ├── Winners → fitness up toward 0.95
  │   └── Losers → fitness down toward 0.10
  │
  ├── Step 6: Direction Threshold Calibration
  │   ├── High-conf poor WR → tighten thresholds (fewer trades)
  │   └── High-conf good WR → loosen thresholds (more trades)
  │
  ├── Step 7: Breakout Weight Adaptation
  │   ├── Breakout trades profitable → boost squeeze+volume weights
  │   └── Breakout trades losing → reduce squeeze+volume weights
  │
  ├── Step 8: Breakout Period Adaptation
  │   ├── Losing + long holds → shorten periods (indicators lagging)
  │   └── Losing + short holds → lengthen periods (too twitchy)
  │
  ├── Step 9: Short-Side Resurrection
  │   ├── Enable: WR >= 55% AND avg PnL > $10 AND >= 10 trades
  │   └── Disable: WR < 35%
  │
  └── Step 10: XGBoost Hyperparameter Evolution
      ├── Good accuracy (>60%) → increase capacity
      ├── Poor accuracy (<50%) → regularize harder
      └── Middling → gentle regularization nudge
```

### EMA Update (Safety-Bounded)

All parameter updates use:
```
delta = α × new + (1-α) × old - old
max_delta = |old| × 0.20 + 0.005     # max 20% shift per step
clamped_delta = clamp(delta, -max_delta, max_delta)
result = old + clamped_delta
```

---

## 23. UNIVERSE & SECTOR MANAGEMENT

### Dynamic Universe Rotation

```
ROTATION (on retrain):
  │
  ├── Update fitness from recent trades:
  │   └── fitness = 0.6 × win_rate + 0.4 × (0.5 + pnl_norm/2)
  │
  ├── Decay all fitness toward 0.50 (×0.95)
  │
  ├── DROP (up to 5 symbols):
  │   ├── No open position
  │   ├── >= 3 observed rotations
  │   └── fitness < 0.40
  │
  ├── ADD (up to 10 symbols):
  │   ├── Not currently active
  │   ├── fitness >= 0.50
  │   └── >= 3 rotations OR already traded
  │
  └── Enforce bounds: [15, 80] symbols
      └── NEVER drop symbols with open positions
```

### Sector Diversification Gate

| Sector | Symbols | Max Positions |
|---|---|---|
| Technology | AAPL, MSFT, NVDA, AMD, AVGO, INTC, MU, ADBE, CRM, SNOW, PLTR | 4 |
| Communication | GOOGL, META, NFLX | 4 |
| Consumer Discretionary | AMZN, TSLA, COST, WMT, UBER, ABNB | 4 |
| ETF | SPY, QQQ, IWM, XLK, XLE | 4 |
| Healthcare | LLY | 4 |
| Energy | XOM | 4 |
| Industrials | CAT | 4 |
| Financials | COIN, SQ | 4 |
| Unknown | Any new scanner finds | NEVER BLOCKED |

The gate also tracks `planned_entries` within a single tick to prevent multiple same-sector entries in one cycle.

---

## 24. BACKGROUND TRAINING & TRANSFER LEARNING

### Background Training

```
BACKGROUND TRAINER (ProcessPoolExecutor)
  │
  ├── Serialize: features, model state, last 200 trades, evolution params
  ├── Separate process: train ML + evolve params
  ├── Stuck detection: > 30 ticks → force-reset
  │
  └── Atomic swap on completion:
      ├── New classifier + regressor + ensemble
      ├── New feature columns
      └── New evolved params → applied to all live components
```

### Transfer Learning

```
CROSS-RUN KNOWLEDGE (persisted in transfer_knowledge.json)
  │
  ├── Last 20 run snapshots (decay-weighted, newest = 1.0)
  ├── Global feature importance (EMA across all runs)
  ├── Best-ever Sharpe params
  ├── Per-regime best config
  │
  └── Warm-start priority:
      ├── 1. Regime-specific best (if Sharpe > 0)
      ├── 2. Decay-weighted average of all snapshots
      └── 3. Seed feature weights from global importance
```

### Market Scanner

```
MARKET SCANNER (every 6 ticks ≈ 60s)
  │
  ├── 3 concurrent API calls:
  │   ├── Most-actives by volume (top 100)
  │   ├── Top gainers (top 50)
  │   └── Top losers (top 50)
  │
  ├── Exclusion: 30 leveraged/inverse ETFs
  │
  ├── Price filter: [$10, $1500]
  ├── Volume filter: >= 500,000
  │
  ├── 7-dimension tension score:
  │   ├── Range compression (0.18)
  │   ├── Volume surge (0.18)
  │   ├── Breakout proximity (0.18)
  │   ├── Gap momentum (0.12)
  │   ├── Minute-bar acceleration (0.12)
  │   ├── Body-to-range ratio (0.12)
  │   └── Range narrowing (0.10)
  │
  ├── Tension threshold: >= 0.30
  └── Max candidates: 80, top 20 injected into universe
```

---

## 25. CONFIGURATION REFERENCE

### Engine Configuration (.env)

| Variable | Value | Effect |
|---|---|---|
| `ORGANISM_TICK_INTERVAL_SECONDS` | 10 | Tick frequency |
| `ORGANISM_LIVE_TIMEFRAME` | 1Min | Bar timeframe |
| `ORGANISM_MAX_POSITIONS` | 15 | Max simultaneous positions |
| `ORGANISM_LONG_ONLY` | true | Block all short entries |
| `ORGANISM_RETRAIN_INTERVAL` | 180→200 | Ticks between retrains |
| `ORGANISM_ML_DECAY_RATE` | 0.005 | Time-decay on training samples |
| `ORGANISM_MAX_PER_SECTOR` | 4 | Sector concentration limit |
| `ORGANISM_DRAWDOWN_KILL_PCT` | 0.08 | 8% drawdown kill switch |
| `ORGANISM_LIVE_LOOKBACK` | 500 | Bars of history to fetch |
| `ORGANISM_MIN_BARS` | 200→50 | Minimum bars for a symbol |

### Key Thresholds Summary

| Threshold | Value | Location | Purpose |
|---|---|---|---|
| Alpha composite minimum | 0.15 | alpha_scanner | Minimum score to be a candidate |
| Breakout composite minimum | 0.20 | breakout_scanner | Minimum breakout score |
| Pure breakout entry threshold | 0.55 | live_engine | Breakout-only entries need high score |
| Symbol fitness gate | 0.35 | live_engine | Chronic loser rejection |
| ML confidence reversal | 0.30 | live_engine | ML reversal exit confidence floor |
| Max loss safety net | 15% | live_engine + exits | Absolute loss limit |
| Kelly ML floor | 0.08×conf | kelly_sizer | Minimum sizing when ML is confident |
| Kelly breakout floor | 0.01×score | kelly_sizer | Minimum sizing on strong breakout |
| Kelly min notional | $2,000 | kelly_sizer | Minimum position size |
| Kelly max per position | 10% | kelly_sizer | Position concentration limit |
| Kelly max portfolio | 95% | kelly_sizer | Total exposure limit |
| Drawdown risk-off | 25% | kelly_sizer | No new positions at all |
| Intraday size reduction | 40% | live_engine | First/last 15 min of session |
| Equity-zero threshold | 3 consecutive | live_engine | Block entries on stale data |
| Walk-forward regression | 0.95 | brain_persistence | Don't persist regressing model |

---

## 26. KNOWN REGIME-LABEL MISMATCHES

The regime detector produces: `trending_up`, `trending_down`, `chop`, `high_vol`, `low_vol`, `stress`, `unknown`

The Kelly sizer and exit engine reference additional labels in their lookup tables:
- `trending` → hits default/fallback (Kelly: 0.7, Exits: constructor defaults)
- `normal` → hits default/fallback
- `crisis` → hits default/fallback
- `recovery` → not referenced but would hit default
- `euphoria` → not referenced

**Impact**: When the regime is `low_vol` or `unknown`, the Kelly sizer falls back to regime_scale=0.7, and the exit engine uses constructor defaults (atr_mult=1.5, profit_r=4.0, trail=2.5, max_bars=40). This is conservative but may not be optimal.

**Potential issue**: There is no explicit `normal` regime. The most common operating state (non-trending, non-volatile) maps to `chop` or `low_vol`, which both have reduced position sizing (0.50 for chop, 0.70 fallback for low_vol). The engine may be systematically undersizing positions in calm markets.
