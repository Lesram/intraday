# Evolving Trading Organism — Complete Technical Blueprint

**Version:** 1.0.0  
**Date:** 2026-02-15  
**Status:** Implementation Guide  
**Supersedes:** SELF_LEARNING_ORGANISM_BLUEPRINT.md (partial), BREAKOUT_ALPHA_BLUEPRINT.md (alpha only), LIVING_STRATEGY_SYSTEM_PLAN.md (policy only)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System Architecture](#2-system-architecture)
3. [Current State Inventory](#3-current-state-inventory)
4. [Complete Module Specification](#4-complete-module-specification)
5. [The Evolution Loop — Scientific Foundation](#5-the-evolution-loop--scientific-foundation)
6. [Brain Persistence & Knowledge Retention](#6-brain-persistence--knowledge-retention)
7. [Live Trading Integration Plan](#7-live-trading-integration-plan)
8. [Data Pipeline — Real Data Only](#8-data-pipeline--real-data-only)
9. [Implementation Phases & Milestones](#9-implementation-phases--milestones)
10. [Test Plan & Acceptance Criteria](#10-test-plan--acceptance-criteria)
11. [Risk Safeguards & Governance](#11-risk-safeguards--governance)
12. [Monitoring & Observability](#12-monitoring--observability)
13. [Open Issues & Technical Debt](#13-open-issues--technical-debt)

---

## 1. Executive Summary

The **Evolving Trading Organism** is a closed-loop autonomous trading system that:

1. **Senses** — Ingests real-time and historical market data via Alpaca API
2. **Understands** — Computes 68+ ML features per symbol per bar, detects market regime
3. **Decides** — XGBoost ensemble predicts direction + magnitude, alpha scanner ranks candidates, breakout scanner identifies setups
4. **Acts** — Kelly-sized entries with momentum pyramiding through the Alpaca broker (paper or live)
5. **Observes** — Tracks every trade outcome: PnL, exit reason, direction accuracy, slippage, holding period
6. **Learns** — XGBoost retrains on accumulated trade data with walk-forward gating
7. **Evolves** — Meta-learning engine adapts 7 parameter categories from outcome evidence
8. **Remembers** — All learned state persists to disk and accumulates across runs

The system is designed so that **every run makes it smarter**. Knowledge is never thrown away — it is retained, compressed, and recycled. The organism gets progressively better at reading the market, sizing positions, timing exits, and selecting which instruments to trade.

### Design Principles

| Principle | Implementation |
|-----------|----------------|
| **No fake data** | All data from Alpaca API (historical bars + live quotes/trades) |
| **No mock execution** | Paper trading uses real Alpaca paper account; live uses real brokerage |
| **Gradual evolution** | EMA smoothing (α=0.30), max 20% parameter shift per epoch |
| **Knowledge compounds** | Brain persists models, trades, features, evolved params across runs |
| **Fail-safe by default** | Governance kill switches, circuit breaker, drawdown halt, shadow mode |
| **Evidence-based only** | Every parameter change is justified by statistically significant trade data |

### Target Performance Trajectory

| Metric | Baseline (v3.0, no evolution) | Target (mature organism, 50+ runs) |
|--------|-------------------------------|-------------------------------------|
| Annual Return | +35% | +60–100% |
| Sharpe Ratio | 2.83 | 3.0–4.0 |
| Max Drawdown | 3.25% | <5% |
| Win Rate | 72.9% | 70–80% |
| W/L Ratio | 4.65 | 5.0+ |
| Direction Accuracy | 62% | 70%+ |

These targets assume compounding intelligence over 50+ brain-persisted runs. The organism should never regress — the walk-forward gate and evolution safety clamps ensure monotonic improvement.

---

## 2. System Architecture

### 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        EVOLVING TRADING ORGANISM                            │
│                                                                             │
│  ┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────┐  │
│  │   PERCEPTION LAYER   │  │    DECISION LAYER    │  │  EXECUTION LAYER │  │
│  │                      │  │                      │  │                  │  │
│  │  ┌────────────────┐  │  │  ┌────────────────┐  │  │  ┌────────────┐ │  │
│  │  │ Alpaca Client  │  │  │  │ Alpha Scanner  │  │  │  │ Kelly Sizer│ │  │
│  │  │ (data source)  │  │  │  │ (candidate     │  │  │  │ (position  │ │  │
│  │  └───────┬────────┘  │  │  │  ranking)      │  │  │  │  sizing)   │ │  │
│  │          │           │  │  └───────┬────────┘  │  │  └─────┬──────┘ │  │
│  │  ┌───────▼────────┐  │  │          │           │  │        │        │  │
│  │  │ ML Feature Eng │  │  │  ┌───────▼────────┐  │  │  ┌─────▼──────┐ │  │
│  │  │ (68 features)  │──│──│─►│ ML Signal Gen  │  │  │  │ Pyramider  │ │  │
│  │  └───────┬────────┘  │  │  │ (XGB ensemble) │  │  │  │ (3 layers) │ │  │
│  │          │           │  │  └───────┬────────┘  │  │  └─────┬──────┘ │  │
│  │  ┌───────▼────────┐  │  │          │           │  │        │        │  │
│  │  │ Regime Detect  │  │  │  ┌───────▼────────┐  │  │  ┌─────▼──────┐ │  │
│  │  │ (market state) │──│──│─►│Breakout Scanner│  │  │  │ Exit Eng   │ │  │
│  │  └────────────────┘  │  │  │ (6 detectors)  │  │  │  │ (ATR+trail)│ │  │
│  │                      │  │  └────────────────┘  │  │  └────────────┘ │  │
│  └──────────────────────┘  └──────────────────────┘  └────────┬───────┘  │
│                                                                │          │
│  ┌─────────────────────────────────────────────────────────────▼────────┐ │
│  │                          LEARNING LAYER                              │ │
│  │                                                                      │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │ │
│  │  │ Continuous   │  │  Evolution   │  │    Brain     │               │ │
│  │  │ Learner      │  │  Engine      │  │  Persistence │               │ │
│  │  │              │  │              │  │              │               │ │
│  │  │ • Retrain    │  │ • 7 adapters │  │ • Models     │               │ │
│  │  │ • Drift det  │  │ • EMA smooth │  │ • Trades     │               │ │
│  │  │ • Walk-fwd   │  │ • Safety     │  │ • Params     │               │ │
│  │  │   gate       │  │   clamps     │  │ • Equity     │               │ │
│  │  └──────────────┘  └──────────────┘  └──────────────┘               │ │
│  │                                                                      │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
│                                                                           │
│  ┌──────────────────────────────────────────────────────────────────────┐ │
│  │                        GOVERNANCE LAYER                              │ │
│  │  Kill switches │ Drawdown halt │ Change budget │ Freeze controls    │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 The Feedback Loop (One Complete Cycle)

Every epoch (60 bars ≈ 3 months of daily data), the organism completes one full evolution cycle:

```
    ┌─────────────────────────────────────────────────────────────┐
    │                                                             │
    ▼                                                             │
 ┌──────┐    ┌──────┐    ┌─────┐    ┌──────┐    ┌──────┐    ┌───┴──┐
 │ SENSE│───►│DECIDE│───►│ ACT │───►│RECORD│───►│LEARN │───►│EVOLVE│
 │      │    │      │    │     │    │      │    │      │    │      │
 │Data  │    │ML +  │    │Enter│    │Track │    │XGB   │    │Adapt │
 │Fetch │    │Alpha │    │Exit │    │Every │    │Re-   │    │All   │
 │Feats │    │Score │    │Size │    │Trade │    │train │    │Params│
 │Regime│    │Break-│    │Pyra-│    │PnL   │    │Walk- │    │Signal│
 │Detect│    │out   │    │mid  │    │Reason│    │fwd   │    │Exit  │
 │      │    │      │    │     │    │Conf  │    │Gate  │    │Size  │
 └──────┘    └──────┘    └─────┘    └──────┘    └──────┘    └──────┘
                                                              │
                                                    ┌─────────▼──────────┐
                                                    │   BRAIN PERSIST    │
                                                    │                    │
                                                    │ Save evolved state │
                                                    │ to disk. Next run  │
                                                    │ starts HERE, not   │
                                                    │ from scratch.      │
                                                    └────────────────────┘
```

### 2.3 Mode Matrix

| Mode | Data Source | Order Execution | Position Tracking | Brain Persist | Evolution |
|------|-----------|----------------|-------------------|---------------|-----------|
| **Backtest** | Alpaca historical (500+ daily bars) | Simulated with slippage model | In-memory portfolio | ✅ Disk (JSON/CSV/joblib) | ✅ Full |
| **Paper** | Alpaca paper account + live WebSocket | Real paper orders via Alpaca API | PostgreSQL + Alpaca sync | ✅ Disk + DB | ✅ Full |
| **Live** | Alpaca live + WebSocket | Real orders via outbox pattern | PostgreSQL + Alpaca sync | ✅ Disk + DB | ✅ Gated (shadow→canary→active) |

---

## 3. Current State Inventory

### 3.1 What Exists (Built & Working)

| Module | File | Lines | Status | Tests |
|--------|------|-------|--------|-------|
| ML Feature Engine | `backend/organism/ml_features.py` | 379 | ✅ Production | ✅ |
| ML Signal Generator | `backend/organism/ml_signal.py` | 423 | ✅ Production, dynamic thresholds | ✅ |
| Alpha Scanner | `backend/organism/alpha_scanner.py` | 216 | ✅ Production, symbol fitness | ✅ |
| Breakout Scanner | `backend/organism/breakout_scanner.py` | 436 | ✅ Production | ✅ |
| Kelly Position Sizer | `backend/organism/kelly_sizer.py` | 284 | ✅ Production, evolved regime scales | ✅ |
| Adaptive Exit Engine | `backend/organism/adaptive_exits.py` | 455 | ✅ Production, evolved params | ✅ |
| Continuous Learner | `backend/organism/continuous_learner.py` | 392 | ✅ Production, PnL-weighted gate | ✅ |
| Momentum Pyramider | `backend/organism/pyramider.py` | 270 | ✅ Production | ✅ |
| Brain Persistence | `backend/organism/brain_persistence.py` | 693 | ✅ Production | ✅ |
| Self-Evolution Engine | `backend/organism/self_evolution.py` | 853 | ✅ Production, 7 adapters | ✅ 14 tests |
| Governance Controller | `backend/organism/governance.py` | 185 | ✅ Production | ✅ |
| Regime Detector | `backend/organism/regime.py` | 482 | ✅ Production | ✅ |
| Organism Runner | `backend/organism/runner.py` | 155 | ✅ Production (live tick coord) | ✅ |
| Walk-Forward Evaluator | `backend/organism/walk_forward.py` | 460 | ✅ Production | ✅ |
| Training Orchestrator | `backend/organism/training.py` | 372 | ⚠️ Partial (data fetch broken) | ✅ |
| Promotion Controller | `backend/organism/promotion.py` | 407 | ✅ Production | ✅ |
| Attribution Service | `backend/organism/attribution.py` | 422 | ✅ Production | ✅ |
| Feature Store | `backend/organism/feature_store.py` | 345 | ⚠️ Unused in practice | ✅ |
| Nightly Scheduler | `backend/organism/nightly_scheduler.py` | 121 | ✅ Production | ✅ |
| **Backtest v3** | `scripts/run_breakout_organism.py` | 1594 | ✅ Full integration | Manual |
| **Alpaca Client** | `backend/data/alpaca_client.py` | 924 | ✅ Production (sync+async) | ✅ |
| **Order Service** | `backend/services/order_service.py` | 1614 | ✅ Full (circuit breaker, outbox) | ✅ |
| **Multi-Strategy Live** | `backend/services/multi_strategy_live_runner.py` | 430 | ✅ 10 strategies | ✅ |

**Total: 510+ tests passing, 16 organism modules, full broker integration.**

### 3.2 What's Missing (Gaps to Close)

| Gap ID | Description | Severity | Phase |
|--------|-------------|----------|-------|
| **G-01** | Backtest path and live path are disconnected — organism ML pipeline doesn't feed into `OrderService` | 🔴 Critical | Phase 2 |
| **G-02** | `governance.py` state not persisted in brain | 🟡 Medium | Phase 1 |
| **G-03** | `regime.py` state not persisted in brain (smoothed probs, history) | 🟡 Medium | Phase 1 |
| **G-04** | Inline `detect_regime()` in backtest script is simplified — doesn't use full `RegimeDetector` | 🟡 Medium | Phase 1 |
| **G-05** | `_close_all_positions()` doesn't create TradeRecords — end-of-run positions lost | 🟡 Medium | Phase 1 |
| **G-06** | No walk-forward gate on brain saves — backtest brain could overfit | 🟡 Medium | Phase 2 |
| **G-07** | `training.py` data fetch broken — `AlpacaClient()` called without credentials | 🟡 Medium | Phase 2 |
| **G-08** | `feature_store.py` never called in any pipeline | 🟠 Low | Phase 3 |
| **G-09** | Breakout scanner indicator periods not tunable via evolution | 🟠 Low | Phase 3 |
| **G-10** | No live organism runner that combines ML + breakout + evolution | 🔴 Critical | Phase 2 |
| **G-11** | Brain lacks locking for concurrent writes | 🟠 Low | Phase 3 |
| **G-12** | Trade history CSV grows unbounded — no compression or rotation | 🟠 Low | Phase 3 |
| **G-13** | Multi-run evolution regression testing — no automated check that brain_N > brain_N-1 | 🟡 Medium | Phase 2 |

---

## 4. Complete Module Specification

### 4.1 Module 1 — ML Feature Engine (`ml_features.py`)

**Purpose:** Compute 68 lookahead-free features per symbol per bar.

**Feature Categories (68 total):**

| Category | Count | Features |
|----------|-------|----------|
| Price Action | 15 | Returns (1d–20d), log return, momentum accel, close/high/low ratios, range pct, gap |
| Moving Averages | 8 | EMA 8/21/50, SMA 50/200, EMA crossover signals, distance-to-MA |
| Volatility | 11 | ATR 14/50, BB width/squeeze/position, realized vol, vol expansion, vol regime, NATR |
| Volume | 8 | Volume SMA ratio, OBV, OBV slope, VWAP distance, volume trend, cumulative delta, anomaly flag |
| Momentum | 8 | RSI 14/7, MACD signal/histogram, stochastic K/D, ADX 14 |
| Trend | 4 | Trend strength, direction, Z-score 20, HH/HL pattern |
| Cross-Asset | 8 | SPY beta, SPY correlation, relative return, sector momentum (from SPY reference) |
| Regime | 6 | Vol regime, trend regime, ATR ratio, vol percentile, regime composite |

**Contract:**  
- Input: `DataFrame` with columns `[open, high, low, close, volume, timestamp]`, optional `spy_df`
- Output: Same DataFrame + 68 feature columns
- Guarantee: No NaN in final row (filled with 0.0), no lookahead bias

### 4.2 Module 2 — ML Signal Generator (`ml_signal.py`)

**Purpose:** XGBoost ensemble for direction classification + return magnitude regression.

**Architecture:**

```
Input: 68 features (per symbol, per bar)
       │
       ├──► XGBClassifier ──► P(up) ∈ [0,1]
       │    • 200 estimators, depth=5
       │    • L1=0.1, L2=1.0, subsample=0.8
       │    • Target: 1 if ret_next > 0
       │
       └──► XGBRegressor  ──► predicted_return ∈ ℝ
            • Same hyperparams
            • Target: actual next-bar return
       │
       ▼
Direction = +1 if P(up) > threshold_buy
           -1 if P(up) < threshold_sell
            0 otherwise

Confidence  = P(up) if buy, (1 - P(up)) if sell
Pred Return = regressor output × direction
```

**Dynamic (Evolved) Parameters:**
- `direction_threshold_buy` — default 0.55, range [0.50, 0.70], evolved by EvolutionEngine §6
- `direction_threshold_sell` — default 0.45, range [0.30, 0.50], mirrors buy threshold
- `feature_selection` — features with evolved weight < 0.20 are dropped (minimum 15 safety)

**Training:** Rolling window of 200–250 bars. Walk-forward gated.

### 4.3 Module 3 — Alpha Scanner (`alpha_scanner.py`)

**Purpose:** Rank all symbols by composite alpha score for trade candidate selection.

**Scoring System:**

$$\text{composite} = w_{ML} \times S_{ML} + w_{vol} \times S_{vol} + w_{mom} \times S_{mom} + w_{brk} \times S_{brk} + w_{reg} \times S_{reg}$$

Where:
- $S_{ML}$ = `confidence × |predicted_return| × 20`, capped at 1.0
- $S_{vol}$ = `(volume_ratio - 1) / 2`, capped at 1.0
- $S_{mom}$ = cross-sectional 20-day return rank [0, 1]
- $S_{brk}$ = `(1 - BB_squeeze) × 0.6 + vol_expansion × 0.4`
- $S_{reg}$ = regime-direction alignment score [0, 1]

**Weights (evolved):** Default `[0.35, 0.20, 0.20, 0.15, 0.10]`, adapted by EvolutionEngine from trade attribution.

**Symbol Fitness Scaling:**

$$\text{composite}_{\text{final}} = \text{composite} \times (0.5 + f_{\text{symbol}})$$

Where $f_{\text{symbol}} \in [0.1, 0.95]$ is the symbol's rolling fitness from EvolutionEngine.

### 4.4 Module 4 — Breakout Scanner (`breakout_scanner.py`)

**Purpose:** 6-detector proprietary breakout identification system.

| Detector | Weight | Signal |
|----------|--------|--------|
| Bollinger Squeeze | 25% | BB width percentile (tighter = higher). Fires when BB exits Keltner Channel |
| Volume Surge | 25% | Max of last 3 bars' vol / 20-bar avg. Linear [1×, 5×] |
| Range Contraction | 15% | ATR₁₀/ATR₅₀ ratio. Lower = more contracted |
| Relative Strength | 15% | Cross-sectional 20-day return rank |
| Pivot Breakout | 15% | Price vs 20-bar high/low. Excess/ATR |
| Institutional Flow | 5% | Count of 5×+ median volume bars in 5 days |

**Composite with Bonus:**

$$\text{score} = \sum w_i \times d_i + \mathbb{1}[\text{squeeze\_firing} \wedge \text{vol\_ratio} > 1.5] \times 0.30$$

Capped at 1.0. Minimum 0.30 to qualify.

**Evolved Weights:** All 6 detector weights adapted by EvolutionEngine from breakout trade outcomes.

### 4.5 Module 5 — Kelly Position Sizer (`kelly_sizer.py`)

**Purpose:** Half-Kelly sizing with regime conditioning and breakout conviction bonus.

**Formula:**

$$f^* = \frac{p \times b - q}{b} \quad \text{(Kelly fraction)}$$

$$\text{shares} = \frac{\text{equity} \times f^*/2 \times R_{\text{regime}} \times B_{\text{breakout}}}{\text{price}}$$

Where:
- $p$ = win probability from ML confidence, $q = 1 - p$, $b$ = W/L ratio (default 2.0)
- $R_{\text{regime}}$ = regime-specific scale factor (evolved), range [0.05, 1.50]
- $B_{\text{breakout}}$ = `1.0 + min(breakout_score × 0.5, 0.5)` — conviction bonus

**Constraints:** Max 12% per position, min $2,000, max 8 concurrent positions.

**Evolved Parameters:** All regime scale factors adapted from PnL per regime.

### 4.6 Module 6 — Adaptive Exit Engine (`adaptive_exits.py`)

**Purpose:** ATR-based exit system with trailing stops, partial take-profit, and regime conditioning.

**Exit Hierarchy (checked every bar, in order):**

1. **Stop Loss** — entry ± `ATR × stop_atr_scale × regime_multiplier`
2. **Partial Take Profit** — sell `partial_tp_pct` of shares at `partial_tp_r × R` of profit
3. **Trailing Stop** — activates after `trailing_start_atr × ATR` move, trails at `trailing_distance × ATR` from peak
4. **Full Take Profit** — `profit_r_multiple × R` (regime-adjusted: 3R in chop, 8R in crisis)
5. **Time Decay** — reduce position by 25% if held beyond `max_bars` (regime-adjusted)

**Evolved Parameters (5 scales, applied as multipliers on base values):**
- `stop_atr_scale` — base 1.0, widens if stop-out rate > 45%, tightens if < 15%
- `trailing_start_atr_scale` — base 1.0
- `trailing_distance_scale` — base 1.0, widens if trail captures big winners, tightens if trail losses
- `partial_tp_r_scale` — base 1.0, delays if full-TP avg >> partial avg
- `partial_tp_pct` — base 0.30, increases if partial outperforms full-run trades

### 4.7 Module 7 — Continuous Learning Engine (`continuous_learner.py`)

**Purpose:** The "fast brain" — manages ML model lifecycle within a run.

**Triggers for Retrain:**
1. **Scheduled** — every 60 bars
2. **Drift-detected** — PSI > 0.10 on feature distributions
3. **Performance degradation** — direction accuracy drops below 50%

**Walk-Forward Gate (PnL-weighted composite score):**

$$\text{score} = 0.4 \times \text{hit\_rate} + 0.3 \times \text{accuracy} + 0.6 \times \max(\text{dir\_accuracy} - 0.5,\ 0)$$

New model accepted if: `new_score - old_score ≥ threshold` OR `new_score ≥ 0.40 AND hit_rate ≥ 0.48`.

If rejected, the old model is restored (full rollback of `_clf`, `_reg`, `_is_trained`).

### 4.8 Module 8 — Self-Evolution Engine (`self_evolution.py`)

**Purpose:** Meta-learning brain that adapts ALL tunable parameters from trade outcome evidence.

**7 Adaptation Algorithms:**

| # | Adapter | What It Changes | Evidence Source |
|---|---------|----------------|-----------------|
| 1 | Signal Weight | Alpha scanner `w_ML`, `w_vol`, `w_mom`, `w_brk`, `w_reg` | High-conf vs low-conf win rate, direction accuracy |
| 2 | Exit Params | Stop ATR, trailing start/distance, partial TP R/pct | Exit reason distribution × PnL per reason |
| 3 | Regime Scale | Kelly regime multipliers per regime label | Average PnL per regime |
| 4 | Feature Selection | Per-feature weight [0, 2] → drop if < 0.20 | XGBoost importance × direction accuracy |
| 5 | Symbol Fitness | Per-symbol score [0.1, 0.95] → affects alpha ranking | Per-symbol win rate × avg PnL |
| 6 | Direction Thresholds | ML buy/sell confidence thresholds | Win rate at high/medium/low confidence buckets |
| 7 | Breakout Weights | 6 detector weights in breakout scanner | High-breakout vs low-breakout trade PnL comparison |

**Safety Mechanisms:**
- EMA smoothing: `new_value = α × target + (1-α) × old_value` with α = 0.30
- Max shift clamp: no parameter moves more than 20% per epoch
- Minimum trade count: need ≥ 8 trades before adapting
- Weight normalization: alpha weights and breakout weights always sum to 1.0

**All evolved state serializes to `EvolvedParams.to_dict()` for brain persistence.**

### 4.9 Module 9 — Brain Persistence (`brain_persistence.py`)

**Purpose:** Cross-run cumulative learning — the organism's long-term memory.

**Persisted State:**

| Artifact | Format | Contents |
|----------|--------|----------|
| `manifest.json` | JSON | Version stamp, generation #, total runs, cumulative PnL, Sharpe |
| `ml_classifier.joblib` | joblib | Trained XGBClassifier (direction model) |
| `ml_regressor.joblib` | joblib | Trained XGBRegressor (magnitude model) |
| `ml_state.json` | JSON | Feature columns, XGB hyperparams, generation, metrics |
| `learning_state.json` | JSON | Bars seen, trades, PnL, best Sharpe, retrain count, drift events |
| `trade_history.csv` | CSV | ALL trades across ALL runs — the organism's full experience |
| `reference_feats.csv` | CSV | Drift detection baseline features |
| `equity_curve.csv` | CSV | Full equity curve across all runs |
| `epoch_metrics.csv` | CSV | All epoch performance metrics |
| `extra_counters.json` | JSON | Peak equity, breakout/pyramid/partial-TP counts, **evolved_params** |
| `backups/` | Directory | Last 5 brain snapshots for rollback |

**Atomic Write Protocol:**
1. Create `.tmp_save/` directory
2. Write all files to `.tmp_save/`
3. Move existing brain to `backups/` with timestamp
4. Rename `.tmp_save/` to brain directory
5. Prune old backups (keep last 5)
6. If any step fails, clean up `.tmp_save/` — old brain untouched

### 4.10 Module 10 — Momentum Pyramider (`pyramider.py`)

**Purpose:** Add to winning positions at breakout continuation levels.

**3-Layer Pyramid:**

| Layer | Allocation | Trigger | Stop Action |
|-------|-----------|---------|-------------|
| Layer 0 (Entry) | 60% of Kelly size | Initial position open | Stop at entry - ATR × regime_mult |
| Layer 1 (Add) | 30% | Price at +1.5R | Move stop to breakeven |
| Layer 2 (Add) | 10% | Price at +3.0R | Trail at 1.5× ATR from peak |

**Anti-Pyramid (Loss Control):**
- At -0.7R with 1 layer → cut 50%
- At -1.0R → close entire position

### 4.11 Module 11 — Governance Controller (`governance.py`)

**Purpose:** Kill switches, freeze controls, policy versioning — the organism's immune system.

**Controls:**
- `freeze/unfreeze` — halt all parameter adaptation
- `halt_trading/resume` — stop all order execution
- `disable/enable_strategy` — per-strategy kill switch
- `trigger_drawdown_kill` — auto-halt on drawdown > limit (default 5%), adaptive cooldown scales with severity
- `can_change()` — daily change budget (default 100 changes/day)

### 4.12 Module 12 — Regime Detector (`regime.py`)

**Purpose:** Multi-signal market regime detection with probability vectors and smoothing.

**Regime Labels:** `trending_up`, `trending_down`, `chop`, `high_vol`, `low_vol`, `stress`, `unknown`

**Detection Signals:**
- SMA slope direction + magnitude → trend state
- ATR ratio + realized vol percentile → volatility state
- Gap frequency + volume anomalies → stress state

**Output:** Probability vector over regimes + primary label + confidence + churn rate.

---

## 5. The Evolution Loop — Scientific Foundation

### 5.1 Mathematical Framework

The organism operates as a **contextual bandit with delayed rewards**. Each epoch is one "round":

1. **Context** $x_t$ = market regime, feature distributions, symbol universe state
2. **Action** $a_t$ = parameter vector $\theta_t$ (exit params, signal weights, sizing, etc.)
3. **Reward** $r_t$ = realized PnL, Sharpe, win rate over the epoch

The evolution engine solves for the policy:

$$\theta_{t+1} = \theta_t + \alpha \cdot \nabla_\theta \hat{r}(\theta_t, x_t)$$

In practice, we approximate this gradient via **attribution analysis** — we don't compute the gradient analytically but instead observe which parameter regions correlate with high reward and shift toward them using EMA updates.

### 5.2 EMA Update Rule

For each evolved parameter $p$:

$$p_{\text{new}} = \text{clamp}\left(\alpha \cdot p_{\text{target}} + (1-\alpha) \cdot p_{\text{old}},\ \ p_{\text{old}} \pm \delta_{\max}\right)$$

Where:
- $\alpha = 0.30$ (smoothing constant — 30% trust in new evidence)
- $\delta_{\max} = |p_{\text{old}}| \times 0.20 + 0.005$ (max 20% shift + epsilon for near-zero params)
- $p_{\text{target}}$ = computed from trade outcome analysis specific to each adapter

### 5.3 Why EMA, Not Gradient Descent

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| **SGD / Adam** | Optimal convergence | Requires differentiable loss; noisy with <100 trades/epoch | ❌ |
| **Bayesian Optimization** | Sample-efficient | Expensive per iteration; hard to serialize state | ❌ |
| **Evolutionary Strategy (CMA-ES)** | Population-based exploration | Needs many parallel evaluations | ❌ |
| **EMA with attribution** | Stable, no hyperparameter search, serializable, gradual | Suboptimal convergence rate | ✅ |

EMA was chosen because:
1. **Stability** — in a financial system, a parameter oscillation can cost real money
2. **Serializability** — the entire evolved state is a flat dict, trivially persisted
3. **Interpretability** — every change has a human-readable reason in the evolution log
4. **Monotonicity** — with safety clamps, the organism converges and doesn't regress catastrophically

### 5.4 Knowledge Retention Strategy

```
Run N                          Run N+1                        Run N+2
┌───────────────────┐          ┌───────────────────┐          ┌───────────────────┐
│ Load brain (gen G)│          │ Load brain (gen G')│          │ Load brain (gen G")│
│ Fine-tune on new  │          │ Fine-tune on new   │          │ Fine-tune on new  │
│ Epoch 1: trade → │          │ Epoch 1: trade →  │          │ Epoch 1: trade → │
│   evolve params  │          │   evolve params   │          │   evolve params  │
│ Epoch 2: trade → │          │ Epoch 2: trade →  │          │ Epoch 2: trade → │
│   evolve params  │          │   evolve params   │          │   evolve params  │
│ ...              │          │ ...               │          │ ...              │
│ Save brain (gen G')│         │ Save brain (gen G")│         │ Save brain (gen G'")│
└───────────────────┘          └───────────────────┘          └───────────────────┘
       │                              │                              │
       ▼                              ▼                              ▼
  trade_history.csv             trade_history.csv             trade_history.csv
  [run1: 133 trades]            [run1+2: 266 trades]          [run1+2+3: 399 trades]
  equity_curve.csv              equity_curve.csv              equity_curve.csv
  [run1: 300 bars]              [run1+2: 600 bars]            [run1+2+3: 900 bars]
  evolved_params                evolved_params                evolved_params
  [gen 5]                       [gen 10]                      [gen 15]
```

**Key invariant:** Trade history GROWS monotonically. The XGBoost model is retrained on ALL accumulated trade data, not just the current epoch. This means every run benefits from every previous run's experience.

### 5.5 Convergence Monitoring

To verify the organism is actually learning, track these metrics across runs:

| Metric | Expected Trend | Red Flag |
|--------|---------------|----------|
| Cumulative PnL | Monotonically increasing slope | Slope turns negative for 3+ epochs |
| Sharpe per epoch | Increasing or stable | Drops below 1.0 for 3+ epochs |
| Evolution generation | Strictly increasing | Resets to 0 (brain corruption) |
| Direction accuracy | Converging toward 65%+ | Below 50% (worse than random) |
| Win rate | Converging toward 70%+ | Below 55% |
| Feature count (active) | Decreasing (pruning noise) | Drops below 15 (over-pruning) |
| Symbol fitness variance | Increasing (differentiation) | All converge to 0.5 (no learning) |

---

## 6. Brain Persistence & Knowledge Retention

### 6.1 What Must Be Persisted

| State | Currently Persisted? | Fix Required |
|-------|---------------------|--------------|
| XGBoost classifier (direction) | ✅ joblib | None |
| XGBoost regressor (magnitude) | ✅ joblib | None |
| ML training state (generation, metrics) | ✅ JSON | None |
| Learning state (bars, trades, PnL, Sharpe) | ✅ JSON | None |
| Trade history (all runs) | ✅ CSV | None |
| Equity curve (all runs) | ✅ CSV | None |
| Epoch metrics (all runs) | ✅ CSV | None |
| Reference features (drift baseline) | ✅ CSV | None |
| Evolved params (all 7 categories) | ✅ JSON (in extra_counters) | **G-02**: Promote to own file |
| Governance state | ❌ | **G-02**: Add to brain save |
| Regime detector smoothed probs | ❌ | **G-03**: Add to brain save |
| Regime history (churn detection) | ❌ | **G-03**: Add to brain save |
| Breakout scanner cached indicators | ❌ | Low priority, recompute is cheap |
| Pyramider active positions | ❌ | Low priority, only live matters |

### 6.2 Brain Directory Structure (Target)

```
brain/
├── manifest.json                  # Format version, generation, run metadata
├── ml_classifier.joblib           # Trained XGBClassifier
├── ml_regressor.joblib            # Trained XGBRegressor
├── ml_state.json                  # Model hyperparams, feature cols, metrics
├── learning_state.json            # ContinuousLearner state
├── evolved_params.json            # ★ NEW: Dedicated file for EvolvedParams
├── governance_state.json          # ★ NEW: Governance controller state
├── regime_state.json              # ★ NEW: Regime detector running state
├── trade_history.csv              # All trades across all runs
├── reference_feats.csv            # Drift detection baseline
├── equity_curve.csv               # Equity across all runs
├── epoch_metrics.csv              # Per-epoch metrics across all runs
├── evolution_log.csv              # ★ NEW: Full evolution change log
└── backups/
    ├── brain_20260215_083000/
    ├── brain_20260215_090000/
    └── ... (keep last 5)
```

### 6.3 Brain Quality Gates

Before loading a brain, validate:

1. **Format version match** — reject if `BRAIN_FORMAT_VERSION` mismatch (currently v1, no migration)
2. **Model sanity** — loaded XGB model must predict without error on a dummy input
3. **Trade count monotonicity** — new brain must have ≥ trades of old brain
4. **No NaN in evolved params** — every numeric field finite
5. **Weight normalization** — alpha weights sum to 1.0 ± 0.01, breakout weights sum to 1.0 ± 0.01
6. **Feature column consistency** — model's expected features match current feature engine output

---

## 7. Live Trading Integration Plan

### 7.1 Architecture: Bridging Backtest and Live

The backtest engine (`run_breakout_organism.py`) and the live server (`MultiStrategyLiveRunner`) currently operate independently. The integration plan unifies them:

```
                    UNIFIED ORGANISM LIVE RUNNER
                    ────────────────────────────
                              │
                    ┌─────────▼──────────┐
                    │ OrganismLiveEngine  │ ★ NEW: replaces separate paths
                    │                    │
                    │ Combines:          │
                    │ • ML Signal Gen    │
                    │ • Alpha Scanner    │
                    │ • Breakout Scanner │
                    │ • Kelly Sizer      │
                    │ • Adaptive Exits   │
                    │ • Pyramider        │
                    │ • Cont. Learner    │
                    │ • Evolution Engine │
                    │ • Brain Persist    │
                    │ • Governance       │
                    │ • Regime Detector  │
                    └────────┬───────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
     ┌────────▼───────┐ ┌───▼────┐ ┌──────▼───────┐
     │ Alpaca Client  │ │  Order │ │  Portfolio   │
     │ (data stream)  │ │Service │ │  Service     │
     │                │ │(broker)│ │ (positions)  │
     └────────────────┘ └────────┘ └──────────────┘
```

### 7.2 Live Mode — Bar-by-Bar Flow

```python
# Pseudocode for one live tick (called every bar interval)
async def live_tick(engine: OrganismLiveEngine):
    # 1. GOVERNANCE CHECK
    if governance.is_trading_halted:
        return

    # 2. FETCH LATEST DATA (real data, not historical)
    bars = await alpaca_client.get_latest_bars(symbols, lookback=250)
    
    # 3. COMPUTE FEATURES (same 68 features as backtest)
    features_by_symbol = {sym: compute_ml_features(df) for sym, df in bars.items()}
    
    # 4. DETECT REGIME
    regime = regime_detector.detect(features_by_symbol["SPY"])
    
    # 5. CHECK EXITS on existing positions (via Alpaca positions)
    positions = await portfolio_service.get_positions()
    for pos in positions:
        exit_signal = exit_engine.check_exit(pos, features_by_symbol[pos.symbol], regime)
        if exit_signal.action != "hold":
            await order_service.submit_order(pos.symbol, exit_signal.shares, "sell")
    
    # 6. CHECK PYRAMIDS on existing positions
    for pos in positions:
        pyramid_action = pyramider.check_pyramid(pos, current_price)
        if pyramid_action.action == "add":
            await order_service.submit_order(pos.symbol, pyramid_action.shares, "buy")
    
    # 7. SCAN FOR NEW ENTRIES
    breakout_signals = breakout_scanner.scan(features_by_symbol)
    ml_signals = signal_gen.predict_batch(features_by_symbol)
    candidates = alpha_scanner.scan(features_by_symbol, ml_signals, regime)
    
    # 8. SIZE POSITIONS
    sizes = kelly_sizer.size_positions(candidates, equity, regime)
    
    # 9. EXECUTE ENTRIES (via real broker)
    for size in sizes:
        if len(positions) < MAX_OPEN_POSITIONS:
            await order_service.submit_order(size.symbol, size.shares, "buy")
    
    # 10. RECORD TRADE OUTCOMES for closed positions
    for fill in get_recent_fills():
        learner.record_trade(fill_to_trade_record(fill))
    
    # 11. PERIODIC: RETRAIN + EVOLVE (every retrain_interval bars)
    if learner.should_retrain():
        learner.retrain(features_by_symbol)
        evolved_params = evolution_engine.evolve(evolved_params, learner.trade_history)
        apply_evolved_params(evolved_params, ...)
        brain.save(...)  # Persist all learned state
```

### 7.3 Execution Mode Progression

| Stage | Duration | Order Mode | Description |
|-------|----------|-----------|-------------|
| **1. Backtest Validation** | 3+ runs | Simulated | Prove evolution improves across runs with historical data |
| **2. Paper Shadow** | 1 week | `shadow` (log-only) | Organism generates signals, no real orders — compare to baseline |
| **3. Paper Execute** | 2 weeks | `execute` on paper | Real paper orders via Alpaca paper account |
| **4. Paper Canary** | 1 week | `execute` on paper | Reduced universe (5 symbols), monitor closely |
| **5. Live Shadow** | 1 week | `shadow` on live | Same as #2 but against live market feed |
| **6. Live Canary** | 2 weeks | `execute` on live | 5% of capital, 3 symbols max |
| **7. Live Ramp** | 4 weeks | `execute` on live | 15% of capital, 10 symbols |
| **8. Live Active** | Ongoing | `execute` on live | Full capital, full universe |

**At every stage transition:**
- Brain is saved
- Performance report generated
- Comparison against baseline and previous stage
- Manual approval required for stages 5–8

### 7.4 Environment Configuration

```bash
# ── Data ──────────────────────────────────────────────────
ALPACA_API_KEY=<key>
ALPACA_SECRET_KEY=<secret>
ALPACA_PAPER=true                          # true=paper, false=live

# ── Organism Core ─────────────────────────────────────────
ORGANISM_ENABLED=1
ORGANISM_NIGHTLY_ENABLED=1
ORGANISM_BRAIN_DIR=./brain                 # Brain persistence directory
ORGANISM_FREEZE_ADAPTATION=0               # 1=freeze all evolution
ORGANISM_HALT_TRADING=0                    # 1=emergency stop
ORGANISM_MAX_CHANGES_PER_DAY=100
ORGANISM_DRAWDOWN_KILL_PCT=0.05            # 5% drawdown halt

# ── Live Runner ───────────────────────────────────────────
ORGANISM_LIVE_ENABLED=1
ORGANISM_LIVE_INTERVAL_SECONDS=86400       # 1 day for daily bars
ORGANISM_LIVE_SYMBOLS=AAPL,MSFT,GOOGL,...  # Universe
ORGANISM_LIVE_LOOKBACK=500
ORGANISM_LIVE_TIMEFRAME=1Day

# ── Execution Mode ────────────────────────────────────────
TRADING_EXECUTION_MODE=shadow              # shadow|dry_run|execute

# ── Database ──────────────────────────────────────────────
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/algotrading
```

---

## 8. Data Pipeline — Real Data Only

### 8.1 Data Sources (No Fakes)

| Source | Usage | Format | Frequency |
|--------|-------|--------|-----------|
| **Alpaca Historical Bars** | Backtest + live lookback | OHLCV DataFrame | On-demand |
| **Alpaca Latest Quote** | Current price for live exits | Mid-price float | Per-bar |
| **Alpaca WebSocket** | Real-time order fills | Event stream | Continuous |
| **Alpaca Account API** | Equity, buying power, positions | JSON | Per-tick |
| **PostgreSQL** | Order history, position tracking, lifecycle events | Relational | Continuous |
| **Brain Files** | ML models, trade history, evolved params | Disk (JSON/CSV/joblib) | Per-epoch |

### 8.2 Data Quality Checks

**Before every tick:**

1. **Freshness** — reject bars older than 3 calendar days (configurable)
2. **Completeness** — require ≥ 200 bars per symbol for feature computation
3. **OHLCV sanity** — `high ≥ max(open, close)`, `low ≤ min(open, close)`, `volume ≥ 0`
4. **Symbol coverage** — at least 50% of universe must have valid data
5. **SPY available** — required for cross-asset features and relative strength

**Before ML prediction:**

6. **Feature NaN rate** — reject symbols with >5% NaN in latest feature row
7. **Feature range** — flag features outside 5σ of historical distribution
8. **Drift check** — PSI > 0.10 triggers ContinuousLearner retrain

**Before order execution:**

9. **Price sanity** — current price within 10% of last close (gap detection)
10. **Liquidity** — average daily volume > 50,000 shares
11. **Market hours** — only trade during regular session (9:30 AM – 4:00 PM ET)

### 8.3 Feature Computation Pipeline

```
Raw OHLCV bars (per symbol, 500 bars)
       │
       ▼
compute_ml_features(df, spy_df)
       │
       ├──► Price Action (15 features)
       ├──► Moving Averages (8 features)
       ├──► Volatility (11 features)
       ├──► Volume (8 features)
       ├──► Momentum (8 features)
       ├──► Trend (4 features)
       ├──► Cross-Asset (8 features, requires SPY)
       └──► Regime (6 features)
       │
       ▼
68 features per symbol per bar
       │
       ▼
Feature Selection (EvolutionEngine)
  • Drop features with evolved weight < 0.20
  • Keep minimum 15 features (safety)
       │
       ▼
Active feature matrix → ML Signal Generator
```

---

## 9. Implementation Phases & Milestones

### Phase 1: Foundation Hardening (Gap Fixes)

**Goal:** Fix all identified gaps in existing modules. No new features.

| Step | Task | Files | Est. Effort |
|------|------|-------|-------------|
| 1.1 | Promote `evolved_params` from `extra_counters` to dedicated `evolved_params.json` file | `brain_persistence.py` | 2h |
| 1.2 | Persist governance state (`_frozen`, `_trading_halted`, `_disabled`, `_change_count`) | `brain_persistence.py`, `governance.py` | 2h |
| 1.3 | Persist regime detector state (`_history`, `_smoothed_probs`) | `brain_persistence.py`, `regime.py` | 2h |
| 1.4 | Replace inline `detect_regime()` in backtest with full `RegimeDetector` module | `run_breakout_organism.py` | 3h |
| 1.5 | Fix `_close_all_positions()` to create `TradeRecord` for unclosed positions | `run_breakout_organism.py` | 1h |
| 1.6 | Add brain quality gates (NaN check, weight normalization, feature consistency) | `brain_persistence.py` | 2h |
| 1.7 | Remove duplicate `print_brain_status()` method | `brain_persistence.py` | 15m |
| 1.8 | Fix `training.py` `_fetch_price_data()` — pass credentials to `AlpacaClient` | `training.py` | 1h |

**Acceptance:** All existing tests pass + new unit tests for each fix.

### Phase 2: Live Organism Engine

**Goal:** Create the unified live trading engine that bridges backtest and production.

| Step | Task | Files | Est. Effort |
|------|------|-------|-------------|
| 2.1 | Create `OrganismLiveEngine` class combining all organism modules | `backend/organism/live_engine.py` (NEW) | 8h |
| 2.2 | Implement `async live_tick()` — one bar of the organism loop | `live_engine.py` | 4h |
| 2.3 | Wire `OrganismLiveEngine` into `MultiStrategyLiveScheduler` | `multi_strategy_live_scheduler.py` | 3h |
| 2.4 | Map Alpaca fills to `TradeRecord` for continuous learner feedback | `live_engine.py` | 2h |
| 2.5 | Implement live position → pyramid state reconstruction on startup | `live_engine.py` | 3h |
| 2.6 | Add walk-forward gate before brain save in backtest mode | `run_breakout_organism.py` | 2h |
| 2.7 | Add multi-run regression test: brain_N+1.sharpe ≥ brain_N.sharpe × 0.95 | Test file | 3h |
| 2.8 | Integration test: organism live tick with paper account mock | Test file | 4h |

**Acceptance:** Paper trading produces real Alpaca fills that feed the learning loop.

### Phase 3: Production Readiness

**Goal:** Harden for 24/7 unattended operation.

| Step | Task | Files | Est. Effort |
|------|------|-------|-------------|
| 3.1 | Add brain file locking (`fcntl`/`msvcrt`) for concurrent write safety | `brain_persistence.py` | 2h |
| 3.2 | Implement trade history CSVcompression + rotation (keep 10k most recent, archive rest) | `brain_persistence.py` | 3h |
| 3.3 | Wire `VersionedFeatureStore` into live engine for feature versioning | `live_engine.py`, `feature_store.py` | 3h |
| 3.4 | Expose organism status via WebSocket (real-time evolution dashboard) | `routes.py`, frontend | 6h |
| 3.5 | Add Prometheus metrics: `organism_evolution_generation`, `organism_direction_accuracy`, `organism_sharpe_per_epoch` | `live_engine.py` | 2h |
| 3.6 | Implement brain migration path for format version bumps | `brain_persistence.py` | 3h |
| 3.7 | Add error backoff + jitter to nightly scheduler | `nightly_scheduler.py` | 1h |
| 3.8 | Breakout indicator periods tunable via evolution | `breakout_scanner.py`, `self_evolution.py` | 4h |

**Acceptance:** System runs unattended for 7 days on paper account without intervention.

### Phase 4: Advanced Intelligence

**Goal:** Push the organism's adaptive capabilities beyond parameter tuning.

| Step | Task | Est. Effort |
|------|------|-------------|
| 4.1 | Dynamic universe selection — organism adds/removes symbols based on fitness | 6h |
| 4.2 | Multi-timeframe features — combine 1D + 1H + 15M signals | 8h |
| 4.3 | Cross-asset regime conditioning — use sector ETFs for better regime detection | 4h |
| 4.4 | Ensemble model expansion — add LightGBM + Random Forest to ensemble | 6h |
| 4.5 | Short-side resurrection — re-enable shorts when organism identifies profitable short regimes | 4h |
| 4.6 | Automated hyperparameter evolution — tune XGBoost `n_estimators`, `max_depth`, `learning_rate` | 6h |
| 4.7 | Inter-run transfer learning — use accumulated trade data to warm-start new market conditions | 8h |

---

## 10. Test Plan & Acceptance Criteria

### 10.1 Test Categories

| Category | Marker | Count Target | Purpose |
|----------|--------|-------------|---------|
| `unit` | `@pytest.mark.unit` | 50+ per module | Isolated function correctness |
| `integration` | `@pytest.mark.integration` | 20+ | Cross-module interaction |
| `live` | `@pytest.mark.live` | 10+ | Real Alpaca API (paper) |
| `evolution` | `@pytest.mark.evolution` | 15+ | Multi-epoch learning verification |
| `regression` | `@pytest.mark.regression` | 5+ | Brain-over-brain improvement |

### 10.2 Unit Tests (Per Module)

**self_evolution.py (14 existing + 6 new):**
- [x] `EvolvedParams` defaults are valid (weights sum to 1.0)
- [x] Serialisation roundtrip (to_dict → from_dict)
- [x] Feature selection threshold respects weight cutoff
- [x] Feature selection safety floor (never below 15)
- [x] `EvolutionEngine.evolve()` changes params from trade data
- [x] Skips evolution with insufficient trades
- [x] Symbol fitness updates correctly
- [x] Regime scales adapt from PnL
- [x] Multiple evolution steps accumulate
- [x] Evolution is gradual (max 20% shift)
- [x] `apply_evolved_params` pushes to alpha scanner
- [x] `apply_evolved_params` pushes to exit engine
- [x] `apply_evolved_params` pushes to signal generator
- [x] `apply_evolved_params` pushes to kelly sizer
- [ ] Exit params widen stops when stop_loss_rate > 45%
- [ ] Exit params tighten stops when stop_loss_rate < 15%
- [ ] Direction threshold raises when high-conf WR < 45%
- [ ] Direction threshold lowers when high-conf WR > 65%
- [ ] Breakout weights boost when breakout trades outperform
- [ ] Weight normalization preserves sum = 1.0 after every evolution step

**brain_persistence.py (existing + 8 new):**
- [ ] Save and load full brain roundtrip
- [ ] Atomic write survives interruption (brain file intact)
- [ ] Backup rotation keeps exactly 5
- [ ] Quality gate rejects NaN in evolved params
- [ ] Quality gate rejects weight sum != 1.0
- [ ] Quality gate rejects feature column mismatch
- [ ] Trade history appends across runs (never shrinks)
- [ ] Equity curve concatenates across runs

**ml_signal.py (existing + 4 new):**
- [ ] Predict uses dynamic thresholds (not hardcoded 0.55)
- [ ] Feature selection drops low-weight features
- [ ] Feature selection enforces minimum 15 features
- [ ] Model roundtrip: train → save → load → predict gives same output

**continuous_learner.py (existing + 3 new):**
- [ ] PnL-weighted walk-forward gate accepts improving model
- [ ] Walk-forward gate rejects degrading model
- [ ] Old model restored on rejection (rollback)

### 10.3 Integration Tests (Cross-Module)

| Test | Description | Real Data? |
|------|-------------|-----------|
| **IT-01** | Full epoch: load data → compute features → predict → scan → size → exit → retrain → evolve | Historical (Alpaca) |
| **IT-02** | Brain persist roundtrip: run 1 epoch → save → load → verify all state | Historical |
| **IT-03** | Multi-epoch convergence: 5 epochs, verify Sharpe trend is non-decreasing | Historical |
| **IT-04** | Evolution + retrain interaction: evolve params → retrain model → verify model uses evolved thresholds | Historical |
| **IT-05** | Regime-conditioned sizing: verify Kelly output changes with regime | Synthetic (but real feature structure) |

### 10.4 Live Tests (Real Alpaca Paper Account)

**Prerequisites:**
- Valid `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` env vars
- Paper account with $100,000+ equity
- Market hours (or historical data fallback)

| Test | Description | Duration |
|------|-------------|----------|
| **LT-01** | Data fetch: download 500 bars for 50 symbols, verify all features compute | ~2 min |
| **LT-02** | Price query: `get_current_price()` for 10 symbols, verify non-zero | ~10s |
| **LT-03** | Paper order: submit + cancel limit order, verify lifecycle | ~30s |
| **LT-04** | Paper round-trip: buy 1 share SPY → sell 1 share SPY → verify PnL tracking | ~60s |
| **LT-05** | Full live tick: run one `live_tick()` cycle on paper, verify no errors | ~5 min |
| **LT-06** | Overnight paper: run organism in paper-execute mode for 24h, verify brain save | 24h |
| **LT-07** | Multi-day paper: 5 consecutive trading days, verify knowledge accumulates | 5 days |

### 10.5 Regression Tests (Brain-Over-Brain)

| Test | Acceptance Criteria |
|------|-------------------|
| **RT-01** | `brain_run_N+1.sharpe >= brain_run_N.sharpe * 0.95` (allow 5% variance) |
| **RT-02** | `brain_run_N+1.total_trades >= brain_run_N.total_trades` (monotonic accumulation) |
| **RT-03** | `brain_run_N+1.evolution_generation > brain_run_N.evolution_generation` (strictly increasing) |
| **RT-04** | No evolved param is NaN or Inf after any run |
| **RT-05** | Alpha weights sum to 1.0 ± 0.01 after every evolution step |

### 10.6 Formal Feature Acceptance Checklist

A complete "pass" requires ALL of the following:

```
□ All unit tests pass (pytest -m unit)
□ All integration tests pass (pytest -m integration)
□ Backtest v3 with evolution produces positive return over 5 epochs
□ Brain persists and loads correctly (verify with RT-01 through RT-05)
□ 3 consecutive backtest runs show non-decreasing Sharpe (RT-01)
□ Paper account live test runs for 24h without error (LT-06)
□ Evolution log shows >0 parameter changes per epoch
□ Direction accuracy ≥ 55% (above random)
□ No hardcoded mock data anywhere in the pipeline
□ All data sourced from Alpaca API
□ Governance kill switch tested and verified (freeze + halt)
□ Drawdown kill switch tested (trigger at configured limit)
```

---

## 11. Risk Safeguards & Governance

### 11.1 Defense-in-Depth Layers

```
Layer 1: EVOLUTION SAFETY
  • EMA smoothing (α=0.30) prevents radical parameter shifts
  • Max 20% change per epoch on any parameter
  • Walk-forward gate blocks degrading ML models
  • Minimum 8 trades required before any adaptation

Layer 2: POSITION SAFETY
  • Max 12% equity per position (Kelly capped)
  • Max 8 concurrent positions
  • Half-Kelly (never full-Kelly)
  • Anti-pyramid cuts at -0.7R and -1.0R

Layer 3: GOVERNANCE SAFETY
  • Global freeze switch (ORGANISM_FREEZE_ADAPTATION)
  • Global trading halt (ORGANISM_HALT_TRADING)
  • Per-strategy disable switch
  • Daily change budget (100 changes/day)
  • Drawdown kill switch at 5% (adaptive cooldown)

Layer 4: EXECUTION SAFETY
  • Circuit breaker (5% daily P&L loss → halt)
  • Three execution modes (shadow → dry_run → execute)
  • Idempotent orders (per-symbol locks)
  • Outbox pattern (DB → broker, survives crashes)
  • Slippage model (5 bps) baked into backtest

Layer 5: PROMOTION SAFETY (Live Only)
  • Shadow → Paper → Canary (5% capital) → Ramp (15%) → Active
  • Minimum duration per stage (1h → 24h → 24h → 48h)
  • Automatic rollback on: drawdown > 8%, slippage > 50bps, turnover > 10×
  • Last-known-good policy always available for instant rollback
```

### 11.2 Kill Switch Protocol

**Automatic Triggers:**

| Condition | Action | Recovery |
|-----------|--------|----------|
| Portfolio drawdown > 5% | Halt all trading for adaptive cooldown | Auto-resume after cooldown |
| Daily P&L loss > 5% | Circuit breaker opens | Auto-close after recovery period |
| 3 consecutive losing epochs | Freeze evolution | Manual review + unfreeze |
| Model accuracy < 45% | Skip model promotion, keep old model | Retrain on next trigger |
| Brain load failure | Start fresh (no persistence) | Auto — first run builds new brain |

**Manual Controls (via API or env vars):**
- `POST /api/organism/freeze` — halt all parameter adaptation
- `POST /api/organism/halt` — stop all order execution
- `POST /api/organism/disable/{strategy}` — disable specific strategy
- `POST /api/organism/status` — query all governance state
- Set `ORGANISM_HALT_TRADING=1` — emergency stop (no API needed)

### 11.3 Maximum Loss Bounds

| Bound | Value | Mechanism |
|-------|-------|-----------|
| **Per-trade max loss** | -1.0R (ATR-based stop) | Adaptive Exit Engine |
| **Per-position max loss** | -12% of equity | Kelly cap + stop loss |
| **Daily max loss** | -5% of equity | Circuit breaker |
| **Portfolio max drawdown** | -5% from peak | Governance kill switch |
| **Worst-case total loss** | ~-20% of equity | All safeguards fail simultaneously (theoretical) |

---

## 12. Monitoring & Observability

### 12.1 Key Metrics to Track

**Performance (per epoch and rolling):**
- `organism_total_return` — cumulative return since first run
- `organism_sharpe_ratio` — rolling 60-bar Sharpe
- `organism_max_drawdown` — peak-to-trough drawdown
- `organism_win_rate` — trades with PnL > 0 / total trades
- `organism_direction_accuracy` — predicted direction matches actual
- `organism_avg_pnl_per_trade` — mean PnL across all trades

**Evolution (per epoch):**
- `organism_evolution_generation` — total evolution steps completed
- `organism_params_changed` — count of parameters evolved this epoch
- `organism_alpha_weight_ml` — current ML signal weight
- `organism_stop_atr_scale` — current stop loss scale
- `organism_direction_threshold_buy` — current ML confidence threshold
- `organism_active_features` — count of features passing selection
- `organism_symbol_fitness_max` — highest symbol fitness score
- `organism_symbol_fitness_min` — lowest symbol fitness score

**Health (continuous):**
- `organism_brain_generation` — current brain generation (should only increase)
- `organism_brain_save_success` — counter of successful brain saves
- `organism_brain_save_failure` — counter of failed brain saves
- `organism_governance_frozen` — 1 if frozen, 0 if active
- `organism_governance_trading_halted` — 1 if halted
- `organism_data_freshness_seconds` — age of latest bar data
- `organism_feature_nan_rate` — fraction of NaN in latest features

### 12.2 Alerting Rules

| Alert | Condition | Severity |
|-------|-----------|----------|
| **OrganismDrawdownKill** | `organism_max_drawdown > 0.05` | 🔴 Critical |
| **OrganismCircuitBreakerOpen** | Circuit breaker enters OPEN state | 🔴 Critical |
| **OrganismBrainSaveFailed** | `organism_brain_save_failure` incremented | 🟡 Warning |
| **OrganismNoTrades** | 0 trades in last 5 epochs | 🟡 Warning |
| **OrganismDirectionAccuracyLow** | `organism_direction_accuracy < 0.50` for 3 epochs | 🟡 Warning |
| **OrganismSharpeNegative** | `organism_sharpe_ratio < 0` for 2 epochs | 🟡 Warning |
| **OrganismStaleData** | `organism_data_freshness_seconds > 259200` (3 days) | 🟡 Warning |
| **OrganismFeatureNaN** | `organism_feature_nan_rate > 0.10` | 🟠 Info |

---

## 13. Open Issues & Technical Debt

### 13.1 Known Technical Debt

| ID | Issue | Impact | Proposed Fix |
|----|-------|--------|-------------|
| TD-01 | `breakout_scanner._rolling_std()` uses Python loop — O(n×period) | Performance | Replace with numpy cumsum approach |
| TD-02 | `brain_persistence` `_json_serializer` loses `-inf`/`+inf` information | Data loss | Map to sentinel strings `-Infinity`/`Infinity`, parse back on load |
| TD-03 | `promotion.py` no auto-retry of rolled-back candidate | Missed opportunities | Add retry-with-adjustment logic |
| TD-04 | `test_mode` handling scattered across AlpacaClient with try/except | Code quality | Introduce proper mock interface |
| TD-05 | `print_brain_status()` defined twice in `brain_persistence.py` | Bug | Remove duplicate |
| TD-06 | Long-only hardcoded (`LONG_ONLY=True`) | Missing alpha | Phase 4.5 — conditional short re-enablement |
| TD-07 | No pagination in `get_historical_data()` | Silent data truncation | Add pagination for >10k bars |

### 13.2 Research Questions

| ID | Question | Impact |
|----|----------|--------|
| RQ-01 | Does the organism converge or oscillate after 100+ generations? | Model validity |
| RQ-02 | What is the optimal α (EMA smoothing) — is 0.30 too aggressive or too conservative? | Evolution speed |
| RQ-03 | Should feature weights evolve faster than signal weights? | Parameter hierarchy |
| RQ-04 | Can we detect and adapt to *regime transitions* (not just static regimes)? | Regime edge |
| RQ-05 | Is the 200-bar training window optimal, or should it expand with accumulated data? | Model quality |
| RQ-06 | Would a separate model per regime outperform a single model with regime features? | Architecture |

### 13.3 Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-02-14 | Use EMA over gradient descent for parameter evolution | Stability, serializability, interpretability (§5.3) |
| 2026-02-14 | Keep evolved params in `extra_counters` (temporary) | Ship fast, promote to own file in Phase 1 |
| 2026-02-14 | PnL-weighted walk-forward gate replaces accuracy-only gate | Win-rate + direction accuracy more aligned with profits than raw accuracy |
| 2026-02-14 | Max 20% shift per epoch | Prevents catastrophic parameter oscillation |
| 2026-02-14 | Minimum 15 features after selection | Prevents XGBoost degenerate train on too few features |
| 2026-02-14 | Half-Kelly (never full) | Full Kelly has optimal growth but unacceptable variance |
| 2026-02-14 | Long-only for now | Shorts were net negative in v2 backtesting |

---

## Appendix A: File Map

```
backend/organism/
├── __init__.py              # Module docstring
├── adaptive_exits.py        # Module 6 — ATR exit engine
├── alpha_scanner.py         # Module 3 — Composite alpha scoring
├── attribution.py           # Phase 1 — Fill-based PnL attribution
├── brain_persistence.py     # Module 9 — Cross-run memory
├── breakout_scanner.py      # Module 4 — 6-detector breakout
├── continuous_learner.py    # Module 7 — Fast-brain retrain loop
├── feature_store.py         # Phase 2 — Versioned feature store
├── governance.py            # Module 11 — Kill switches & controls
├── kelly_sizer.py           # Module 5 — Half-Kelly + regime scaling
├── live_engine.py           # ★ PLANNED (Phase 2) — Unified live engine
├── ml_features.py           # Module 1 — 68-feature engine
├── ml_signal.py             # Module 2 — XGBoost ensemble
├── nightly_scheduler.py     # Background slow-brain loop
├── promotion.py             # Phase 5 — Shadow→production pipeline
├── pyramider.py             # Module 10 — 3-layer momentum adds
├── regime.py                # Module 12 — Multi-signal regime detector
├── routes.py                # API routes for organism status
├── runner.py                # OrganismRunner (live tick coordinator)
├── self_evolution.py        # Module 8 — Meta-learning engine (7 adapters)
├── training.py              # Phase 4 — Nightly training orchestrator
└── walk_forward.py          # Phase 3 — Walk-forward evaluation

scripts/
├── run_breakout_organism.py     # v3 backtest master script (1594 lines)
├── run_organism_backtest.py     # Multi-strategy backtest with organism
├── run_organism_self_improving.py # Self-improving organism runner
└── run_hft_organism.py          # HFT variant

tests/
├── test_self_evolution.py       # 14 tests for evolution engine
└── test_*.py                    # 500+ tests across all modules
```

## Appendix B: Quick-Start Commands

```bash
# ── Backtest (historical data, simulated fills) ────────────────
python scripts/run_breakout_organism.py --epochs 5

# ── Backtest with brain (continue learning from previous run) ──
python scripts/run_breakout_organism.py --epochs 5
# (brain auto-loads from ./brain/ if exists)

# ── Fresh start (ignore existing brain) ────────────────────────
python scripts/run_breakout_organism.py --epochs 5 --fresh

# ── Run tests ──────────────────────────────────────────────────
python -m pytest tests/ -m unit -q --tb=short
python -m pytest tests/test_self_evolution.py -v

# ── Start live server (paper, shadow mode) ─────────────────────
ORGANISM_ENABLED=1 \
ORGANISM_LIVE_ENABLED=1 \
TRADING_EXECUTION_MODE=shadow \
ALPACA_PAPER=true \
python main.py

# ── Check organism status ──────────────────────────────────────
curl http://localhost:8000/api/organism/status
```

---

*This blueprint is the single source of truth for the Evolving Trading Organism. All implementation work should reference this document. Update this document as decisions change.*
