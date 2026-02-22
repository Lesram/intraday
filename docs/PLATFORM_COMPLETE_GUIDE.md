# Algorithmic Trading Platform — Complete Guide

> **Version:** 1.0 — February 17, 2026  
> **Platform:** Institutional-Grade Algorithmic Trading Platform with Living Organism AI  
> **Purpose:** Comprehensive reference for learning, operating, and maintaining the platform

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Platform Architecture Overview](#2-platform-architecture-overview)
3. [The Living Organism — How the AI Thinks and Trades](#3-the-living-organism--how-the-ai-thinks-and-trades)
4. [Trading Strategies — The Signal Generators](#4-trading-strategies--the-signal-generators)
5. [Machine Learning Pipeline — The Prediction Engine](#5-machine-learning-pipeline--the-prediction-engine)
6. [Order Pipeline — From Signal to Execution](#6-order-pipeline--from-signal-to-execution)
7. [Risk Management — The Safety Net](#7-risk-management--the-safety-net)
8. [Frontend Application — The Control Center](#8-frontend-application--the-control-center)
9. [Backend API — Every Endpoint Documented](#9-backend-api--every-endpoint-documented)
10. [Configuration Reference — Every Setting Explained](#10-configuration-reference--every-setting-explained)
11. [Getting Started — Setup and First Run](#11-getting-started--setup-and-first-run)
12. [Day-to-Day Operations Guide](#12-day-to-day-operations-guide)
13. [Maintenance Manual](#13-maintenance-manual)
14. [Troubleshooting Guide](#14-troubleshooting-guide)
15. [Architecture Deep Dives](#15-architecture-deep-dives)
16. [Glossary](#16-glossary)

---

## 1. Executive Summary

### What This Platform Does

This is a **self-evolving algorithmic trading platform** that trades US equities through the Alpaca brokerage. It combines traditional quantitative strategies (mean reversion, momentum, statistical arbitrage) with a machine learning system that continuously learns and adapts from its own trading outcomes.

The platform's core innovation is the **Living Organism** — an AI system that:
- Observes markets every 60 seconds via automated tick cycles
- Predicts price direction and magnitude using XGBoost ensemble ML across 68 engineered features
- Makes entry, exit, and position sizing decisions using regime-aware adaptive rules
- Evolves its own parameters after every trading epoch based on what worked and what didn't
- Governs itself with kill switches, drawdown limits, and promotion gates to prevent runaway losses

### What You Can Do With It

| Capability | Description |
|------------|-------------|
| **Automated Trading** | The organism trades autonomously once a model is promoted, executing entries, exits, and pyramiding based on ML signals |
| **Manual Trading** | Submit buy/sell orders directly through the Trading page with pre-trade risk checks |
| **Strategy Management** | Create, backtest, start, stop, and compare 15+ built-in strategies |
| **Backtesting** | Test any strategy against historical data with detailed performance metrics (Sharpe, Sortino, max drawdown, win rate) |
| **ML Model Training** | Train, evaluate, compare, and deploy machine learning models for signal generation |
| **Portfolio Monitoring** | Real-time portfolio tracking with live equity updates via WebSocket |
| **Risk Monitoring** | 4-layer risk management with live dashboards, kill switches, and emergency stops |
| **Market Scanning** | Real-time market scanner with customizable filters for finding trading opportunities |
| **Observability** | Prometheus metrics, OpenTelemetry tracing, Grafana dashboards for system health |

### Current State

- **Broker:** Alpaca Paper Trading (production-ready for live trading)
- **Trading Universe:** 20 symbols — AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA, AMD, AVGO, CRM, COST, WMT, LLY, XOM, CAT, SPY, QQQ, IWM, XLK, XLE
- **Server:** Python/FastAPI on localhost:8000 with WebSocket (Socket.IO)
- **Frontend:** React 19 / TypeScript on localhost:5173
- **Database:** PostgreSQL + Redis
- **ML Status:** XGBoost models training but not yet promoted (Sharpe ratio below 0.3 threshold — the organism is deliberately conservative about deploying unproven models)

---

## 2. Platform Architecture Overview

### System Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                         USER INTERFACE                                │
│  React 19 + TypeScript + Ant Design 5 + Socket.IO                   │
│  localhost:5173                                                       │
│  ┌──────────┬──────────┬──────────┬──────────┬──────────┬──────────┐ │
│  │Dashboard │ Trading  │Strategies│ Organism │  Risk    │ ML Models│ │
│  │          │          │          │Dashboard │Dashboard │          │ │
│  └────┬─────┴────┬─────┴────┬─────┴────┬─────┴────┬─────┴────┬─────┘ │
└───────┼──────────┼──────────┼──────────┼──────────┼──────────┼───────┘
        │  REST    │  REST    │  REST    │  REST    │  REST    │
        │  + WS    │  + WS    │          │  + WS    │  + WS    │
┌───────┼──────────┼──────────┼──────────┼──────────┼──────────┼───────┐
│       │          │    BACKEND API (FastAPI + Socket.IO)       │       │
│       │          │    localhost:8000                          │       │
│  ┌────▼──────────▼──────────▼──────────▼──────────▼──────────▼────┐  │
│  │                    Middleware Stack                              │  │
│  │  CORS → Rate Limiting → Deduplication → GZip → Metrics        │  │
│  └────┬───────────────────────────────────────────────────────────┘  │
│       │                                                              │
│  ┌────▼───────────────────────────────────────────────────────────┐  │
│  │  Route Layer: /api/v1/*                                        │  │
│  │  Public: /auth, /health, /monitoring                           │  │
│  │  Protected (JWT): /portfolio, /orders, /positions, /risk,      │  │
│  │    /strategies, /models, /organism, /signals, /trades, /admin  │  │
│  └────┬───────────────────────────────────────────────────────────┘  │
│       │                                                              │
│  ┌────▼────────────────────┐  ┌──────────────────────────────────┐  │
│  │  LIVING ORGANISM        │  │  SERVICES LAYER                   │  │
│  │  Scheduler (60s tick)   │  │  OrderService   PortfolioService │  │
│  │  Live Engine            │  │  PositionsService  TradeService   │  │
│  │  Governance Controller  │  │  RiskManager (service)            │  │
│  │  Training Orchestrator  │  │  SignalService                    │  │
│  │  Promotion Manager      │  │  LivingPolicyEngine               │  │
│  │  Self-Evolution Engine  │  │  StrategyEngine                   │  │
│  └────┬────────────────────┘  └──────┬───────────────────────────┘  │
│       │                              │                               │
│  ┌────▼────────────────────┐  ┌──────▼───────────────────────────┐  │
│  │  ML PIPELINE            │  │  RISK MANAGEMENT                  │  │
│  │  MLSignalGenerator      │  │  AsyncRiskManager (pre-trade)    │  │
│  │  FeatureEngineering     │  │  AdvancedRiskManager (portfolio) │  │
│  │  Model Manager/Registry │  │  BlackSwanProtection (tail risk) │  │
│  │  Drift Detection        │  │  Position Limits                  │  │
│  │  Prediction Service     │  │  Circuit Breakers                 │  │
│  └────┬────────────────────┘  └──────┬───────────────────────────┘  │
│       │                              │                               │
│  ┌────▼────────────────────────────────▼─────────────────────────┐  │
│  │  INFRASTRUCTURE                                                │  │
│  │  Database (asyncpg)  │  Redis (Cache/Sessions)  │  Outbox     │  │
│  │  Security (JWT/RBAC) │  Observability (OTEL)    │  WebSocket  │  │
│  └────┬──────────────────┬────────────────────────────┬──────────┘  │
└───────┼──────────────────┼────────────────────────────┼──────────────┘
        │                  │                            │
   ┌────▼─────┐    ┌──────▼──────┐             ┌──────▼──────┐
   │PostgreSQL│    │    Redis    │             │   Alpaca    │
   │  :5432   │    │    :6379    │             │  Broker API │
   └──────────┘    └─────────────┘             └─────────────┘
```

### Technology Stack

| Layer | Technology | Version | Purpose |
|-------|-----------|---------|---------|
| **Backend Framework** | FastAPI | Latest | Async Python web framework |
| **ASGI Server** | Uvicorn | Latest | Production server with hot-reload |
| **ORM** | SQLAlchemy 2.0 | 2.x | Async database operations |
| **Database** | PostgreSQL | 16 | Primary data store |
| **Cache** | Redis | 7 | Caching, sessions, token blacklist |
| **Broker** | Alpaca-py | Latest | Market data + order execution |
| **ML Framework** | XGBoost + scikit-learn | Latest | Gradient boosted trees, ensemble models |
| **WebSocket** | Socket.IO (python-socketio) | Latest | Real-time bidirectional communication |
| **Frontend Framework** | React | 19 | User interface |
| **UI Library** | Ant Design | 5 | Pre-built UI components |
| **Build Tool** | Vite | Latest | Fast development + production builds |
| **State Management** | Zustand | Latest | Lightweight React state |
| **Data Fetching** | React Query | Latest | API caching + synchronization |
| **Language** | TypeScript | Latest | Type-safe frontend code |
| **Observability** | OpenTelemetry + Prometheus + Grafana | Latest | Metrics, tracing, dashboards |
| **Auth** | JWT (python-jose) + bcrypt | Latest | Token-based authentication |
| **Containerization** | Docker + Docker Compose | Latest | Deployment packaging |
| **Orchestration** | Kubernetes (optional) | Latest | Production scaling |

### Key Design Patterns

1. **Application Factory** — `create_app()` produces isolated FastAPI instances, enabling test isolation and multiple configurations
2. **Dependency Injection via `app.state`** — All services (database, risk, ML, websocket) are injected at creation time and accessed via request state
3. **Transactional Outbox** — Orders are written to a database outbox table in the same transaction as the order record, then dispatched to Alpaca asynchronously. This guarantees no lost orders.
4. **Order State Machine** — 16-state finite state machine with explicit valid transitions, ensuring orders follow a consistent lifecycle
5. **Opt-in Background Services** — Expensive subsystems (organism, ML scheduler, streaming) are gated behind environment variable flags
6. **Fail-Closed Security** — Token blacklist checks memory first, rejects insecure JWT defaults in production, enforces bcrypt 72-byte limit

---

## 3. The Living Organism — How the AI Thinks and Trades

### Concept

The Living Organism is the platform's most advanced feature — a **self-evolving trading AI** that learns from its own trading outcomes and adapts its behavior over time. Think of it as a biological organism:

| Biological Analogy | Platform Component | What It Does |
|---|---|---|
| **Heartbeat** | Scheduler (60s tick) | Regular rhythmic cycle of observation and action |
| **Brain** | Brain Persistence | Long-term memory — stores learned parameters, models, trade history |
| **Eyes** | Alpaca Data Client | Observes market data (prices, volume, indicators) |
| **Nervous System** | ML Signal Generator | Processes observations into predictions |
| **Muscles** | Order Pipeline | Executes trading decisions |
| **Immune System** | Governance Controller | Kill switches and drawdown protection |
| **DNA** | Self-Evolution Engine | Adapts 40+ parameters from trade outcomes |
| **Growth Stages** | Promotion Manager | Controlled deployment: shadow → paper → canary → ramp → active |

### The Tick Cycle — What Happens Every 60 Seconds

Every 60 seconds, the organism executes a **12-step tick cycle**:

```
Step 1: GOVERNANCE CHECK
   └─ Is the organism halted? Frozen? In drawdown cooldown?
   └─ If yes → skip this tick entirely

Step 2: FETCH MARKET DATA
   └─ Download latest bars for all 20 symbols from Alpaca
   └─ Timeframe: 1Day bars, lookback: 500 bars

Step 3: DETECT MARKET REGIME (per symbol + cross-asset)
   └─ Classify each symbol: trending_up, trending_down, chop, high_vol, low_vol, stress
   └─ Cross-asset check using sector ETFs (XLK, XLE, XLF, XLV, etc.)
   └─ Output: probability vector per regime, EMA-smoothed (α=0.3)

Step 4: GET CURRENT POSITIONS + PORTFOLIO STATE
   └─ Query Alpaca for live positions and account equity
   └─ Calculate current portfolio drawdown

Step 5: CHECK EXITS on existing positions
   └─ For each open position, run through AdaptiveExitEngine:
      ├─ Hard stop-loss (ATR-based, regime-adaptive)
      ├─ Partial take-profit at 2R (sell 40%, move stop to breakeven)
      ├─ Full take-profit
      ├─ Trailing stop (activates after 2×ATR favorable move)
      ├─ Time-based exit (only if in profit)
      └─ Stress regime tightening (40% stop tightening)

Step 6: CHECK PYRAMIDS on winning positions
   └─ Layer 0: 60% allocation at entry
   └─ Layer 1: +30% at +1.5R (move stops to breakeven)
   └─ Layer 2: +10% at +3.0R (trail at 1.5×ATR)
   └─ Anti-pyramid: cut 50% at -0.7R, cut 100% at -1.0R

Step 7: SCAN FOR NEW ENTRIES
   └─ Breakout scanner (6 pattern detectors)
   └─ ML signal generator (XGBoost direction + magnitude)
   └─ Alpha scanner (combined scoring)
   └─ Output: ranked list of entry candidates

Step 8: SIZE POSITIONS via Kelly Criterion
   └─ Raw Kelly fraction → Half-Kelly → Drawdown scale
   └─ → Volatility target (15% annualized)
   └─ → Regime scale (trending_up: 1.2×, chop: 0.5×, crisis: 0.1×)
   └─ → Confidence clamp [0.3× to 1.5×]
   └─ → Breakout bonus (up to 2.0×)
   └─ Caps: max 8% per position, min $500 (intraday), max 95% portfolio

Step 9: SUBMIT ENTRY ORDERS
   └─ Send to broker client (Alpaca)
   └─ Through the transactional outbox for guaranteed delivery

Step 10: RECONCILE FILLS
   └─ Match broker fills to tracked metadata
   └─ Detect closed positions by diffing broker vs tracked state

Step 11: PERIODIC RETRAIN + EVOLVE (every 60 bars)
   └─ Retrain ML model on latest data
   └─ Compute PnL attribution per strategy/signal source
   └─ Run Self-Evolution Engine (see below)
   └─ Rotate trading universe based on symbol fitness scores

Step 12: SAVE BRAIN STATE (every 10 ticks)
   └─ Walk-forward gate: only save if current Sharpe ≥ 95% of best Sharpe
   └─ Atomic file write with HMAC-signed model files
   └─ Up to 5 backup generations maintained
```

### The Self-Evolution Engine — How Parameters Adapt

Every 60 bars (~1 trading day), the organism runs **10 adaptation steps** that tune its behavior from actual trade outcomes:

| Step | What Adapts | How It Works |
|------|-------------|--------------|
| **1. Signal Weight Adaptation** | How much to trust each signal source (ML, volume, momentum, breakout, regime) | Compares high-confidence vs low-confidence trade win rates. Boosts sources that produce accurate high-confidence signals. |
| **2. Exit Parameter Tuning** | Stop-loss width, take-profit targets, trailing stop distances | If >45% of exits are stop-losses → widen stops 10%. If <15% → tighten 5%. Compares partial TP vs full TP average gains. |
| **3. Regime-Size Scaling** | Position size multipliers per market regime | Positive average P&L in a regime → scale up 8% (cap 1.5×). Negative → scale down 10% (floor 0.05×). |
| **4. Feature Weighting** | ML feature importance overrides | Weights features by XGB importance × direction accuracy. High importance features get boosted; low importance features get suppressed. |
| **5. Symbol Fitness** | Per-symbol trading confidence scores | Combines win rate + average P&L into a sigmoid-mapped fitness score [0.1, 0.95]. Low fitness symbols get smaller positions or dropped from universe. |
| **6. Direction Threshold Calibration** | ML confidence thresholds for buy/sell | If high-confidence trades have <45% win rate → raise buy threshold (require more confidence). If >65% → lower threshold (trade more signals). |
| **7. Breakout Weight Adaptation** | Which breakout patterns to prioritize | Compares P&L from breakout trades (confidence>0.7) vs non-breakout. If breakout outperforms → boost squeeze/volume weights. |
| **8. Breakout Period Tuning** | Indicator lookback periods (Bollinger, ATR, pivot, etc.) | Losing breakout trades with avg hold >15 days → shorten periods. Avg hold <3 days → lengthen. Bounded to safe ranges. |
| **9. Short-Side Control** | Whether to allow short selling | Enable shorts when: WR ≥ 55% AND avg_pnl ≥ $10 over 10+ trades. Disable when: WR < 35%. Auto-resurrection when conditions improve. |
| **10. XGB Hyperparameter Evolution** | ML model complexity (depth, estimators, regularization) | Accuracy ≥ 60% → increase capacity (more trees, deeper). <50% → regularize harder (fewer trees, shallower, more L1/L2). |

**Key constraint:** All changes are EMA-smoothed (α=0.30) with max 20% shift per epoch and minimum 8 trades required. This prevents the organism from overreacting to a few lucky or unlucky trades.

### Governance — The Safety System

The Governance Controller acts as the organism's immune system:

| Control | Trigger | Action | Recovery |
|---------|---------|--------|----------|
| **Drawdown Kill** | Portfolio down 5% from peak | Halts all trading | Auto-recovers after 1-hour cooldown (adaptive: scales 1×–3× based on severity) |
| **Freeze Adaptation** | Manual command | Stops self-evolution but continues trading | Manual unfreeze via API or UI |
| **Halt Trading** | Manual command or extreme drawdown | Stops all trading activity | Manual resume via API or UI |
| **Strategy Disable** | Manual or poor performance | Disables individual strategy signals | Manual re-enable |
| **Policy Versioning** | Every parameter change | SHA-256 hash tracks config versions | Rollback to any previous version |
| **Daily Change Limit** | >100 parameter changes/day | Stops further adaptation | Resets at midnight |

### Model Promotion Pipeline

New ML models aren't deployed immediately. They go through a 5-stage controlled rollout:

```
SHADOW (1 hour minimum)
  │  Model predicts in parallel but doesn't trade
  │  No exposure allowed
  │
  ▼
PAPER EXECUTE (1 day minimum)
  │  20% exposure cap
  │  Paper trades only
  │
  ▼
CANARY (1 day minimum)
  │  5% portfolio exposure cap
  │  Maximum 5 symbols
  │
  ▼
RAMP (2 days minimum)
  │  15% exposure cap
  │  Maximum 20 symbols
  │
  ▼
ACTIVE
     25% exposure cap
     Full 100-symbol universe
```

**Automatic rollback triggers:**
- Drawdown exceeds 8%
- Slippage exceeds 50 basis points
- Turnover exceeds 10× portfolio value
- Regime churn exceeds 50%

### Brain Persistence — What Gets Saved

The organism's entire learned state is saved atomically to disk:

```
organism_brain/
├── manifest.json            # Version, generation, performance metrics
├── ml_classifier.joblib     # XGBoost direction model (HMAC-signed)
├── ml_regressor.joblib      # XGBoost magnitude model (HMAC-signed)
├── ml_state.json            # Feature columns, XGB hyperparameters
├── learning_state.json      # Continuous learner state
├── trade_history.csv        # Last 10,000 trades
├── reference_feats.csv      # Drift detection baseline
├── equity_curve.csv         # Portfolio equity over time
├── epoch_metrics.csv        # Performance per evolution epoch
├── evolved_params.json      # All 40+ evolved parameters
├── governance_state.json    # Kill switch states, change history
├── regime_state.json        # Regime detector EMA state
└── backups/                 # Up to 5 prior generation snapshots
```

**Safety guarantees:**
- Writes use temp file + atomic rename (no partial saves)
- Cross-platform file locking (Windows: msvcrt, Linux: fcntl)
- Walk-forward gate: won't save if performance regressed >5%
- ML models are HMAC-signed to prevent tampering

---

## 4. Trading Strategies — The Signal Generators

### Strategy Architecture

The platform has **15+ trading strategies** organized in three tiers:

```
Tier 1: Core Strategies (built-in, always available)
   ├── MeanReversionStrategy      ← Buy oversold, sell overbought (Bollinger + RSI)
   ├── MomentumStrategy           ← Follow trends (MACD + SMA crossover)
   ├── EnsembleStrategy           ← AI ensemble predictions
   ├── StatisticalArbitrageStrategy ← Kalman-filtered mean reversion
   ├── RebalancingStrategy        ← Portfolio weight drift correction
   └── BasicStrategy              ← Simple RSI + SMA cross

Tier 2: Advanced Strategies (quantitative, indicator-heavy)
   ├── SqueezeBreakoutStrategy          ← Bollinger-Keltner squeeze detection
   ├── FailedBreakoutReversalStrategy   ← Reversal on failed Donchian breakouts
   ├── MultiTimeframeBreakoutStrategy   ← 3-filter higher TF + breakout + momentum
   ├── AdaptiveRegimeMomentumStrategy   ← Volatility regime + multi-TF momentum
   ├── OrderFlowImbalanceStrategy       ← CLV + OBV + VWAP deviation
   ├── VolatilityStructureStrategy      ← GARCH proxy expansion/compression
   ├── CrossSectionalMomentumStrategy   ← 120-day cross-section with crash guard
   └── MicrostructureAlphaStrategy      ← Smart Money + vol-price divergence

Tier 3: Organism Strategies (ML-driven, evolving)
   └── Living Organism ML Signals       ← XGBoost ensemble + 79 features + self-evolution
```

### How Signals Flow Through the System

```
Multiple Strategies → TradingSignal objects
         │
         ▼
Strategy Engine (StrategyEngine.generate_and_gate())
   │
   ├── 1. Resolve Signal Conflicts
   │      Conviction-weighted netting: if momentum says BUY and
   │      mean_reversion says SELL, the higher-confidence signal wins
   │
   ├── 2. Whipsaw Prevention
   │      Block position flips within 60 seconds (anti-churn)
   │
   ├── 3. Inverse-Volatility Sizing
   │      Scale positions inversely to ATR (target 2% daily vol)
   │
   ├── 4. Correlation Check
   │      Warn if >70% of positions are in the same direction
   │
   └── 5. Risk Gate
          Pass each plan through AsyncRiskManager.before_order()
          → Position limits → Notional caps → Kelly → VaR
         │
         ▼
Approved ExecutionPlan objects
         │
         ▼
OrderService.plan_and_submit() → Broker
```

### Strategy Details

#### Mean Reversion Strategy
- **Concept:** Buy when price is oversold (too far below fair value), sell when overbought
- **Indicators:** Bollinger Bands (20-period, 2σ) + RSI (14-period)
- **Buy signal:** RSI < 30 AND price below lower Bollinger Band (with 1% tolerance)
- **Sell signal:** RSI > 70 AND price above upper Bollinger Band
- **Risk:** 2% per trade, stop-loss at 2% below entry + 2% band offset, take-profit at 5%
- **Best regime:** Choppy/ranging markets

#### Momentum Strategy
- **Concept:** Follow the trend — buy assets moving up, sell assets moving down
- **Indicators:** MACD crossover + SMA crossover
- **Buy signal:** MACD crosses above signal line OR fast SMA crosses above slow SMA
- **Sell signal:** MACD crosses below signal line OR fast SMA crosses below slow SMA
- **Risk:** 2% per trade, 3% stop-loss, 5% take-profit
- **Best regime:** Strong trending markets

#### Ensemble Strategy
- **Concept:** Use AI model predictions to trade
- **Mechanism:** Gets predictions from the ML ensemble model
- **Buy signal:** Model confidence > 60% AND predicted return > 2%
- **Strong signal:** Predicted return > 5% (higher conviction)
- **Risk:** Dynamic based on model confidence
- **Best regime:** All regimes (model learns regime-specific patterns)

#### Statistical Arbitrage Strategy
- **Concept:** Trade mean-reversion of statistically related assets using Kalman filtering
- **Mechanism:** Kalman filter tracks the evolving relationship (hedge ratio) between correlated assets
- **Entry:** Z-score exceeds ±2.0 standard deviations from mean
- **Exit:** Z-score returns to ±0.5 standard deviations
- **Kalman parameters:** Process noise Q=0.001, measurement noise R=1.0
- **Best regime:** Stable correlation regimes

#### Adaptive Regime Momentum Strategy
- **Concept:** Adapt momentum trading to the current volatility regime
- **Mechanism:** Classifies market into low/medium/high volatility using vol percentile, then applies regime-appropriate ATR stop multipliers
- **Risk:** ATR-based stops that widen in high-vol and tighten in low-vol
- **Best regime:** All (self-adaptive)

### Living Policy Engine — Adaptive Strategy Weighting

The Living Policy Engine dynamically adjusts how much to trust each strategy:

- **Mechanism:** EMA-smoothed strategy scores (α=0.2) with max 5% weight change per update
- **Weight bounds:** [0.10, 2.50] — no strategy can be completely silenced or dominate too much
- **Regime boost:** Trending markets boost momentum weight +20%. Choppy markets boost mean_reversion +15%
- **Shadow mode:** Can run in shadow mode (calculates but doesn't apply weights) via `LIVING_STRATEGY_MODE=shadow`
- **Persistence:** Snapshots weights to disk every 300 seconds

---

## 5. Machine Learning Pipeline — The Prediction Engine

### Feature Engineering — 79 ML Features

The organism computes **79 features** per symbol per time bar:

| Category | Count | Examples |
|----------|-------|---------|
| **Price Action** | 15 | 1/2/3/5/10/20-day returns, log return, momentum acceleration, body ratio (open-close vs high-low), gap percentage |
| **Trend** | 10 | SMA ratios (5/10/20/50 vs close), MACD/signal/histogram (normalized to ATR), ADX (trend strength) |
| **Mean Reversion** | 8 | RSI (14-period and 5-period), Bollinger position/width, z-scores (20 and 50-period), Stochastic K/D |
| **Volatility** | 10 | ATR (normalized), vol ratios, realized vol (annualized), Parkinson (high-low vol), Garman-Klass (OHLC vol), Bollinger squeeze detection |
| **Volume** | 8 | Volume/SMA ratio, OBV slope, Money Flow Index, VWAP distance, volume breakout flag |
| **Cross-Sectional** | 5 | Relative strength vs SPY, 20-day beta, market correlation, idiosyncratic volatility, sector momentum |
| **Microstructure** | 5 | Spread proxy, price impact, tick direction, close location in range, true range percentage |
| **Temporal** | 4 | Day of week, month (sin/cos cyclical encoding), percentage from 52-week high/low |
| **Regime** | 4 | Trend strength, choppiness index, Hurst exponent, regime label (encoded) |

### ML Model Architecture

The platform uses a **dual-model XGBoost ensemble**:

```
┌─────────────────────────────────────────────────────┐
│  INPUT: 79 features per symbol                       │
│                                                      │
│  Feature Selection (evolved weights > 0.20,          │
│  minimum 15 features kept)                           │
│                                                      │
│      ┌──────────────────┐  ┌──────────────────────┐ │
│      │ Model A           │  │ Model B               │ │
│      │ XGBClassifier     │  │ XGBRegressor          │ │
│      │ (direction:       │  │ (magnitude:           │ │
│      │  up/down)         │  │  expected return)     │ │
│      │                   │  │                       │ │
│      │ n_estimators=200  │  │ n_estimators=200      │ │
│      │ max_depth=5       │  │ max_depth=5           │ │
│      │ learning_rate=0.05│  │ learning_rate=0.05    │ │
│      │ subsample=0.8     │  │ subsample=0.8         │ │
│      │ colsample=0.8     │  │ colsample=0.8         │ │
│      └────────┬─────────┘  └──────────┬────────────┘ │
│               │                       │               │
│               ▼                       ▼               │
│      P(up) probability         Predicted return       │
│      Confidence = |P-0.5|×2                           │
│                                                      │
│  ┌─────────────────────────────────────────────────┐ │
│  │  Phase 4.4 Ensemble Blend (optional)             │ │
│  │  60% Primary XGB + 40% secondary ensemble       │ │
│  │  (RandomForest + optional LightGBM)              │ │
│  └─────────────────────────────────────────────────┘ │
│                                                      │
│  OUTPUT: MLSignal(symbol, direction, confidence,     │
│          predicted_return, feature_importance)        │
└─────────────────────────────────────────────────────┘
```

**Training details:**
- Rolling window: 250 bars of training data
- Target A (direction): `1 if next_day_return > 0 else 0`
- Target B (magnitude): next-day return (extreme returns capped at ±50%)
- Temporal split per symbol to avoid cross-symbol leakage
- Retrained every 60 bars (~1 trading day)

**Dynamic thresholds:** The buy/sell confidence thresholds start at 0.55/0.45 but are evolved by the Self-Evolution Engine based on actual trading accuracy.

### Model Promotion Requirements

For a model to be promoted from training to live trading, it must pass:

1. **Sharpe ratio ≥ 0.3** — minimum risk-adjusted return threshold
2. **Improvement ≥ 5%** — must beat the current incumbent model
3. **Out-of-sample validation** — must perform on unseen data
4. Then goes through the 5-stage promotion pipeline (shadow → paper → canary → ramp → active)

### Drift Detection

The platform monitors for **feature drift** — when the statistical distribution of incoming features changes significantly from what the model was trained on:

- **Method:** Population Stability Index (PSI) with quantile-based bins
- **Warning threshold:** PSI > 0.10
- **Alert threshold:** PSI > 0.25
- **Action:** Triggers automatic model retraining when drift is detected

---

## 6. Order Pipeline — From Signal to Execution

### Complete Order Lifecycle

```
1. SIGNAL GENERATION
   Strategy produces TradingSignal(symbol, side, confidence, stop_loss, take_profit)
        │
2. SIGNAL NETTING (StrategyEngine)
   Multiple signals for same symbol → conviction-weighted net
   Whipsaw prevention → block flips within 60 seconds
        │
3. POSITION SIZING
   Inverse-volatility scaling (target 2% daily vol)
   Convert exposure to share quantity using portfolio value
        │
4. PRE-TRADE RISK CHECK (AsyncRiskManager)
   ├── Position limits (max $1M per position, production)
   ├── Notional caps ($100K default)
   ├── Kelly sizing (max 2× Kelly fraction)
   └── VaR check (max portfolio VaR)
        │
5. ORDER SUBMISSION (OrderService.submit_symbol_order)
   ├── Circuit breaker check (5 failures → OPEN, 5% daily loss → OPEN)
   ├── Per-symbol async lock (prevents duplicate simultaneous orders)
   ├── Idempotency check (TTL 3600s, cache max 10,000 entries)
   ├── DB persist via OrdersRepo.upsert_by_idempotency()
   └── Outbox enqueue (transactional, same DB transaction)
        │
6. OUTBOX DISPATCH (OutboxDispatcher.run_forever)
   ├── Claim batch (FOR UPDATE SKIP LOCKED — concurrent-safe)
   ├── Semaphore(8) — max 8 concurrent dispatches
   ├── Smart TIF: market hours → "day", off-hours → "gtc"
   └── Send to AlpacaBrokerClient.place_order()
        │
7. BROKER EXECUTION (AlpacaBrokerClient)
   ├── HTTP/2 with connection pool (50 keepalive / 100 max)
   ├── Retry on 429, 500, 502, 503, 504 with exponential backoff
   ├── Idempotency: checks for existing order, handles 422 duplicate
   └── Returns broker order ID + status
        │
8. FILL TRACKING
   ├── Order state transitions: SUBMITTED → PENDING_EXECUTION → PARTIALLY_FILLED → FILLED
   ├── Post-fill slippage measurement (feedback to slippage model)
   └── P&L attribution to originating strategy
        │
9. RECONCILIATION
   ├── Startup: fetches last 500 orders from Alpaca, syncs with DB
   └── Per-tick: reconcile broker positions vs tracked positions
```

### Order State Machine

Orders follow a strict 16-state finite state machine:

```
PENDING_VALIDATION → VALIDATED → PENDING_RISK_ASSESSMENT
         │                            │
         │                     ┌──────┴──────┐
         │                     │             │
         │              RISK_APPROVED    RISK_REJECTED
         │                     │
         │              PENDING_SUBMISSION
         │                     │
         │                 SUBMITTED
         │                     │
         │            PENDING_EXECUTION
         │                     │
         │              ┌──────┴──────┐
         │              │             │
         │       PARTIALLY_FILLED   FILLED ← Terminal
         │              │
         │           FILLED ← Terminal
         │
         ├── CANCELLED ← Terminal (user or system cancel)
         ├── REJECTED ← Terminal (risk or broker rejection)
         ├── EXPIRED ← Terminal (time-in-force expired)
         ├── FAILED ← Terminal (system error)
         │
         ├── PENDING_RETRY (transient failure, will retry)
         └── UNDER_REVIEW (manual review needed)
```

Every state transition is:
- Validated against `VALID_TRANSITIONS` dictionary
- Recorded in an append-only audit log (PostgreSQL `audit_log` table)
- Tracked by Prometheus metrics (`order_state_transitions_total`)
- Integrity-verified via SHA-256 hash snapshots

### Circuit Breaker

The order service has a built-in circuit breaker to prevent cascading failures:

| Parameter | Value |
|-----------|-------|
| Failure threshold | 5 consecutive failures → circuit OPEN |
| Success threshold | 3 successes → circuit CLOSED |
| Timeout | 60 seconds before half-open retry |
| Window | 300 seconds sliding window |
| Loss threshold | 5% daily loss → circuit OPEN |
| P&L reset | Daily at 9:30 AM Eastern |

**States:** CLOSED (normal) → OPEN (all orders rejected) → HALF_OPEN (allow one test order) → CLOSED

---

## 7. Risk Management — The Safety Net

### Four Layers of Risk Protection

The platform implements **four independent layers** of risk management:

```
Layer 1: PRE-TRADE RISK (AsyncRiskManager)
   Blocks individual orders that violate limits
   ├── Position size limits
   ├── Notional caps ($100K default per order)
   ├── Kelly criterion sizing (max 2× Kelly fraction = 40%)
   └── Portfolio VaR check

Layer 2: PORTFOLIO RISK (AdvancedRiskManager)
   Monitors aggregate portfolio health
   ├── Value at Risk (VaR) — 1-day, 5-day, 10-day horizons
   ├── Drawdown tracking — running max vs cumulative returns
   ├── Concentration risk — Herfindahl index + sector exposure
   ├── Correlation risk — pairwise correlation averaging
   ├── Market regime detection — CALM/VOLATILE/TRENDING/CRISIS
   └── Risk level scoring → LOW/MEDIUM/HIGH/CRITICAL

Layer 3: TAIL RISK (BlackSwanProtection)
   Circuit breakers for extreme market events
   ├── Flash Crash L1: SPY -3% / 1h → Alert only
   ├── Flash Crash L2: SPY -5% / 1h → Reduce exposure 30%
   ├── Flash Crash L3: SPY -7% / 1h → HALT all trading
   ├── VIX > 40 → Reduce exposure 50%
   ├── Portfolio Drawdown > 5% → Reduce exposure 50%
   └── Single Position Loss > 15% → Alert only

Layer 4: SERVICE-LEVEL RISK (RiskManager Service)
   Dashboard monitoring with DB persistence
   ├── 6 monitored metrics: daily_loss, max_drawdown, position_count,
   │   total_exposure, order_count_daily, buying_power_used
   ├── Status thresholds: NORMAL → WARNING (80%) → CRITICAL (95%) → BREACHED (100%)
   ├── Violation recording + Slack/PagerDuty alerts
   └── Emergency stop: kills all strategies + cancels all pending orders
```

### Risk Limits Reference

| Limit | Production | Development |
|-------|-----------|-------------|
| Max single position | $1,000,000 | $100,000 |
| Max position count | 100 | 100 |
| Max sector concentration | 25% | 25% |
| Max single symbol concentration | 10% | 10% |
| Max daily loss | $50,000 | $5,000 |
| Max portfolio drawdown | 15% | 5% |
| Circuit breaker trigger | 5% intraday | 3% intraday |
| Max leverage | 4× | 4× |
| Maintenance margin | 25% | 25% |
| Kelly fraction ceiling | 20% | 20% |
| Max portfolio VaR | 2% (1-day) | 2% (1-day) |

### Risk Profiles

The platform supports three risk profiles, configurable via `RISK_PROFILE` environment variable:

| Profile | Max Symbol Exposure | Circuit Breaker % | Use Case |
|---------|--------------------|--------------------|----------|
| **strict** | 15% | 5% | Production live trading |
| **staging** | 60% | 20% | Paper trading / testing |
| **relaxed** | 90% | 50% | Development / backtesting |

### Emergency Stop

The kill switch performs three immediate actions:
1. **Stop all active strategies** — no new signals generated
2. **Cancel all pending orders** — pending, submitted, partially filled — all cancelled
3. **Record the event** — DB record with reason, timestamp, affected orders/strategies

Can be triggered via:
- Kill switch button on the Risk Dashboard
- `POST /api/v1/risk/emergency-stop` API call
- Automatic trigger when risk metrics hit BREACHED level

---

## 8. Frontend Application — The Control Center

### Navigation Guide

When you log in, the sidebar on the left gives you access to every feature:

| Page | What It Shows | What You Can Do |
|------|---------------|-----------------|
| **Dashboard** | Portfolio equity, daily P&L, buying power, positions value, active strategies, pending orders, open positions, total P&L, equity chart | View real-time portfolio state, close positions |
| **Orders** | Active and historical orders with status, fills, timestamps | Submit new orders, cancel pending orders, view order history |
| **Trade History** | Completed trades with analytics: win rate, avg win/loss, best/worst trade, Sharpe, max drawdown, profit factor | Browse trade history, export to CSV, filter by date/symbol |
| **Trading** | Order entry form (symbol, side, type, quantity, price, TIF) | Submit buy/sell orders with various order types |
| **Portfolio** | Detailed portfolio view with positions, allocation, performance | Monitor portfolio composition |
| **Strategies** | List of all strategies with status, performance, configuration | Create, edit, delete, start, stop, pause strategies |
| **Backtesting** | Backtest configuration form + results with detailed analytics | Run backtests against historical data, compare results |
| **ML Models** | Model registry, training interface, analytics, lifecycle | Train models, deploy/deactivate, compare, view drift |
| **Risk Management** | Risk level, metrics, violations, emergency status | Monitor risk, resolve violations, trigger kill switch |
| **Market Scanner** | Real-time scanner with RSI, MACD, SMA, ATR, volume, signals | Scan for opportunities, apply filters |
| **Living Organism** | Organism status, tick history, learned state, policy weights, brain manifest, attribution | Freeze/unfreeze, halt/resume, trigger training, manual tick |
| **Reports** | *Coming soon* | — |
| **Admin** | *Coming soon* (visible to admin role only) | — |
| **Settings** | *Coming soon* | — |

### Dashboard Deep Dive

The main Dashboard is your primary view. It shows 8 stat cards:

1. **Portfolio Equity** — Total account value (cash + positions)
2. **Daily P&L** — Today's profit/loss with percentage
3. **Buying Power** — Available cash for new trades
4. **Positions Value** — Total market value of all open positions
5. **Active Strategies** — Count of currently running strategies
6. **Pending Orders** — Orders waiting to be filled
7. **Open Positions** — Number of open positions
8. **Total P&L** — All-time unrealized profit/loss

Below the cards:
- **Positions Table** — All open positions with symbol, quantity, market value, P&L, and a close button
- **Equity Curve Chart** — Portfolio value over time
- **Connection Status** — Shows if WebSocket is connected for real-time updates

### Organism Dashboard Deep Dive

The Organism Dashboard has three tabs:

**Overview Tab:**
- State indicator: ACTIVE (green), FROZEN (yellow), HALTED (red)
- Policy version number
- Tick count
- Latest run details: timestamp, market regime, signals generated, orders submitted, duration, errors
- Improvement indicators: error-free rate, average signals per tick, duration trend

**Runs History Tab:**
- Paginated table (20 per page) of every tick cycle
- Columns: Timestamp, Regime, Signals, Orders, Errors, Duration
- Color-coded by regime and error status

**Learned State Tab:**
- Policy Weights table: strategy name → current weight → score
- Brain Manifest: key-value pairs (model version, generation, Sharpe, trade count)
- Attribution Snapshot: JSON view of per-strategy PnL attribution

**Admin Controls (top of page):**
- Freeze/Unfreeze Adaptation — stops parameter evolution
- Halt/Resume Trading — stops all trading
- Trigger Training — manually start a training cycle
- Trigger Tick — manually execute one tick cycle

### Real-Time Updates (WebSocket)

The frontend maintains a persistent Socket.IO connection to the backend for live updates:

| Event | What Updates | Refresh Rate |
|-------|-------------|--------------|
| `portfolio_update` | Portfolio equity, P&L, buying power | On change |
| `order_update` | Order status changes (submitted, filled, cancelled) | On change |
| `position_update` | Position changes (new, closed, P&L updates) | On change |
| `organism_tick` | Organism dashboard (regime, signals, state) | Every 60 seconds |
| `risk_metric_update` | Risk dashboard metrics | On change |
| `risk_violation_alert` | Risk violation notifications | On event |
| `emergency_stop_event` | Emergency stop banner | On event |
| `strategy_update` | Strategy status changes | On change |
| `signal` | New trading signals | On generation |
| `alert` | System-wide alerts | On event |

**Auto-reconnect:** If the WebSocket disconnects, it automatically reconnects with exponential backoff (1s → 60s, max 10 attempts).

---

## 9. Backend API — Every Endpoint Documented

### Authentication

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/v1/auth/login` | None | Login with username/password → JWT tokens |
| POST | `/api/v1/auth/register` | None | Register new user account |
| POST | `/api/v1/auth/logout` | JWT | Logout (blacklists current token) |
| POST | `/api/v1/auth/token/refresh` | JWT | Refresh expired access token |
| POST | `/api/v1/auth/password/reset` | JWT | Reset password |

### Portfolio & Positions

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/v1/portfolio` | JWT | Full portfolio (equity, P&L, buying power, positions) |
| GET | `/api/v1/portfolio/history` | JWT | Portfolio value history |
| GET | `/api/v1/positions` | JWT | All open positions |
| GET | `/api/v1/positions/{symbol}` | JWT | Position detail for symbol |

### Orders & Trades

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/v1/orders` | JWT | List orders (paginated, filterable) |
| GET | `/api/v1/orders/{id}` | JWT | Single order detail |
| POST | `/api/v1/orders` | JWT | Submit new order |
| PATCH | `/api/v1/orders/{id}` | JWT | Modify order (cancel-and-replace) |
| DELETE | `/api/v1/orders/{id}` | JWT | Cancel order |
| GET | `/api/v1/trades` | JWT | Trade history with analytics |
| GET | `/api/v1/trades/analytics` | JWT | Trade analytics (win rate, Sharpe, etc.) |
| GET | `/api/v1/trades/export/csv` | JWT | Export trades as CSV |

### Strategies

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/v1/strategies` | JWT | List all strategies |
| GET | `/api/v1/strategies/{id}` | JWT | Strategy detail |
| POST | `/api/v1/strategies` | JWT | Create new strategy |
| PATCH | `/api/v1/strategies/{id}` | JWT | Update strategy config |
| DELETE | `/api/v1/strategies/{id}` | JWT | Delete strategy |
| POST | `/api/v1/strategies/{id}/start` | JWT | Activate strategy |
| POST | `/api/v1/strategies/{id}/stop` | JWT | Deactivate strategy |
| POST | `/api/v1/strategies/{id}/pause` | JWT | Pause strategy |
| GET | `/api/v1/strategies/{id}/performance` | JWT | Performance metrics |
| POST | `/api/v1/strategies/{id}/backtest` | JWT | Run backtest |

### Backtesting

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/v1/backtests` | JWT | List backtest history |
| GET | `/api/v1/backtests/{id}` | JWT | Backtest result detail |
| POST | `/api/v1/backtests` | JWT | Run new backtest |
| DELETE | `/api/v1/backtests/{id}` | JWT | Delete backtest |
| GET | `/api/v1/backtests/{id}/export` | JWT | Export results (CSV/JSON) |

### ML Models

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/v1/models` | JWT | List models (paginated, filtered) |
| GET | `/api/v1/models/{id}` | JWT | Model detail |
| DELETE | `/api/v1/models/{id}` | JWT | Delete model |
| POST | `/api/v1/models/{id}/activate` | JWT | Activate/deactivate model |
| POST | `/api/v1/models/train` | JWT | Start model training |
| GET | `/api/v1/models/training/{jobId}` | JWT | Training progress |
| POST | `/api/v1/models/training/{jobId}/cancel` | JWT | Cancel training |
| POST | `/api/v1/models/predict` | JWT | Single prediction |
| POST | `/api/v1/models/predict/batch` | JWT | Batch predictions |
| GET | `/api/v1/models/{id}/features` | JWT | Feature importance |
| POST | `/api/v1/models/compare` | JWT | Compare models |
| GET | `/api/v1/models/{id}/health` | JWT | Health & drift metrics |
| GET | `/api/v1/models/lifecycle/summary` | JWT | Lifecycle overview |

### Risk Management

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/v1/risk/dashboard` | JWT | Full risk dashboard data |
| GET | `/api/v1/risk/metrics` | JWT | All risk metrics |
| GET | `/api/v1/risk/violations` | JWT | Violation history |
| POST | `/api/v1/risk/violations/{id}/resolve` | JWT | Resolve violation |
| GET | `/api/v1/risk/limits` | JWT | Risk limit settings |
| PUT | `/api/v1/risk/limits/{name}` | JWT | Update risk limit |
| POST | `/api/v1/risk/emergency-stop` | JWT | Trigger emergency stop |
| GET | `/api/v1/risk/emergency-stop/active` | JWT | Check active emergency |
| POST | `/api/v1/risk/emergency-stop/{id}/resolve` | JWT | Resolve emergency |

### Living Organism

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/v1/organism/status` | JWT | Full organism status |
| GET | `/api/v1/organism/runs` | JWT | Tick run history |
| GET | `/api/v1/organism/brain` | JWT | Brain manifest |
| GET | `/api/v1/organism/policy` | JWT | Current policy weights |
| GET | `/api/v1/organism/attribution` | JWT | Strategy PnL attribution |
| POST | `/api/v1/organism/train` | **Admin** | Trigger training |
| POST | `/api/v1/organism/freeze` | **Admin** | Freeze adaptation |
| POST | `/api/v1/organism/unfreeze` | **Admin** | Unfreeze adaptation |
| POST | `/api/v1/organism/halt` | **Admin** | Halt all trading |
| POST | `/api/v1/organism/resume` | **Admin** | Resume trading |
| POST | `/api/v1/organism/promote` | **Admin** | Promote candidate model |
| POST | `/api/v1/organism/rollback` | **Admin** | Rollback to previous model |
| POST | `/api/v1/organism/compute-attribution` | **Admin** | Run attribution analysis |
| POST | `/api/v1/organism/tick` | **Admin** | Manual tick execution |

### System Health

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/` | None | Service info (name, version, status) |
| GET | `/health` | None | Full health check (DB, Redis, broker) |
| GET | `/readyz` | None | Readiness probe (DB connected) |
| GET | `/livez` | None | Liveness probe (process alive) |
| GET | `/healthz` | None | Kubernetes health check |
| GET | `/metrics` | None | Prometheus metrics scrape endpoint |

---

## 10. Configuration Reference — Every Setting Explained

### Environment Variables (.env)

The platform reads all configuration from the `.env` file in the project root. Here's every setting:

#### Core Application

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_ENVIRONMENT` | `development` | Environment: development, testing, staging, production |
| `APP_HOST` | `0.0.0.0` | Server bind address |
| `APP_PORT` | `8000` | Server port |
| `APP_LOG_LEVEL` | `INFO` | Logging level: DEBUG, INFO, WARNING, ERROR |
| `DEBUG` | `true` | Enable debug mode |
| `APP_CORS_ORIGINS` | `["localhost:3000","localhost:5173"]` | Allowed CORS origins (JSON array) |

#### Database

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | *(required)* | PostgreSQL connection: `postgresql+asyncpg://user:pass@host:5432/dbname` |
| `DATABASE_POOL_SIZE` | `30` | Connection pool size |
| `DATABASE_MAX_OVERFLOW` | `50` | Extra connections beyond pool |
| `DATABASE_ECHO` | `false` | Log all SQL queries |
| `DB_POOL_RECYCLE` | `3600` | Recycle connections after N seconds |

#### Alpaca Broker

| Variable | Default | Description |
|----------|---------|-------------|
| `ALPACA_API_KEY_ID` | *(required)* | Alpaca API key |
| `ALPACA_API_SECRET_KEY` | *(required)* | Alpaca API secret |
| `ALPACA_PAPER` | `true` | Paper trading mode (set `false` for live) |
| `ALPACA_BASE_URL` | `https://paper-api.alpaca.markets` | API base URL |
| `ALPACA_DATA_URL` | `https://data.alpaca.markets/v2` | Market data URL |
| `ALPACA_STREAM_URL` | `wss://paper-api.alpaca.markets/stream` | WebSocket streaming URL |
| `ALPACA_DATA_FEED` | `iex` | Data feed: `iex` (free) or `sip` (paid, all exchanges) |
| `USE_MOCK_BROKER` | `false` | Use mock broker instead of real Alpaca |
| `USE_MOCK_DATA` | `false` | Use mock market data |

#### Security

| Variable | Default | Description |
|----------|---------|-------------|
| `JWT_SECRET_KEY` | *(required)* | Secret for signing JWT tokens (≥32 chars) |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `JWT_EXPIRE_MINUTES` | `60` | Access token expiration |
| `SECURITY_JWT_SECRET` | `${JWT_SECRET_KEY}` | Alternative JWT secret (some modules) |
| `PICKLE_HMAC_SECRET` | *(test only)* | HMAC key for ML model integrity |

#### Living Organism

| Variable | Default | Description |
|----------|---------|-------------|
| `ORGANISM_ENABLED` | `0` | Enable the Living Organism subsystem (`1` to enable) |
| `ENABLE_ORGANISM_SCHEDULER` | `0` | Enable automatic 60-second tick scheduling |
| `ORGANISM_TICK_INTERVAL_SECONDS` | `60` | Seconds between organism ticks |
| `ORGANISM_LIVE_LOOKBACK` | `500` | Number of historical bars to fetch |
| `ORGANISM_LIVE_TIMEFRAME` | `1Day` | Bar timeframe for analysis |
| `ORGANISM_MAX_POSITIONS` | `8` | Maximum concurrent positions |
| `ORGANISM_RETRAIN_INTERVAL` | `60` | Bars between ML retraining |
| `ORGANISM_TRAIN_WINDOW` | `200` | Training data window size |
| `ORGANISM_MIN_BARS` | `200` | Minimum bars before trading |
| `ORGANISM_LONG_ONLY` | `True` | Restrict to long positions only |
| `ORGANISM_DRAWDOWN_KILL_PCT` | `0.05` | Kill switch trigger (5% drawdown) |
| `ORGANISM_DRAWDOWN_COOLDOWN_S` | `3600` | Cooldown after kill switch (seconds) |

#### Trading

| Variable | Default | Description |
|----------|---------|-------------|
| `TRADING_PAUSED` | `false` | Pause all trading activity |
| `TRADING_START_HOUR_ET` | `9` | Market open hour (Eastern) |
| `TRADING_END_HOUR_ET` | `16` | Market close hour (Eastern) |
| `MAX_DAILY_ORDERS` | `100` | Maximum orders per day |
| `MAX_ORDER_SIZE` | `100` | Maximum shares per order |
| `MAX_ORDER_SIZE_USD` | `1000.0` | Maximum dollar value per order |
| `MAX_DAILY_NOTIONAL_USD` | `10000.0` | Maximum daily notional value |
| `DAILY_NOTIONAL_CAP_USD` | `10000` | Daily notional spending cap |
| `SYMBOL_WHITELIST` | `AAPL,MSFT,GOOGL,...` | Allowed trading symbols |

#### Risk

| Variable | Default | Description |
|----------|---------|-------------|
| `RISK_PROFILE` | `relaxed` | Risk profile: strict, staging, relaxed |
| `RISK_MAX_POSITION_VALUE` | `1.0` | Max position as fraction of portfolio |
| `RISK_MAX_SYMBOL_EXPOSURE` | `0.60` | Max exposure to single symbol |
| `RISK_CIRCUIT_BREAKER_PCT` | `0.20` | Circuit breaker drawdown trigger |
| `RISK_FALLBACK_PORTFOLIO_VALUE` | `250000.0` | Fallback value when real value unavailable |
| `RISK_ALLOW_ADMIN_OVERRIDE` | `true` | Allow admin to override risk blocks |

#### ML / MLOps

| Variable | Default | Description |
|----------|---------|-------------|
| `DISABLE_ML` | `0` | Disable ML entirely (uses no-op stubs) |
| `ENABLE_ML_LIFECYCLE_SCHEDULER` | `0` | Enable ML lifecycle automation |
| `MLOPS_DRIFT_PSI_WARN` | `0.10` | PSI warning threshold |
| `MLOPS_DRIFT_PSI_ALERT` | `0.25` | PSI alert threshold |
| `MLOPS_AUTO_PROMOTION_ENABLED` | `false` | Auto-promote champion models |
| `MLOPS_AUTO_RETRAIN_ENABLED` | `false` | Auto-retrain on drift detection |

#### Living Strategy

| Variable | Default | Description |
|----------|---------|-------------|
| `LIVING_STRATEGY_ENABLED` | `true` | Enable adaptive strategy weighting |
| `LIVING_STRATEGY_MODE` | `active` | Mode: `active` (apply weights) or `shadow` (calculate only) |
| `SCORE_EMA_ALPHA` | `0.2` | EMA smoothing for strategy scores |
| `WEIGHT_MAX_DELTA` | `0.05` | Max weight change per update |

#### Observability

| Variable | Default | Description |
|----------|---------|-------------|
| `OTEL_ENABLED` | `true` | Enable OpenTelemetry tracing |
| `OTEL_SERVICE_NAME` | `algotrading-api-prod` | Service name in traces |
| `PROMETHEUS_ENABLED` | `true` | Enable Prometheus metrics |
| `PROMETHEUS_PATH` | `/metrics` | Metrics scrape path |
| `METRICS_ENABLED` | `true` | Enable application metrics |
| `STRUCTURED_LOGGING` | `true` | JSON structured logging |

#### Outbox

| Variable | Default | Description |
|----------|---------|-------------|
| `OUTBOX_POLL_INTERVAL` | `1.0` | Seconds between outbox polls |
| `OUTBOX_BATCH_SIZE` | `10` | Orders processed per batch |
| `OUTBOX_MAX_RETRIES` | `3` | Max retry attempts |
| `OUTBOX_RETRY_BACKOFF` | `2.0` | Backoff multiplier |

#### Frontend

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_API_BASE_URL` | `http://localhost:8000` | Backend API URL |
| `VITE_WS_BASE_URL` | `http://localhost:8000` | WebSocket server URL |
| `VITE_APP_NAME` | `AlgoTrading Platform` | Application title |
| `VITE_ENABLE_TRADING` | `true` | Enable trading features |
| `VITE_ENABLE_ML_MODELS` | `true` | Enable ML features |
| `VITE_ENABLE_STRATEGIES` | `true` | Enable strategy features |

---

## 11. Getting Started — Setup and First Run

### Prerequisites

| Software | Version | Purpose |
|----------|---------|---------|
| Python | 3.11+ | Backend runtime |
| Node.js | 18+ | Frontend build |
| PostgreSQL | 16 | Database |
| Redis | 7 | Caching |
| Docker + Docker Compose | Latest | Container orchestration (recommended) |

### Option A: Docker Compose (Recommended)

```bash
# 1. Clone and enter the project
cd c:\Users\Marsel\intra\algotrading_platform

# 2. Create your .env file from the template
copy .env.example .env

# 3. Edit .env — set these REQUIRED values:
#    JWT_SECRET_KEY=<generate with: python -c "import secrets; print(secrets.token_urlsafe(32))">
#    POSTGRES_PASSWORD=<strong password>
#    ALPACA_API_KEY_ID=<your Alpaca API key>
#    ALPACA_API_SECRET_KEY=<your Alpaca API secret>
#    DATABASE_URL=postgresql+asyncpg://trading:YOUR_PASSWORD@localhost:5432/algotrading

# 4. Start core services
docker-compose up -d    # Starts: api (8000), db (5432), redis (6379)

# 5. Start frontend dev server
cd frontend
npm install
npm run dev             # Starts on localhost:5173

# 6. Optional: Start observability stack (Prometheus, Grafana)
cd ..
docker-compose --profile observability up -d
# Access Grafana at localhost:3000, Prometheus at localhost:9090
```

### Option B: Local Development (No Docker)

```bash
# 1. Start PostgreSQL and Redis manually
# (Ensure they're running on localhost:5432 and localhost:6379)

# 2. Create virtual environment
cd c:\Users\Marsel\intra\algotrading_platform
python -m venv venv
.\venv\Scripts\Activate.ps1

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Create your .env file
copy .env.example .env
# Edit .env with your values (see step 3 in Option A)

# 5. Run database migrations
alembic upgrade head

# 6. Start backend
python main.py
# Server starts on localhost:8000

# 7. Start frontend (in another terminal)
cd frontend
npm install
npm run dev
# Starts on localhost:5173
```

### First Login

1. Open `http://localhost:5173` in your browser
2. Register a new account at the registration page
3. Log in with your credentials
4. You'll land on the Dashboard — initially empty until the organism starts producing data

### Enabling the Living Organism

To enable the AI trading system, add these to your `.env`:

```env
ORGANISM_ENABLED=1
ENABLE_ORGANISM_SCHEDULER=1
```

Then restart the backend. The organism will begin ticking every 60 seconds.

**Note:** The organism will observe and analyze markets immediately, but it won't execute trades until an ML model passes the promotion gates (Sharpe ≥ 0.3, passes walk-forward validation, completes the 5-stage promotion pipeline).

### Getting Alpaca API Keys

1. Go to [https://alpaca.markets](https://alpaca.markets) and create a free account
2. Navigate to your paper trading dashboard
3. Find your API Key ID and Secret Key
4. Add them to `.env`:
   ```env
   ALPACA_API_KEY_ID=PKxxxxxxxxxxxxxxxx
   ALPACA_API_SECRET_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ALPACA_PAPER=true
   ```

---

## 12. Day-to-Day Operations Guide

### Daily Checklist

| Time | Action | How |
|------|--------|-----|
| **Pre-market (before 9:30 AM ET)** | Verify system health | Check Dashboard — all green? Organism ticking? |
| | Check overnight alerts | Risk Dashboard — any violations? |
| | Review organism state | Organism Dashboard → Overview tab |
| **Market open** | Monitor first tick | Organism Dashboard → watch for regime detection |
| | Check positions | Dashboard → Positions table |
| **Throughout the day** | Monitor P&L | Dashboard → Daily P&L card |
| | Watch risk levels | Risk Dashboard → overall level |
| **Market close** | Review daily performance | Trade History → analytics |
| | Check organism learned state | Organism Dashboard → Learned State tab |
| **Weekly** | Review strategy weights | Organism Dashboard → Policy weights |
| | Check model drift | ML Models → Analytics → Performance Trends |
| | Review risk violations | Risk Dashboard → violation history |

### Common Operations

#### Submitting a Manual Order

1. Navigate to **Trading** page
2. Fill in: Symbol, Side (Buy/Sell), Order Type (Market/Limit/Stop/Stop Limit), Quantity
3. For Limit/Stop orders: enter Price
4. Select Time-in-Force (Day, GTC, IOC, FOK)
5. Click Submit
6. Order appears in **Orders** page with live status updates

#### Running a Backtest

1. Navigate to **Backtesting** page
2. Select a strategy from the dropdown
3. Set date range (max 5 years, no future dates)
4. Configure initial capital and parameters
5. Click "Run Backtest"
6. View results: total return, Sharpe ratio, Sortino, max drawdown, win rate, equity curve, trade log

#### Training a New ML Model

1. Navigate to **ML Models** page → **Training** tab
2. Select model type (ensemble, xgboost, random_forest, regression, classification)
3. Choose features and symbols
4. Set lookback period and test split ratio
5. Optionally configure hyperparameters
6. Click "Start Training"
7. Monitor progress via the training progress bar (polls every 2 seconds)
8. Once complete, evaluate results in the Analytics tab

#### Triggering Emergency Stop

**Via UI:**
1. Navigate to **Risk Management** page
2. Click the large red **Kill Switch** button
3. Confirm action
4. All strategies stop, all pending orders cancelled

**Via API:**
```
POST /api/v1/risk/emergency-stop
Authorization: Bearer <your-jwt-token>
```

**To recover:**
1. Investigate the cause
2. Resolve the issue
3. Go to Risk Management → resolve the emergency stop
4. Restart strategies manually

### Monitoring the Organism

The Organism Dashboard tells you everything about the AI's current state:

**Understanding the Overview:**
- **State: ACTIVE** (green) — organism is running normally
- **State: FROZEN** (yellow) — adaptation is frozen but trading continues
- **State: HALTED** (red) — all trading stopped

**Understanding Regimes:**
- **trending_up** — market is in an uptrend. Organism trades aggressively.
- **trending_down** — market is declining. Organism trades defensively.
- **chop** — market is range-bound. Organism reduces position sizes.
- **high_vol** — market is very volatile. Organism widens stops, reduces sizes.
- **low_vol** — market is calm. Organism may trade more.
- **stress** — extreme market conditions. Organism minimizes exposure.

**Understanding Signals:**
- "0 signals generated" — Normal when no ML model is promoted yet. The organism is learning but not trading.
- "N signals generated" — The ML model found N trading opportunities this tick.

---

## 13. Maintenance Manual

### Backup and Recovery

#### Database Backups
```bash
# PostgreSQL backup
pg_dump -h localhost -U trading algotrading > backup_$(date +%Y%m%d).sql

# Restore
psql -h localhost -U trading algotrading < backup_20260217.sql
```

#### Brain State Backups
The organism brain auto-maintains up to 5 generational backups in `organism_brain/backups/`. To manually backup:
```bash
# Copy the entire brain directory
xcopy organism_brain organism_brain_backup_%date:~-4,4%%date:~-7,2%%date:~-10,2% /E /I
```

#### Recovery from Brain Corruption
If the brain state becomes corrupted:
1. Stop the backend: `Ctrl+C` on the running `python main.py`
2. Delete the corrupted brain: `rmdir /s /q organism_brain`
3. Restart: `python main.py`
4. The organism will start learning from scratch (cold start)

### Database Migrations

```bash
# Check current migration version
alembic current

# Upgrade to latest
alembic upgrade head

# Create a new migration after model changes
alembic revision --autogenerate -m "description of change"

# Rollback one migration
alembic downgrade -1
```

### Log Management

Logs are stored in the `logs/` directory:
- `logs/app.log` — Main application log
- `logs/audit/` — Audit trail logs

**Log rotation:** Max 10MB per file, 5 backup files kept.

**Changing log level at runtime:**
```env
APP_LOG_LEVEL=DEBUG  # or INFO, WARNING, ERROR
```

### Updating Dependencies

```bash
# Backend
pip install -r requirements.txt --upgrade

# Frontend
cd frontend
npm update

# Check for security vulnerabilities
pip-audit
npm audit
```

### Performance Tuning

#### Database Pool Tuning
```env
DATABASE_POOL_SIZE=30        # Increase for high concurrency
DATABASE_MAX_OVERFLOW=50     # Temporary extra connections
DB_POOL_RECYCLE=3600         # Recycle connections hourly
```

#### Organism Tick Interval
```env
ORGANISM_TICK_INTERVAL_SECONDS=60   # Default: 60 seconds
# Lower = more responsive but more API calls
# Higher = less responsive but fewer API calls
```

#### Redis Caching
```env
REDIS_URL=redis://localhost:6379    # Default Redis
# For production, consider Redis Cluster or Sentinel
```

### Health Checks

```bash
# Quick system check
curl http://localhost:8000/health

# Readiness check (DB connected)
curl http://localhost:8000/readyz

# Liveness check (process alive)
curl http://localhost:8000/livez

# Prometheus metrics
curl http://localhost:8000/metrics
```

### Running Tests

```powershell
# Fast smoke test (< 30 seconds)
python -m pytest -x -q -m "unit" --maxfail=3 --tb=short

# Integration tests (< 5 minutes)
python -m pytest -x -q -m "unit or api or services" --cov=backend --cov-branch --tb=short

# Full test suite with coverage report
python -m pytest -v --cov=backend --cov-branch --cov-report=html:test_results --cov-report=term-missing:skip-covered

# Frontend TypeScript check
cd frontend && npx tsc --noEmit

# Frontend build test
cd frontend && npm run build
```

### Docker Maintenance

```bash
# View running services
docker-compose ps

# View logs
docker-compose logs -f api      # Follow API logs
docker-compose logs -f db       # Follow PostgreSQL logs

# Restart a service
docker-compose restart api

# Rebuild after code changes
docker-compose up -d --build api

# Full cleanup (WARNING: destroys data volumes)
docker-compose down -v
```

### Kubernetes Operations

```bash
# Deploy
kubectl apply -k k8s/

# Check pods
kubectl -n algotrading get pods

# View logs
kubectl -n algotrading logs -f deployment/algotrading-api

# Scale replicas
kubectl -n algotrading scale deployment algotrading-api --replicas=3

# Rollback deployment
kubectl -n algotrading rollout undo deployment/algotrading-api
```

---

## 14. Troubleshooting Guide

### Common Issues and Solutions

#### Backend won't start

| Symptom | Cause | Solution |
|---------|-------|----------|
| `RuntimeError: No database URL` | Missing `DATABASE_URL` in `.env` | Add `DATABASE_URL=postgresql+asyncpg://trading:password@localhost:5432/algotrading` |
| `ConnectionRefusedError: 5432` | PostgreSQL not running | Start PostgreSQL: `docker-compose up -d db` |
| `ConnectionRefusedError: 6379` | Redis not running | Start Redis: `docker-compose up -d redis` |
| `ModuleNotFoundError` | Missing Python dependencies | `pip install -r requirements.txt` |
| `JWT validation failed` | Invalid or missing JWT_SECRET_KEY | Set `JWT_SECRET_KEY` in `.env` (min 32 characters) |

#### Frontend won't build

| Symptom | Cause | Solution |
|---------|-------|----------|
| TypeScript errors | Type mismatches | Run `npx tsc --noEmit` to see errors, fix types |
| `ENOENT: package.json` | Wrong directory | `cd frontend` first |
| Node modules missing | Dependencies not installed | `npm install` |

#### Organism not ticking

| Symptom | Cause | Solution |
|---------|-------|----------|
| "Organism not enabled" | `ORGANISM_ENABLED` not set | Add `ORGANISM_ENABLED=1` to `.env` |
| Ticks show but no signals | No promoted ML model | Normal — model needs to pass Sharpe ≥ 0.3 and promotion pipeline |
| "Governance: HALTED" | Drawdown kill triggered | Wait for cooldown (1 hour) or manually resume via UI |
| "Governance: FROZEN" | Adaptation frozen | Unfreeze via Organism Dashboard |
| No tick for >120 seconds | Scheduler stuck or API timeout | Check logs, restart backend |

#### Orders not executing

| Symptom | Cause | Solution |
|---------|-------|----------|
| "Circuit breaker OPEN" | 5+ failures or 5% daily loss | Wait for 60-second timeout, fix upstream issue |
| "Risk check failed" | Order exceeds risk limits | Reduce order size or adjust risk limits |
| "Idempotency conflict" | Duplicate order submission | Wait for TTL (3600s) to expire |
| Orders stuck in SUBMITTED | Outbox dispatcher backlog | Check logs for dispatcher errors |
| "Market closed" | Trading outside hours | Wait for market hours (9:30–16:00 ET, weekdays) |

#### WebSocket disconnected

| Symptom | Cause | Solution |
|---------|-------|----------|
| "Disconnected" badge | Backend restarted | Auto-reconnects within 60 seconds |
| Persistent disconnection | CORS or auth issue | Check browser console, verify CORS origins in `.env` |
| No real-time updates | WebSocket disabled | Verify `WEBSOCKET_ENABLED=true` |

### Log Locations

| What | Where |
|------|-------|
| Backend application logs | `logs/app.log` |
| Audit trail | `logs/audit/` |
| Docker container logs | `docker-compose logs api` |
| Frontend console | Browser Developer Tools → Console tab |
| Test results | `test_results/` directory |
| Organism brain | `organism_brain/` directory |

### Useful Debug Commands

```bash
# Check if backend is responding
curl -s http://localhost:8000/ | python -m json.tool

# Check database connectivity
curl -s http://localhost:8000/readyz

# View organism status
curl -s -H "Authorization: Bearer TOKEN" http://localhost:8000/api/v1/organism/status | python -m json.tool

# View portfolio
curl -s -H "Authorization: Bearer TOKEN" http://localhost:8000/api/v1/portfolio | python -m json.tool

# Check Prometheus metrics
curl -s http://localhost:8000/metrics | head -50
```

---

## 15. Architecture Deep Dives

### Data Flow: Login to First Trade

```
1. USER opens localhost:5173 → React app loads
2. USER enters credentials → POST /api/v1/auth/login
3. BACKEND validates password (bcrypt) → creates JWT token (HS256, 60min expiry)
4. FRONTEND stores access token in memory (XSS protection), refresh in sessionStorage
5. FRONTEND starts Socket.IO connection with JWT auth
6. FRONTEND loads Dashboard → GET /api/v1/portfolio → Alpaca account data
7. WEBSOCKET receives organism_tick event → dashboard updates
8. USER navigates to Trading → fills order form → POST /api/v1/orders
9. ORDER SERVICE validates → risk checks → persists to DB + outbox (same transaction)
10. OUTBOX DISPATCHER claims order → sends to Alpaca → gets fill
11. FILL recorded in DB → WebSocket broadcasts order_update
12. FRONTEND receives update → refreshes positions, portfolio
```

### Data Flow: Organism Tick Cycle (Detailed)

```
SCHEDULER.tick() [every 60s]
    │
    ▼
LIVE_ENGINE.live_tick()
    │
    ├─ governance.is_trading_halted() → skip if True
    │
    ├─ alpaca_data_client.get_historical_bars_df(symbol, 500, "1Day")
    │     └─ HTTP GET https://data.alpaca.markets/v2/stocks/{symbol}/bars
    │     └─ Returns DataFrame: Open, High, Low, Close, Volume
    │
    ├─ regime_detector.detect(bars_df)
    │     ├─ SMA slope + price vs SMA → trend score
    │     ├─ ATR ratio + returns vol → volatility score
    │     ├─ Volume anomaly detection → stress score
    │     └─ Softmax → probability vector → EMA smooth (α=0.3)
    │
    ├─ positions_service.get_all_positions()
    │     └─ alpaca TradingClient → live broker positions
    │
    ├─ adaptive_exit_engine.check_exit(position, bars, regime)
    │     ├─ Regime-adaptive lookup table (stop ATR, TP R-mult, trail ATR)
    │     └─ Priority: stop-loss > partial TP > full TP > trail > time-based
    │
    ├─ pyramider.check_pyramid(position, bars)
    │     └─ Layer 1 at +1.5R, Layer 2 at +3.0R, anti-pyramid at -0.7R / -1.0R
    │
    ├─ ml_signal_generator.predict(features)
    │     ├─ compute_ml_features(bars, spy_bars) → 79 features
    │     ├─ XGBClassifier.predict_proba() → P(up)
    │     ├─ XGBRegressor.predict() → expected return
    │     └─ Ensemble blend: 60% primary + 40% secondary
    │
    ├─ kelly_sizer.size(signal, regime, portfolio)
    │     └─ Half-Kelly × drawdown × vol_target × regime × confidence × breakout
    │
    ├─ broker_client.place_order(symbol, qty, side)
    │     └─ Through OrderService → outbox → AlpacaBrokerClient
    │
    ├─ [Every 60 bars] evolution_engine.evolve(trades)
    │     └─ 10 adaptation steps (see Section 3)
    │
    └─ [Every 10 ticks] brain_persistence.save()
          └─ Walk-forward gate → atomic file write → HMAC-signed models
```

### Middleware Stack (Request Processing Order)

Every HTTP request passes through this middleware chain:

```
INCOMING REQUEST
    │
    ▼
1. CORS Middleware
   Check Origin header, add Access-Control-Allow-* headers
    │
    ▼
2. Rate Limiting Middleware
   Token bucket per IP, exempt: /health, /metrics, /docs
    │
    ▼
3. Request Deduplication Middleware
   SHA-256 hash of (method + path + body), TTL=300s, cache=10K entries
   Prevents duplicate requests from being processed
    │
    ▼
4. GZip Middleware
   Compress responses > 500 bytes
    │
    ▼
5. Metrics Middleware
   Record: http_requests_total counter + http_request_duration_seconds histogram
   Labels: method, route, status_code
    │
    ▼
6. Route Handler (your endpoint code)
    │
    ▼
OUTGOING RESPONSE
```

### Security Architecture

```
Authentication Flow:
  POST /auth/login → bcrypt verify → JWT(sub, roles, iss, aud, exp, iat, jti) → 200

Request Authentication:
  Request → Extract Bearer token → decode_token() → verify signature, exp, iss, aud
  → check token blacklist (memory first, then Redis) → get_current_user()
  → inject AuthenticatedUser(username, roles, token_id) into request

Role-Based Access Control:
  Route dependencies:
  - get_authenticated_user → requires valid JWT (any role)
  - require_admin → requires "admin" role
  - require_trader → requires "trader" or "admin" role
  - require_api → requires "api" or "admin" role

Token Security:
  - Access tokens: memory only (never localStorage)
  - Refresh tokens: sessionStorage (cleared on tab close)
  - Token blacklist: dual storage (Redis + in-memory failsafe)
  - Fail-closed: if Redis unavailable, tokens are revoked by default
  - 72-byte bcrypt limit: passwords > 72 bytes are rejected (not silently truncated)

Production Guards:
  - JWT secret validated ≥ 32 characters
  - Default secrets rejected in production
  - API keys checked with constant-time comparison
```

---

## 16. Glossary

| Term | Definition |
|------|-----------|
| **ATR** | Average True Range — a measure of volatility based on high-low-close range |
| **Alpha** | Excess return above a benchmark (e.g., beating SPY) |
| **Beta** | Measure of a stock's volatility relative to the overall market |
| **Bollinger Bands** | Price channels at ±2 standard deviations from a moving average |
| **Brain** | The organism's persisted learned state (models, parameters, trade history) |
| **Breakout** | Price movement through a support or resistance level |
| **Circuit Breaker** | Safety mechanism that halts trading after a series of failures or excessive losses |
| **CVaR** | Conditional Value at Risk — expected loss in the worst X% of scenarios |
| **Drawdown** | Peak-to-trough decline in portfolio value |
| **EMA** | Exponential Moving Average — weighted average giving more weight to recent data |
| **Epoch** | One evolution cycle (~60 bars) where parameters are updated |
| **Feature** | A computed numerical value used as input to the ML model |
| **Governance** | Kill switches and safety controls that override trading decisions |
| **Half-Kelly** | 50% of the Kelly criterion optimal bet size (more conservative) |
| **Hurst Exponent** | Measure of long-term memory in a time series (>0.5 = trending, <0.5 = mean-reverting) |
| **Idempotency** | Ensuring the same operation can be retried without creating duplicates |
| **JWT** | JSON Web Token — compact, URL-safe token for authentication |
| **Kelly Criterion** | Optimal bet sizing formula: `f = (bp - q) / b` where b=odds, p=win probability, q=1-p |
| **MACD** | Moving Average Convergence Divergence — trend-following momentum indicator |
| **MFI** | Money Flow Index — volume-weighted RSI |
| **OBV** | On-Balance Volume — running cumulative volume based on price direction |
| **Outbox Pattern** | Design pattern where messages are written to a DB table (outbox) in the same transaction as business data, then dispatched asynchronously |
| **Promotion Pipeline** | Staged rollout (shadow → paper → canary → ramp → active) for deploying new ML models |
| **PSI** | Population Stability Index — measures distribution shift between two datasets |
| **Pyramiding** | Adding to a winning position at predetermined levels |
| **R-multiple** | Return expressed as a multiple of initial risk (e.g., 3R = 3× your stop-loss distance) |
| **RBAC** | Role-Based Access Control — permissions tied to user roles (admin, trader, viewer) |
| **Regime** | Current market state classification (trending, choppy, volatile, stressed) |
| **RSI** | Relative Strength Index — momentum oscillator (0-100, oversold<30, overbought>70) |
| **Self-Evolution** | The organism's ability to adapt its own parameters from trade outcomes |
| **Sharpe Ratio** | Risk-adjusted return: `(mean return - risk-free rate) / standard deviation` |
| **Slippage** | Difference between expected execution price and actual fill price |
| **Socket.IO** | WebSocket library with automatic reconnection, topic-based pub/sub |
| **Sortino Ratio** | Like Sharpe but only penalizes downside volatility |
| **Tick** | One execution cycle of the organism (every 60 seconds) |
| **TIF** | Time-in-Force — how long an order remains active (day, gtc, ioc, fok) |
| **Trailing Stop** | Stop-loss that moves up (for longs) as the price rises, locking in profits |
| **Universe** | The set of symbols the organism is allowed to trade |
| **VaR** | Value at Risk — maximum expected loss at a given confidence level |
| **VWAP** | Volume-Weighted Average Price — benchmark price weighted by trade volume |
| **Walk-Forward** | Validation technique: train on window, test on next period, slide forward, repeat |
| **Whipsaw** | Rapid reversal of a signal, causing unprofitable back-and-forth trades |
| **XGBoost** | eXtreme Gradient Boosting — ensemble ML algorithm using sequential decision trees |
| **Z-Score** | Number of standard deviations from the mean (used in mean-reversion strategies) |

---

*This document was generated on February 17, 2026, from a comprehensive analysis of the platform codebase. For the latest status, see `docs/PLATFORM_STATUS.md`.*
