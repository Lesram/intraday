# SELF-LEARNING LIVING ORGANISM — COMPLETE BLUEPRINT

> **Goal:** Build the most aggressive, highest-return self-learning trading algorithm
> that scans for alpha, trades, learns from results, retrains its ML models, and
> self-corrects every single cycle — surpassing institutional hedge fund standards.

---

## 1. ARCHITECTURE OVERVIEW

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    SELF-LEARNING ORGANISM LOOP                          │
│                                                                         │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────────┐    │
│   │  SCAN    │───▶│ PREDICT  │───▶│  TRADE   │───▶│  ATTRIBUTE   │    │
│   │  Alpha   │    │  ML Sig  │    │  Execute │    │  Fill P&L    │    │
│   └──────────┘    └──────────┘    └──────────┘    └──────┬───────┘    │
│        ▲                                                  │            │
│        │          ┌──────────┐    ┌──────────┐           │            │
│        └──────────│ PROMOTE  │◀───│ RETRAIN  │◀──────────┘            │
│                   │ or REJECT│    │ ML Models│                        │
│                   └──────────┘    └──────────┘                        │
│                                                                         │
│   FAST BRAIN (per bar):  Living Policy weight adaptation               │
│   SLOW BRAIN (per epoch): Full ML retrain + walk-forward gates         │
│   IMMUNE SYSTEM: Governance kill switches + drawdown protection        │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. WHAT EXISTS vs WHAT'S MISSING

### ✅ EXISTS (leverage these)
| Component | Location | Status |
|---|---|---|
| OrganismRunner | `backend/organism/runner.py` | ✅ Wired |
| GovernanceController | `backend/organism/governance.py` | ✅ Working |
| RegimeDetector | `backend/organism/regime.py` | ✅ Working |
| DriftDetector | `backend/organism/regime.py` | ✅ Working |
| TrainingOrchestrator | `backend/organism/training.py` | ✅ Working |
| WalkForwardEvaluator | `backend/organism/walk_forward.py` | ✅ Working |
| AttributionService | `backend/organism/attribution.py` | ✅ Working |
| PromotionController | `backend/organism/promotion.py` | ✅ Working |
| LivingPolicyEngine | `backend/strategies/living_policy.py` | ✅ Working |
| FeatureEngineer | `backend/features/feature_engineering.py` | ✅ 50+ features |
| XGBoost/LSTM/RF Models | `backend/models/ensemble_model.py` | ✅ Defined |
| Advanced Strategies | `backend/strategies/advanced_strategies.py` | ✅ 8 strategies |
| BreakoutScanner | `backend/services/auto_breakout_scanner.py` | ✅ Exists |
| SlippageModel | `backend/services/slippage_model.py` | ✅ Calibrated |
| Kelly Criterion | `backend/risk/risk_manager.py` | ✅ RiskMathUtils |
| AdvancedRiskManager | `backend/risk/advanced_risk_manager.py` | ✅ VaR, DD |
| BlackSwanProtection | `backend/risk/black_swan_protection.py` | ✅ Circuit breakers |
| AlpacaClient | `backend/data/alpaca_client.py` | ✅ Paper+Live |
| SentimentAnalyzer | `backend/data/social_sentiment.py` | ✅ FinBERT |

### ❌ MISSING (build these)
| What | Why It Matters |
|---|---|
| **ML Signal Generator** | No ML model is actually TRAINED on features and used for signal generation in the organism loop |
| **Continuous Retraining Engine** | Models are never retrained on their own trading results; only weights change |
| **Alpha Scanner Integration** | Breakout scanner exists but is not wired into the organism loop |
| **Kelly Position Sizing** | `kelly_fraction()` exists but isn't used in any trading logic |
| **Regime-Conditioned ML** | Different models per regime, not just different weights |
| **Feature Importance Tracker** | No tracking of which features drive alpha over time |
| **Multi-Timeframe Features** | Only daily features; no intraday momentum/volume features |
| **Cross-Asset Signals** | No relative strength, sector rotation, or correlation signals |
| **Adaptive Stop/Take-Profit** | Fixed percentages instead of ATR-based or model-predicted exits |
| **Full Integration Script** | All pieces exist in isolation — no single engine runs everything |

---

## 3. IMPLEMENTATION PLAN

### Module 1: ML Feature Engine (`backend/organism/ml_features.py`)
**70+ features per symbol per bar — the foundation of everything.**

```python
FEATURES = {
    # Price Action (15)
    "ret_1d", "ret_2d", "ret_3d", "ret_5d", "ret_10d", "ret_20d",
    "log_ret_1d", "momentum_acceleration",
    "close_to_high_ratio", "close_to_low_ratio", "range_pct",
    "gap_pct", "body_ratio", "upper_shadow", "lower_shadow",

    # Trend (10)
    "sma_5", "sma_10", "sma_20", "sma_50",
    "ema_12", "ema_26", "macd", "macd_signal", "macd_hist",
    "adx_14",

    # Mean Reversion (8)
    "rsi_14", "rsi_5",
    "bb_position", "bb_width",
    "z_score_20", "z_score_50",
    "stoch_k", "stoch_d",

    # Volatility (10)
    "atr_14", "atr_ratio_to_price",
    "realized_vol_5", "realized_vol_20",
    "vol_ratio_5_20",
    "parkinson_vol", "garman_klass_vol",
    "vol_regime",  # 0=low, 1=normal, 2=high
    "bollinger_squeeze",  # BB_width < threshold
    "vol_expansion_signal",

    # Volume (8)
    "volume_sma_ratio", "obv_slope",
    "volume_momentum_5", "volume_momentum_10",
    "mfi_14",
    "vwap_distance",
    "volume_breakout",  # volume > 2x avg
    "price_volume_divergence",

    # Cross-Sectional (5)
    "relative_strength_vs_spy",
    "sector_momentum",
    "correlation_to_market_20d",
    "beta_20d",
    "idiosyncratic_vol",

    # Microstructure (5)
    "price_impact_estimate",
    "spread_proxy",
    "tick_direction_ratio",
    "close_location_value",  # (C-L)/(H-L)
    "true_range_pct",

    # Temporal (5)
    "day_of_week", "month",
    "days_since_high_52w", "days_since_low_52w",
    "earnings_proximity",  # crude proxy

    # Regime (4)
    "trend_strength",  # ADX-based
    "choppiness_index",
    "hurst_exponent_approx",
    "regime_label_encoded",
}
```

### Module 2: ML Signal Generator (`backend/organism/ml_signal.py`)
**XGBoost ensemble that predicts next-day direction + magnitude.**

- Train on 250-day rolling window (no lookahead)
- Target: next-day return (regression) + direction (classification)
- Walk-forward: retrain every epoch
- Feature importance tracking: drop features with zero importance
- Ensemble: 3 models with different hyperparameters → weighted average
- Confidence calibration: Platt scaling on validation set

### Module 3: Alpha Scanner (`backend/organism/alpha_scanner.py`)
**Actively scans for the highest-conviction trades.**

- Pre-filter: universe of 50+ liquid stocks (configurable)
- Score each symbol on 5 dimensions:
  1. ML model conviction (predicted return magnitude)
  2. Volume breakout strength (volume / avg_volume)
  3. Squeeze-to-expansion transition probability
  4. Relative strength rank (top quintile)
  5. Regime alignment (signal matches regime)
- Output: ranked list of top-N candidates with composite alpha score
- Update every bar (in backtest) or every tick (live)

### Module 4: Kelly Position Sizer (`backend/organism/kelly_sizer.py`)
**Optimal position sizing for maximum geometric growth.**

- Half-Kelly for safety (full Kelly is too aggressive)
- Input: model win probability, win/loss ratio, current drawdown
- Drawdown scaling: reduce size as DD increases (convex)
- Volatility target: scale position by inverse realized vol
- Concentration limits: max 20% per position, max 5 positions
- Dynamic: recalculate every bar based on rolling performance

### Module 5: Adaptive Exits (`backend/organism/adaptive_exits.py`)
**ML-informed stop-loss and take-profit.**

- Stop-loss: 2× ATR (adaptive to volatility regime)
- Take-profit: Predicted return × confidence × multiplier
- Trailing stop: activate after 1× risk, trail at 1.5× ATR
- Time-based exit: if position age > 10 days and ΔP/L < 0 → exit
- Regime exit: if regime changes adversely → tighten stop to 1× ATR

### Module 6: Continuous Learning Engine (`backend/organism/continuous_learner.py`)
**The actual self-improvement loop.**

```
EACH EPOCH:
  1. Collect all trades from this epoch
  2. Compute fill-based attribution per strategy source
  3. Compute reward signals [−1, +1] per source
  4. Retrain ML models on expanded training window
  5. Feature importance analysis → prune dead features
  6. Walk-forward evaluate new model vs current model
  7. ACCEPTANCE GATES:
     - New model Sharpe ≥ 0.3
     - New model beats current by ≥ 5%
     - Max drawdown ≤ 15%
     - Min 5 trades in eval window
  8. If PASS → promote new model (new generation!)
  9. If FAIL → keep current model, log rejection reason
  10. Drift check → if PSI > 0.25, force retrain next epoch
```

### Module 7: Self-Improving Organism Engine (`scripts/run_hft_organism.py`)
**The master controller that ties EVERYTHING together.**

```
INITIALIZATION:
  1. Fetch 1000 days of data for universe
  2. Compute 70+ features per symbol per bar
  3. Train initial ML models on first 250 days
  4. Initialize: weights=uniform, generation=1

EPOCH LOOP (60 trading days each):
  FOR EACH BAR IN EPOCH:
    1. SCAN: Alpha scanner ranks all symbols
    2. PREDICT: ML model generates signals for top candidates
    3. SIZE: Kelly criterion determines position sizes
    4. EXECUTE: Enter/exit with adaptive stops
    5. MONITOR: Governance checks (drawdown kill, circuit breaker)
    6. ADAPT: Living Policy updates weights (fast brain)

  END OF EPOCH:
    7. ATTRIBUTE: Fill-based P&L per strategy
    8. RETRAIN: ML models on expanded window
    9. EVALUATE: Walk-forward acceptance gates
    10. PROMOTE: Adopt new model or keep current
    11. DRIFT: Check feature distribution stability
    12. REPORT: Log generation performance metrics

FINAL REPORT:
  - Total return, Sharpe, Sortino, Calmar, Max DD
  - Per-generation comparison (did it improve?)
  - Weight evolution across generations
  - Feature importance evolution
  - Alpha scanner hit rate
  - Kelly sizing efficiency
```

---

## 4. ACCEPTANCE CRITERIA

| Metric | Minimum Target | Stretch Goal |
|---|---|---|
| Total Return | > 0% (beat the old -6.6%) | > 50% |
| Sharpe Ratio | > 0.5 | > 1.5 |
| Max Drawdown | < 20% | < 10% |
| Generations | ≥ 2 (prove self-improvement) | ≥ 5 |
| Improvement | Gen N+1 Sharpe > Gen N Sharpe | Monotonic |
| Win Rate | > 45% | > 55% |
| Trades | > 100 | > 300 |
| Alpha vs Hold | Sharpe > buy-and-hold Sharpe | 2× buy-and-hold |

---

## 5. NON-NEGOTIABLE ENGINEERING STANDARDS

1. **No lookahead bias** — features use only past data; models trained on [0,T], predict T+1
2. **Walk-forward validation** — every model change must pass OOS acceptance gates
3. **Fill-based attribution** — P&L computed from actual trade fills, not theoretical
4. **Slippage modeling** — 5 bps per trade minimum
5. **Transaction costs** — commission included in all returns
6. **Governance protection** — drawdown kill switch, daily change budget, circuit breakers
7. **No overfitting** — rolling window training, feature pruning, regularization
8. **Reproducibility** — random seeds set, results deterministic
9. **Full reporting** — CSV exports, per-epoch metrics, weight evolution, feature importance

---

## 6. FILE MANIFEST

| File | Purpose |
|---|---|
| `backend/organism/ml_features.py` | 70+ feature computation engine |
| `backend/organism/ml_signal.py` | XGBoost ensemble signal generator |
| `backend/organism/alpha_scanner.py` | Alpha scanning & symbol ranking |
| `backend/organism/kelly_sizer.py` | Kelly criterion position sizing |
| `backend/organism/adaptive_exits.py` | ATR-based adaptive stops & take-profits |
| `backend/organism/continuous_learner.py` | ML retraining & walk-forward gates |
| `scripts/run_hft_organism.py` | Master engine — ties everything together |

---

## 7. EXECUTION ORDER

1. Build `ml_features.py` — compute 70+ features correctly
2. Build `ml_signal.py` — train XGBoost models, predict signals
3. Build `alpha_scanner.py` — rank symbols by alpha potential
4. Build `kelly_sizer.py` — optimal position sizing
5. Build `adaptive_exits.py` — intelligent stop/take-profit
6. Build `continuous_learner.py` — self-improvement loop
7. Build `scripts/run_hft_organism.py` — integration engine
8. Run the full backtest
9. Analyze results, iterate if needed
10. Run existing test suite to verify no regressions
