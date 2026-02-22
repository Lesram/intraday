# Intra Trading Platform — Comprehensive Third-Party Audit Report

**Report Date:** 2026-02-21
**Platform Version:** Commit `a1713d7` (main branch)
**Prepared For:** Independent third-party code review
**Status:** Paper trading (live market, real Alpaca account, no real money at risk)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Platform Overview](#2-platform-overview)
3. [Architecture](#3-architecture)
4. [Backend Code Inventory](#4-backend-code-inventory)
5. [Frontend Code Inventory](#5-frontend-code-inventory)
6. [Infrastructure & Deployment](#6-infrastructure--deployment)
7. [Test Coverage & Quality](#7-test-coverage--quality)
8. [Security Posture](#8-security-posture)
9. [Known Issues & Technical Debt](#9-known-issues--technical-debt)
10. [Go-Live Readiness Checklist](#10-go-live-readiness-checklist)
11. [Recommendations](#11-recommendations)
12. [File Reference Index](#12-file-reference-index)

---

## 1. Executive Summary

### What This Platform Is

Intra is an autonomous algorithmic trading platform built around a "Living Organism" — a self-learning, self-evolving trading engine that detects market regimes, generates ML-driven signals, sizes positions via Kelly criterion, manages adaptive exits, and continuously improves through trade attribution and parameter evolution.

### Codebase Size

| Metric | Count |
|--------|-------|
| Backend Python files | 291 |
| Backend Python lines | 128,227 |
| Frontend TypeScript files | 191 |
| Frontend TypeScript lines | 42,021 |
| Test files (backend) | 384 |
| Test files (frontend) | 18 |
| Total lines of code | ~170,000 |

### Test Results (2026-02-21, this session)

| Suite | Passed | Skipped | Failed |
|-------|--------|---------|--------|
| Backend (pytest) | 7,021 | 684 | 0 |
| Frontend (vitest) | 134 | 0 | 0 |
| **Total** | **7,155** | **684** | **0** |

### Current State

- **Paper trading** on Alpaca (account PA3RLEN7T0N4, ~$106.8K equity, 15 positions)
- **Engine auto-resumes** at 9:28 AM ET daily, ticks every 10 seconds during market hours
- **Docker**: 3 containers (api, db, redis) running
- **Brain persistence**: organism_brain/ directory (gitignored), JSON + CSV state files
- **All tests green**, zero failures across backend and frontend

---

## 2. Platform Overview

### Core Capabilities

1. **Living Organism Engine** — Self-learning trading system with regime detection, ML signals, Kelly sizing, adaptive exits, and parameter evolution
2. **ML Pipeline** — XGBoost ensemble models for direction prediction + magnitude estimation, 79 engineered features, continuous retraining
3. **Adaptive Exit Engine** — ATR-based exits with trailing stops, partial profit taking, regime-conditioned tightening, and 15% max-loss safety net
4. **Decision Telemetry** — Full tick-by-tick transparency: every alpha score, breakout signal, Kelly calculation, and exit proximity recorded in ring buffer
5. **Governance Controls** — Kill switches, drawdown limits (8%), freeze/halt controls, promotion pipeline (shadow → paper → canary → ramp → active)
6. **Market Scanner** — Scans Alpaca screener for most-actives and movers, dynamic universe rotation
7. **Full Trading UI** — React dashboard with real-time WebSocket updates, order management, positions, backtesting, risk management

### Technology Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, Uvicorn, async SQLAlchemy |
| Frontend | React 19, TypeScript, Vite, Ant Design 5 |
| Database | PostgreSQL 16 (Docker) |
| Cache | Redis 7 (Docker) |
| Broker | Alpaca Markets (paper + live APIs) |
| ML | XGBoost, scikit-learn, LightGBM |
| State Management | Zustand + React Query |
| Real-time | Socket.IO WebSocket |
| Containerization | Docker Compose |
| CI/CD | GitHub Actions (lint, type check, security scan, test + coverage) |
| Monitoring | Prometheus + Grafana + OpenTelemetry (optional) |

---

## 3. Architecture

### System Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    FRONTEND (React 19)                       │
│  Dashboard │ Organism │ ML Models │ Orders │ Positions │ ... │
│            Socket.IO WebSocket + React Query                 │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTP/WS (port 5173 → proxy → 8000)
┌──────────────────────▼──────────────────────────────────────┐
│                  FASTAPI BACKEND (port 8000)                 │
│  Routes: /auth, /orders, /portfolio, /organism, /ml-models   │
│  Middleware: JWT auth, CORS, rate limiting                    │
├──────────────────────────────────────────────────────────────┤
│               LIVING ORGANISM ENGINE                         │
│  ┌──────────┐ ┌───────────┐ ┌──────────┐ ┌───────────────┐ │
│  │ Regime   │ │ Alpha     │ │ Kelly    │ │ Adaptive      │ │
│  │ Detector │ │ Scanner   │ │ Sizer    │ │ Exits         │ │
│  └──────────┘ └───────────┘ └──────────┘ └───────────────┘ │
│  ┌──────────┐ ┌───────────┐ ┌──────────┐ ┌───────────────┐ │
│  │ ML Signal│ │ Breakout  │ │ Self     │ │ Brain         │ │
│  │ Generator│ │ Scanner   │ │ Evolution│ │ Persistence   │ │
│  └──────────┘ └───────────┘ └──────────┘ └───────────────┘ │
│  ┌──────────┐ ┌───────────┐ ┌──────────┐ ┌───────────────┐ │
│  │ Decision │ │ Governance│ │ Universe │ │ Background    │ │
│  │ Telemetry│ │ Controller│ │ Selector │ │ Trainer       │ │
│  └──────────┘ └───────────┘ └──────────┘ └───────────────┘ │
├──────────────────────────────────────────────────────────────┤
│  INTEGRATIONS                                                │
│  AlpacaBroker │ AlpacaData │ TradeStream │ MarketDataStream  │
├──────────────────────────────────────────────────────────────┤
│  INFRASTRUCTURE                                              │
│  PostgreSQL 16 │ Redis 7 │ Prometheus │ Grafana              │
└──────────────────────────────────────────────────────────────┘
```

### Request Flow (One Tick)

1. **Scheduler** fires `live_tick()` every 10 seconds during market hours
2. **Data fetch**: Historical bars for all symbols in universe (Alpaca REST)
3. **Feature engineering**: 79 ML features computed per symbol (no lookahead)
4. **Regime detection**: Market classified as TRENDING_UP/DOWN, CHOP, HIGH_VOL, LOW_VOL, STRESS, UNKNOWN
5. **ML signal generation**: XGBoost ensemble predicts direction + magnitude per symbol
6. **Alpha scanning**: 7-factor composite scoring (ML 25%, breakout 20%, institutional 15%, momentum 15%, momentum quality 10%, volume 10%, regime 5%)
7. **Breakout scanning**: 6-pattern detection (squeeze, volume surge, range contraction, relative strength, pivot, institutional flow)
8. **Kelly sizing**: Half-Kelly with drawdown scaling, volatility targeting, regime conditioning, breakout bonus
9. **Order submission**: Market orders via Alpaca, with sector diversification gate (max 4 per sector)
10. **Exit checking**: ATR-based stops, trailing activation after 3x ATR move, partial profit at 3R, 15% max-loss safety net
11. **Brain save**: Full state persisted to disk (models, equity curve, trades, evolved params)
12. **Telemetry**: Full decision snapshot recorded in ring buffer (360 ticks / ~1 hour)
13. **Evolution**: Background training + parameter adaptation from trade outcomes

---

## 4. Backend Code Inventory

### 4.1 Organism Engine (33 files, 15,888 lines)

The organism is the core of the platform. Every file is listed with its purpose and key functions.

#### Core Decision Loop

| File | Lines | Purpose |
|------|-------|---------|
| `backend/organism/live_engine.py` | 2,506 | Main tick loop, order submission, exit checking, telemetry capture |
| `backend/organism/brain_persistence.py` | 1,246 | Persist/restore full learned state (ML models, equity curve, trades, evolved params) |
| `backend/organism/self_evolution.py` | 1,200 | Meta-learning: adapts all tunable parameters from trade evidence |
| `backend/organism/routes.py` | 593 | 17 API endpoints for organism status, decisions, governance controls |

**Key functions in `live_engine.py`:**
- `live_tick()` (line ~200) — One full organism cycle
- `_check_exits()` (line ~698) — Exit loop with 15% max-loss safety net for positions without exit_levels
- `_reconstruct_position_state()` (line ~900) — Loads position state from broker with fallback ATR estimation
- `_build_decision_snapshot()` (line ~1100) — Captures full tick state for telemetry
- `initialize()` (line ~100) — Brain load, ML warmup, index initialization

**Key functions in `brain_persistence.py`:**
- `save()` — Atomic save of 13 state files (manifest, ML models, learning state, trades, equity, params, governance, regime)
- `load()` — Full state restoration with validation
- `validate_brain()` — NaN/Inf checks, weight normalization, model sanity
- `walk_forward_gate()` — Prevents saving regressed models

#### Signal Generation

| File | Lines | Purpose |
|------|-------|---------|
| `backend/organism/ml_signal.py` | 590 | XGBoost ensemble: direction classifier + magnitude regressor |
| `backend/organism/ml_features.py` | 448 | 79 ML features across 6 categories (price, volatility, trend, mean reversion, momentum, liquidity) |
| `backend/organism/alpha_scanner.py` | 239 | 7-factor composite alpha scoring, top-N candidate selection |
| `backend/organism/breakout_scanner.py` | 477 | 6-pattern breakout detection (squeeze, volume, contraction, RS, pivot, flow) |
| `backend/organism/composite_indicators.py` | 534 | 7 advanced composite indicators (squeeze momentum, volume-price divergence, trend alignment, institutional accumulation, mean reversion extremity, breakout readiness, momentum quality) |
| `backend/organism/ensemble_models.py` | 326 | Multi-model ensemble (XGBoost + Random Forest + LightGBM soft-vote) |

**ML Feature Categories (79 total):**
1. Price Action (15): returns, momentum acceleration, close-to-high/low, reversal strength
2. Volatility (10): ATR, realized vol, Parkinson/Garman-Klass vol, BB/KC width
3. Trend (12): SMA/EMA crossovers, MACD, slope, trend strength, breakout distance
4. Mean Reversion (10): RSI, Z-score, BB position, stochastics, oversold/overbought severity
5. Momentum (12): multi-period momentum, ADX, CCI, CMF, OBV, volume momentum
6. Liquidity/Volume (10): volume ratios, dollar volume, spread estimate, volume profile

**Alpha Scanner Weights:**
- ML Signal: 25%
- Breakout Score: 20%
- Institutional Score: 15%
- Momentum Score: 15%
- Momentum Quality: 10%
- Volume/Price Divergence: 10%
- Regime Alignment: 5%
- Minimum composite threshold: 0.15

#### Position Sizing & Exits

| File | Lines | Purpose |
|------|-------|---------|
| `backend/organism/kelly_sizer.py` | 390 | Half-Kelly sizing with drawdown scaling, vol targeting, regime conditioning, breakout bonus |
| `backend/organism/adaptive_exits.py` | 470 | ATR-based exits: stop-loss, take-profit, trailing stop, partial profit, time decay, stress tightening |
| `backend/organism/pyramider.py` | 267 | Adds to winning positions at continuation breakout levels (+1.5R, +3.0R) |

**Kelly Sizer Configuration:**
- Max position: 12% of portfolio
- Max portfolio: 95% invested
- Volatility target: 15% annualized
- Drawdown floor: 10% at max drawdown
- Max drawdown cutoff: 25% (full risk-off)
- Minimum position: $2,000
- Breakout bonus: 1.5x for score > 0.6, 2.0x for score > 0.8

**Adaptive Exit Levels:**
- Stop-loss: Regime-dependent ATR multiplier (trending: 2.5x, chop: 1.5x, stress: 1.0x)
- Take-profit: R-multiple target (trending: 4.0R, chop: 2.0R, stress: 1.5R)
- Trailing stop: Activates after 3x ATR favorable move, trails at regime-dependent ATR distance
- Partial profit: Sells 30% at 3R, rides remaining 70%
- Time decay: 1% per bar stop tightening after regime-specific bar count
- Stress tightening: 40% stop tightening on regime shift to STRESS/HIGH_VOL
- **Safety net: 15% max-loss emergency exit for ALL positions (even without exit_levels)**

#### Regime & Governance

| File | Lines | Purpose |
|------|-------|---------|
| `backend/organism/regime.py` | 647 | Multi-signal regime detection (7 regime labels), drift detection via KL divergence |
| `backend/organism/governance.py` | 250 | Kill switches, freeze/halt controls, drawdown kill, per-strategy disable, rate limiting |
| `backend/organism/promotion.py` | 412 | 6-stage promotion pipeline (SHADOW → PAPER → CANARY → RAMP → ACTIVE → ROLLED_BACK) |
| `backend/organism/sector_map.py` | 76 | GICS sector mapping + diversification gate (max 4 per sector) |

**Regime Labels:** TRENDING_UP, TRENDING_DOWN, CHOP, HIGH_VOL, LOW_VOL, STRESS, UNKNOWN

**Governance Controls:**
- Global freeze (stop all adaptation)
- Trading halt (stop all orders)
- Per-strategy disable
- Drawdown kill switch: 8% (configurable via `ORGANISM_DRAWDOWN_KILL_PCT`)
- Adaptive cooldown after drawdown trigger
- Rate limit: max 100 changes per day

#### Learning & Evolution

| File | Lines | Purpose |
|------|-------|---------|
| `backend/organism/continuous_learner.py` | 391 | Self-improvement engine: retraining based on drift detection and scheduled intervals |
| `backend/organism/background_trainer.py` | 412 | Background ML training in separate ProcessPoolExecutor |
| `backend/organism/transfer_learning.py` | 581 | Knowledge distillation across runs, regime-guided warm starts |
| `backend/organism/walk_forward.py` | 459 | Walk-forward evaluation: tests candidate vs baseline before promotion |
| `backend/organism/attribution.py` | 421 | Fill-based PnL attribution per strategy x symbol |
| `backend/organism/training.py` | 358 | Training orchestrator: data prep → attribution → candidate → walk-forward → promote |
| `backend/organism/feature_store.py` | 282 | Versioned feature snapshots with data quality checks |

**Evolution Parameters (all learnable):**
- Signal weights (ML, breakout, volume, momentum, regime per sub-score)
- Direction thresholds (confidence calibration)
- Exit parameters (ATR multipliers, R-targets)
- Regime-specific sizing scales
- Feature weights and pruning
- Symbol fitness scores
- Breakout indicator periods (BB, ATR, pivot lookback)
- Short-side controls

**Evolution Safety:**
- EMA smoothing (alpha=0.30) prevents sudden parameter jumps
- Max 20% parameter shift per epoch
- Minimum 8 trades required before adaptation
- Walk-forward gate prevents model regression

#### Telemetry & Monitoring

| File | Lines | Purpose |
|------|-------|---------|
| `backend/organism/decision_telemetry.py` | 412 | 7 dataclasses + ring buffer (360 ticks / ~1 hour) for full decision transparency |
| `backend/organism/market_scanner.py` | 473 | Scans Alpaca screener for most-actives and movers |
| `backend/organism/universe_selector.py` | 293 | Fitness-based symbol selection and rotation |
| `backend/organism/multi_timeframe.py` | 172 | Multi-timeframe feature engineering (5m/15m/60m) |
| `backend/organism/streaming_data_provider.py` | 268 | WebSocket-based real-time data provider |

**Decision Telemetry Dataclasses:**
1. `SymbolAlphaDetail` — 7-factor alpha breakdown per symbol
2. `SymbolBreakoutDetail` — 6-pattern breakout breakdown per symbol
3. `PositionExitDetail` — Exit proximity with distances and state flags
4. `RegimeProbabilitySnapshot` — Multi-regime probability vector
5. `KellySizingDetail` — Position size computation breakdown
6. `FilteringSummary` — Alpha/breakout filtering pipeline summary
7. `DecisionSnapshot` — Full tick snapshot combining all above

### 4.2 Services Layer (28 files, 14,862 lines)

**Active Services (2):**
| File | Lines | Purpose |
|------|-------|---------|
| `backend/services/order_service.py` | 1,701 | Order management, submission, cancellation, fill handling, retry logic |
| `backend/services/signal_service.py` | 74 | Signal caching layer (NOT a signal generator) |

**Deprecated/Blueprint Services (26):**
These modules exist as blueprints from earlier development phases. They are not actively used by the organism engine but contain functional code for potential future use:
- `backtest_service.py` (2,775 lines) — Full backtesting engine
- `indicators.py` (1,245 lines) — 50+ technical indicators
- `strategy_service.py` (892 lines) — Strategy CRUD + execution
- `risk_manager.py` (775 lines) — Risk calculations
- `audit_service.py` (586 lines) — Compliance audit trail
- `trade_analytics_service.py` (616 lines) — Trade analytics
- And 20 more modules

### 4.3 Integrations (7 files, ~3,500 lines)

| File | Lines | Purpose |
|------|-------|---------|
| `backend/integrations/alpaca_broker.py` | 881 | Primary broker: orders, positions, account info |
| `backend/integrations/alpaca_stream.py` | 705 | Trade stream WebSocket (order fills, executions) |
| `backend/integrations/alpaca_market_data_stream.py` | 697 | Market data WebSocket (quotes, bars) |
| `backend/integrations/alpaca_stream_production.py` | 563 | Production-hardened streaming with failover |
| `backend/integrations/alpaca_data.py` | 359 | Historical bars + snapshots |
| `backend/integrations/alpaca_outbox.py` | 298 | Reliable async order dispatch with retry |

**Recent Bug Fixes (this session):**
- Fixed WebSocket concurrency bug: dual `listen()` after reconnect caused `ConcurrencyError`
- Added `_cleanup_connection()` method for proper resource cleanup before reconnect
- Fixed `_start_background_tasks()` to prune dead tasks before adding new ones

### 4.4 Configuration (6 files, ~2,700 lines)

| File | Lines | Purpose |
|------|-------|---------|
| `backend/config/base_settings.py` | 1,481 | Comprehensive Pydantic config (app, security, Alpaca, DB, trading, risk, observability) |
| `backend/config/settings.py` | 750+ | Primary settings: 50+ fields across 10 subsystem configs |
| `backend/config/coordinator.py` | 246 | Multi-source config coordinator |
| `backend/config/unified.py` | 193 | Unified settings facade |
| `backend/config/config.py` | 160 | Legacy config (backward compatibility) |

### 4.5 Infrastructure (30+ files)

Key modules in `backend/infra/`:
- `db.py` — AsyncSession management, connection pooling
- `schemas.py` — SQLAlchemy ORM models (Order, Position, Trade, etc.)
- `security.py` — JWT authentication, password hashing
- `guardrails.py` — Order validation and risk checks
- `outbox.py` — Reliable message dispatch
- `metrics.py` — Prometheus metrics
- `repositories/` — Data access layer (orders, positions, strategies, signals, audits)

### 4.6 Models (Pydantic, 6 files, ~3,500 lines)

| File | Lines | Purpose |
|------|-------|---------|
| `backend/models/order_integrity.py` | 754 | Order state machine (FSM), idempotency, audit trail |
| `backend/models/ensemble_model.py` | 1,846 | ML ensemble framework |
| `backend/models/ml_models.py` | 511 | ML lifecycle Pydantic models |
| `backend/models/risk.py` | 199 | Risk management models |
| `backend/models/backtest.py` | 193 | Backtesting request/response models |

---

## 5. Frontend Code Inventory

### 5.1 Overview

- **Framework:** React 19.1 + TypeScript 5.9 + Vite 7.1
- **UI:** Ant Design 5.27 (dark theme)
- **State:** Zustand 5.0 + React Query 5.90
- **Charts:** Canvas-based custom charts + Lightweight Charts + Chart.js
- **Grid:** AG Grid Enterprise 34.2
- **Real-time:** Socket.IO client

### 5.2 Route Structure (12 protected routes)

| Path | Component | Feature |
|------|-----------|---------|
| `/` | Dashboard | Executive summary |
| `/organism` | OrganismDashboard | Living engine control center (7+ tabs) |
| `/ml-models` | MLModelsPage | Model lifecycle management |
| `/trading` | TradingPage | Order entry + pre-trade validation |
| `/orders` | OrdersPage | Active orders + history |
| `/positions` | PositionsPage | Live positions + heatmap |
| `/portfolio` | PortfolioPage | Equity, cash, P&L timeline |
| `/trades` | TradesPage | Trade history + institutional analytics |
| `/strategies` | StrategiesPage | Strategy CRUD + builder (5-step wizard) |
| `/backtesting` | BacktestingPage | Backtest form + results |
| `/risk` | RiskManagement | Risk dashboard + kill switch |
| `/market-data` | ScannerPage | Market scanner |
| `/settings` | SettingsPage | User preferences |

### 5.3 Feature Modules

#### Organism Dashboard (18 files, most complex feature)

The decision dashboard provides full transparency into every tick.

**Core Components:**
- `OrganismDashboard.tsx` (1,170 lines) — Main dashboard with tabs: Overview, Decisions, Runs, Activity, Scanner, Universe, Analytics, Learned State
- `DecisionDashboard.tsx` — Orchestrator with 10-second auto-refresh

**Decision Transparency Components (13 canvas-based + table):**
1. `DecisionHeader.tsx` — Summary stats (tick count, regime, signals, orders)
2. `GovernanceStatusBar.tsx` — Governance state, drawdown, halt status
3. `FilteringFunnel.tsx` — Alpha/breakout filtering pipeline visualization
4. `RegimeProbabilityPanel.tsx` — Regime probability vector display
5. `AlphaScoreTable.tsx` — Sortable table of 7-factor alpha scores per symbol
6. `ExitProximityTable.tsx` — Exit levels with colored distance progress bars
7. `SymbolDecisionDrawer.tsx` — Per-symbol detail (alpha radar + kelly waterfall + exits)
8. `AlphaFactorRadar.tsx` — Canvas spider chart for 7 alpha factors
9. `BreakoutFactorRadar.tsx` — Canvas spider chart for 6 breakout patterns
10. `KellyPipelineWaterfall.tsx` — Canvas waterfall (kelly raw → half → drawdown → vol → regime → final)
11. `ExitProximityGauges.tsx` — Canvas gauge charts per exit condition
12. `EvolutionTimeline.tsx` — Canvas dual chart (generation vs equity/drawdown over time)
13. `RegimeTimeline.tsx` — Regime change history visualization
14. `AttributionChart.tsx` — Sector exposure + confidence distribution

**API Endpoints Consumed:**
```
GET /organism/status, /organism/decisions, /organism/decisions/history
GET /organism/decisions/symbol/:sym, /organism/decisions/exits
GET /organism/evolution/history, /organism/attribution
GET /organism/runs, /organism/policy, /organism/brain
GET /organism/scanner, /organism/universe, /organism/analytics
POST /organism/{freeze|unfreeze|halt|resume|train|tick}
```

#### ML Models (13 files)

Components: ModelRegistry (search/filter), ModelCard (status/metrics), TrainingForm (submit training), TrainingProgressMonitor (real-time progress), PerformanceCharts, FeatureImportance, ModelComparison, LifecycleDashboard

#### Strategies (10 files)

5-step wizard: BasicInfo → Parameters → RiskLimits → ExecutionSettings → Review

#### Trading, Orders, Positions, Portfolio, Risk, Backtesting

Standard CRUD + visualization components with real-time WebSocket updates.

### 5.4 State Management (6 Zustand stores)

| Store | Data |
|-------|------|
| `authStore` | user, accessToken, refreshToken, isAuthenticated |
| `portfolioStore` | portfolio, positions, totalEquity, cash, dayPnL |
| `ordersStore` | orders (map), activeOrders, history |
| `strategiesStore` | strategies, selectedId |
| `marketDataStore` | quotes, trades, bars (maps) |
| `uiStore` | theme, sidebarVisible, modals |

### 5.5 Services (15 API service files)

All services use Axios with JWT Bearer auth, automatic 401 token refresh, and error extraction.

| Service | Endpoints |
|---------|-----------|
| `api.ts` | Base Axios instance + interceptors |
| `authService.ts` | /auth/* (login, register, refresh) |
| `ordersService.ts` | /orders/* (submit, cancel, validate) |
| `portfolioService.ts` | /portfolio/* (positions, history) |
| `mlApi.ts` | /ml-models/* (training, monitoring, lifecycle) |
| `riskApi.ts` | /risk/* (metrics, limits, emergency stop) |
| `websocketManager.ts` | Socket.IO connection + subscriptions |

### 5.6 Type Definitions (12 files)

Comprehensive TypeScript interfaces covering all domain objects: User, Order, Position, Portfolio, Trade, Strategy, ModelInfo, RiskMetric, BacktestResult, WebSocket messages, and more.

---

## 6. Infrastructure & Deployment

### 6.1 Docker Compose (5 services)

| Service | Image | Port | Health Check |
|---------|-------|------|-------------|
| api | python:3.12-slim (multi-stage) | 8000 | GET /healthz (30s interval) |
| db | PostgreSQL 16-alpine | 127.0.0.1:5432 | pg_isready (10s interval) |
| redis | Redis 7-alpine | 127.0.0.1:6379 | redis-cli ping (10s interval) |
| otel-collector | OpenTelemetry (optional) | 4317, 4318 | — |
| prometheus | Prometheus (optional) | 9090 | — |
| grafana | Grafana (optional) | 3000 | — |

**PostgreSQL Tuning:**
- shared_buffers=256MB, work_mem=16MB, effective_cache_size=768MB
- statement_timeout=30000ms, idle_in_transaction_session_timeout=60000ms
- log_min_duration_statement=500ms (slow query logging)

**Redis Configuration:**
- appendonly yes (persistence)
- maxmemory=256mb, allkeys-lru eviction
- Password-protected

### 6.2 Dockerfiles

**Development (`Dockerfile`):**
- Multi-stage build (builder + runtime)
- Non-root user (appuser, uid 10001)
- 1 Uvicorn worker with access logging
- Entry via `docker-entrypoint.sh`

**Production (`Dockerfile.production`):**
- Non-root user (appuser, uid 1000)
- 4 Uvicorn workers with uvloop + httptools
- Minimal runtime deps (libpq5, curl only)

### 6.3 CI/CD (GitHub Actions)

**ci.yml — Quality Gates:**
1. Lint (ruff check + format)
2. Type check (mypy strict)
3. Security (bandit HIGH, pip-audit, safety)
4. Test + Coverage (pytest with PostgreSQL + Redis services)
   - Coverage minimum: 80%
   - Diff coverage: 95%
   - Coverage ratcheting: no decrease vs main (2% tolerance)

**staging.yml — Staging Deployment:**
1. Test → 2. Docker build + push to GHCR → 3. K8s deploy → 4. Smoke tests

**security-scan.yml — Container Security:**
- Trivy Dockerfile scanning (MEDIUM+ severity)
- Filesystem/IaC scanning (vuln, secret, misconfig)
- SBOM generation (CycloneDX)

### 6.4 Key Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `ORGANISM_ENABLED` | 0 | Enable organism engine |
| `ORGANISM_TICK_INTERVAL_SECONDS` | 10 | Tick frequency |
| `ORGANISM_MAX_POSITIONS` | 15 | Max concurrent positions |
| `ORGANISM_DRAWDOWN_KILL_PCT` | 0.08 | 8% drawdown kill switch |
| `ORGANISM_LONG_ONLY` | true | Long-only trading |
| `ORGANISM_RETRAIN_INTERVAL` | 180 | Retraining interval (seconds) |
| `ORGANISM_ML_DECAY_RATE` | 0.005 | Feature recency decay |
| `ORGANISM_MAX_PER_SECTOR` | 4 | Sector diversification limit |
| `ALPACA_PAPER` | true | Paper trading mode |
| `JWT_SECRET_KEY` | (required) | JWT signing key |
| `DATABASE_URL` | (required) | PostgreSQL connection string |

---

## 7. Test Coverage & Quality

### 7.1 Backend Test Summary

**Total: 7,021 passed, 684 skipped, 0 failed**

| Category | Files | Description |
|----------|-------|-------------|
| Organism Engine | 4 | `test_decision_telemetry.py` (23 tests), `test_organism_live_engine.py` (26 tests), `test_organism_integration_smoke.py`, `test_organism_blueprint_persistence.py` |
| Risk Management | 12 | Comprehensive risk calculations, guardrails, edge cases |
| Orders & Execution | 8 | Lifecycle, pipeline, validation, guardrails |
| Portfolio & Positions | 10 | Reconciliation, sync, import, management |
| Market Data | 10 | Service, scanner, analytics, quotes |
| ML Pipeline | 12 | Training, prediction, drift detection, ensemble |
| Database | 6 | Comprehensive DB, models, cache, Redis HA |
| API Routes | 10 | Endpoint validation, coverage, integration |
| Security | 10 | Credentials, boundaries, hardening, pickle |
| Observability | 8 | Logging, metrics, tracing, SLO |
| Integration/E2E | 12 | System integration, resilience, idempotency |
| Auto-generated | 161 | Module-level unit tests for all backend modules |

**Conftest Fixtures:**
- Main: 8 fixtures (mock DB, test client, JWT token, auth headers)
- Real tests: 19 fixtures (PostgreSQL, Alpaca paper broker, factories)

### 7.2 Frontend Test Summary

**Total: 134 passed, 0 failed (18 test files)**

| Feature | Files | Tests | Status |
|---------|-------|-------|--------|
| Organism Dashboard | 10 | 90 | All passing |
| ML Models | 3 | 28 | All passing (ModelCard, ModelRegistry, TrainingForm) |
| Trades | 1 | 15 | All passing (InstitutionalMetricsDisplay) |
| Strategies | 1 | ~2 | All passing |
| Backtesting | 1 | ~5 | All passing |
| **Total** | **18** | **134** | **All passing** |

### 7.3 Coverage Gaps

#### Backend — Organism Modules Without Dedicated Tests (13 modules)

These modules have indirect coverage through integration tests but no dedicated unit test files:

| Module | Lines | Risk Level | Notes |
|--------|-------|-----------|-------|
| `background_trainer.py` | 412 | Medium | Covered by live engine integration tests |
| `continuous_learner.py` | 391 | Medium | Covered by integration tests |
| `ensemble_models.py` | 326 | Medium | Has auto-generated tests |
| `multi_timeframe.py` | 172 | Low | Simple feature engineering |
| `nightly_scheduler.py` | 158 | Low | Scheduling wrapper |
| `promotion.py` | 412 | High | **Complex state machine, needs dedicated tests** |
| `pyramider.py` | 267 | Medium | Position pyramiding logic |
| `runner.py` | 154 | Low | Thin coordination layer |
| `scheduler.py` | 373 | Low | Scheduling wrapper |
| `self_evolution.py` | 1,200 | **High** | **Complex parameter evolution, needs dedicated tests** |
| `streaming_data_provider.py` | 268 | Medium | WebSocket wrapper |
| `training.py` | 358 | Medium | Training orchestrator |
| `transfer_learning.py` | 581 | Medium | Knowledge distillation |

**Priority items:** `self_evolution.py` (1,200 lines) and `promotion.py` (412 lines) are complex state machines that should have dedicated test suites.

#### Frontend — Untested Components (~49 components)

| Category | Count | Components |
|----------|-------|------------|
| Organism | 9 | DecisionDashboard, UniversePanel, ScannerPanel, ExitProximityGauges, and 5 more |
| ML Models | 8 | AnalyticsLazy, FeatureImportance, LifecycleDashboard, ModelComparison, PerformanceCharts, TrainingProgressMonitor, ModelCard_Mobile, MLModelsPage |
| Trading/Orders | 9 | OrderEntryPanel, OrderPreview, PreTradeChecks, ActiveOrdersTable, etc. |
| Backtesting | 6 | BacktestForm, BacktestResults, EquityCurveChart, MetricsTable, TradeLogTable |
| Strategies | 2 | StrategyForm, StrategyBuilderPage |
| Core | 3 | Dashboard, LoginPage, RegisterPage |

---

## 8. Security Posture

### 8.1 Authentication & Authorization

- **JWT-based auth** with HS256 signing, 60-minute token expiration
- Secure cookie enforcement in production
- Password hashing via bcrypt
- Token refresh mechanism with 401 interceptor queue
- Protected routes require valid JWT in Authorization header

### 8.2 Infrastructure Security

- PostgreSQL bound to localhost only (127.0.0.1:5432)
- Redis password-protected
- Non-root Docker containers (appuser with limited uid)
- Minimal runtime dependencies in production image
- All secrets in .env files (gitignored)

### 8.3 CI/CD Security Scanning

- **Bandit**: Python security scan (HIGH severity)
- **pip-audit**: Dependency vulnerability scan
- **Trivy**: Container image scanning (MEDIUM+ severity, SARIF to GitHub Security)
- **SBOM**: CycloneDX generation (90-day retention)

### 8.4 Application Security

- Input validation via Pydantic models
- Order guardrails (size limits, symbol validation, buying power checks)
- Rate limiting middleware
- CORS whitelist (configurable origins)
- Sensitive data scrubbing in logs
- Structured logging with audit trail

### 8.5 Security Concerns for Review

| Concern | Severity | Details |
|---------|----------|---------|
| JWT_SECRET_KEY management | Medium | Must be generated per environment, no key rotation mechanism |
| Database credentials | Medium | Stored in .env, no vault integration |
| API rate limiting | Low | Middleware exists but limits may need tuning for production |
| WebSocket auth | Low | Socket.IO uses JWT token passed at connection time |
| Alpaca API keys | Medium | Stored in .env, paper mode only currently |

---

## 9. Known Issues & Technical Debt

### 9.1 Bugs Fixed This Session (2026-02-21)

| # | Issue | Fix | File |
|---|-------|-----|------|
| 1 | WebSocket dual `listen()` after reconnect causing ConcurrencyError | Added `_cleanup_connection()`, removed duplicate `asyncio.create_task(self.listen())` | `alpaca_market_data_stream.py` |
| 2 | Connection limit exceeded (no cleanup before reconnect) | `_cleanup_connection()` cancels stale tasks, closes WebSocket before reconnect | `alpaca_market_data_stream.py` |
| 3 | ANPA position at -27.5% (should have been stopped at -15%) | Added 15% max-loss safety net for ALL positions even without exit_levels | `live_engine.py:698` |
| 4 | Engine shows 0 positions tracked after restart (failed data fetch) | Added fallback ATR estimation (2% of entry) when historical data unavailable | `live_engine.py:900` |
| 5 | 78 frontend test failures across 4 files | Rewrote ModelCard, ModelRegistry, TrainingForm, InstitutionalMetricsDisplay tests | `__tests__/*.test.tsx` |

### 9.2 Known Technical Debt

| Item | Severity | Description | File(s) |
|------|----------|-------------|---------|
| **Deprecated services** | Low | 26 service modules are deprecated blueprints, not actively used | `backend/services/` |
| **database.py legacy** | Low | 627-line deprecated DB module kept for test compatibility | `backend/database.py` |
| **Config duplication** | Medium | 4+ config modules with overlapping concerns | `backend/config/` |
| **factory.py size** | Low | API factory still ~1,130 lines (target was <500) | `backend/api/factory.py` |
| **Alembic migrations empty** | Medium | No versioned migrations; schema managed through ORM or manual SQL | `backend/migrations/versions/` |
| **Frontend E2E tests missing** | Medium | No Cypress/Playwright integration tests | — |
| **No dark/light mode toggle** | Low | Dark theme hardcoded, no user toggle | Frontend |
| **Canvas in jsdom** | Low | Canvas tests produce warnings (jsdom doesn't implement getContext) | Tests still pass |
| **Security reports outdated** | Medium | Old Jan 18, 2026 reports removed; fresh scans needed | `reports/` |

### 9.3 Production Gotchas (Documented)

These are confirmed behaviors discovered during paper trading:

1. **Logging**: Uses standard `logging.getLogger()` NOT structlog (despite structlog infrastructure)
2. **Env vars in Docker**: `.env` is gitignored; organism vars must be in `docker-compose.yml`
3. **Portfolio store types**: Position uses camelCase (unrealizedPnL, currentPrice, quantity)
4. **Portfolio positions**: `Position[]` array, NOT Record — use `.map()` not `Object.values()`
5. **Alpaca v2 trade stream**: Order data nested under `data.order`, NOT `data`
6. **DB sessions in background tasks**: Use `get_session_context()` NOT `get_db_session()`
7. **NaN propagation**: Beta/correlation ranking have NaN guards
8. **`_reconstruct_position_state`**: Skips symbols with brain-restored exit levels
9. **numpy types in JSON**: FastAPI can't serialize numpy.bool_/float64 — use `_f()`/`_b()` helpers
10. **Canvas in tests**: jsdom doesn't implement getContext() — canvas tests show warnings but pass

---

## 10. Go-Live Readiness Checklist

### 10.1 Ready (Completed)

- [x] Core trading engine functional and paper trading successfully
- [x] 15 positions managed simultaneously with sector diversification
- [x] Adaptive exits with 15% max-loss safety net
- [x] Brain persistence and state restoration across restarts
- [x] Decision telemetry with full tick-by-tick transparency
- [x] Governance controls (freeze, halt, drawdown kill at 8%)
- [x] 7,021 backend tests passing, 134 frontend tests passing
- [x] Docker containerization with health checks
- [x] CI/CD pipeline with lint, type check, security scan, coverage gates
- [x] JWT authentication with token refresh
- [x] WebSocket real-time updates
- [x] Market scanner for dynamic universe rotation
- [x] Fallback ATR estimation when historical data unavailable
- [x] WebSocket reconnection with proper resource cleanup

### 10.2 Recommended Before Live Trading

| Item | Priority | Effort | Description |
|------|----------|--------|-------------|
| **Dedicated tests for self_evolution.py** | High | 2-3 days | 1,200-line parameter evolution engine with no dedicated test suite |
| **Dedicated tests for promotion.py** | High | 1-2 days | Complex 6-stage state machine needs dedicated coverage |
| **Database migration versioning** | High | 1 day | Implement Alembic versioned migrations for schema changes |
| **Secret management** | High | 1-2 days | Move from .env to vault (HashiCorp, AWS Secrets Manager, or similar) |
| **JWT key rotation** | Medium | 1 day | Add key rotation mechanism |
| **Fresh security scans** | Medium | 1 day | Run bandit, pip-audit, Trivy, npm audit with current codebase |
| **E2E tests (critical paths)** | Medium | 3-5 days | Cypress/Playwright for login → order → fill → exit flow |
| **Position reconciliation audit** | Medium | 1 day | Verify Alpaca positions match engine state after prolonged running |
| **Order replay testing** | Medium | 2 days | Simulate order failures, partial fills, rejected orders |
| **Drawdown kill recovery** | Medium | 1 day | Test the engine recovery flow after drawdown kill triggers |
| **Production Dockerfile validation** | Low | 1 day | Validate Dockerfile.production builds and runs correctly |
| **Monitoring stack activation** | Low | 1 day | Enable Prometheus + Grafana in Docker Compose |
| **Load testing** | Low | 2 days | Verify system handles high-frequency ticks without degradation |

### 10.3 Live Trading Configuration Changes Required

```env
# Switch from paper to live
ALPACA_PAPER=false
ALPACA_BASE_URL=https://api.alpaca.markets

# Production security
JWT_SECRET_KEY=<newly-generated-strong-secret>
POSTGRES_PASSWORD=<strong-unique-password>
REDIS_PASSWORD=<strong-unique-password>

# Conservative starting config
ORGANISM_MAX_POSITIONS=5          # Start with fewer positions
ORGANISM_DRAWDOWN_KILL_PCT=0.05   # Tighter 5% drawdown limit
ORGANISM_TICK_INTERVAL_SECONDS=30  # Slower tick rate initially
```

---

## 11. Recommendations

### 11.1 Critical (Must-Have for Live Trading)

1. **Add dedicated tests for `self_evolution.py`** — This 1,200-line module evolves ALL tunable parameters. A bug here silently degrades trading performance. Test parameter clamping, EMA smoothing, minimum trade requirements, and regime-specific adaptation.

2. **Add dedicated tests for `promotion.py`** — The 6-stage promotion pipeline controls when new models go live. Test stage transitions, rollback triggers, budget caps, and metric thresholds.

3. **Implement database migrations** — Currently no versioned Alembic migrations. Any schema change risks data loss. Set up proper migration chain.

4. **Move secrets to vault** — API keys, JWT secret, and DB credentials are in .env files. For live trading, use HashiCorp Vault, AWS Secrets Manager, or similar.

### 11.2 High Priority (Should-Have)

5. **Run fresh security scans** — The old Jan 18 reports were removed. Run bandit, pip-audit, Trivy, and npm audit with current codebase and resolve any HIGH/CRITICAL findings.

6. **Add E2E tests for critical trading paths** — At minimum: login → submit order → order fills → position appears → exit triggers → trade recorded.

7. **Position reconciliation audit** — After prolonged paper trading, verify that engine positions exactly match Alpaca positions. Check for phantom positions or missing positions.

8. **Verify order failure recovery** — Submit orders during market close, test timeout handling, simulate broker API failures. Ensure no orders are lost or duplicated.

### 11.3 Medium Priority (Nice-to-Have)

9. **Config consolidation** — 4+ config modules with overlapping concerns. Consolidate to single source of truth.

10. **Deprecated services cleanup** — 26 deprecated service modules add confusion. Either remove or clearly segregate them.

11. **Frontend E2E testing** — Cypress/Playwright for key user flows.

12. **Monitoring activation** — Enable Prometheus + Grafana stack and set up alerts for key metrics (tick duration, error rate, P&L drawdown).

13. **Load testing** — Verify system handles rapid market data during high-volatility periods.

### 11.4 Improvement Opportunities

14. **Multi-account support** — Currently single-account. For scale, support multiple trading accounts/strategies.

15. **Alert system** — Email/Slack notifications for drawdown triggers, system errors, trade executions.

16. **Backfill strategy** — When engine restarts mid-day, backfill missed ticks instead of waiting for next tick.

17. **A/B testing framework** — Run two parameter sets simultaneously on different symbol subsets to empirically compare.

---

## 12. File Reference Index

### Key Files for Reviewer (Start Here)

| Purpose | File Path |
|---------|-----------|
| **Main entry point** | `backend/api/main.py` |
| **Core tick loop** | `backend/organism/live_engine.py` |
| **ML signal generation** | `backend/organism/ml_signal.py` |
| **Feature engineering** | `backend/organism/ml_features.py` |
| **Alpha scoring** | `backend/organism/alpha_scanner.py` |
| **Breakout detection** | `backend/organism/breakout_scanner.py` |
| **Position sizing** | `backend/organism/kelly_sizer.py` |
| **Adaptive exits** | `backend/organism/adaptive_exits.py` |
| **Regime detection** | `backend/organism/regime.py` |
| **Parameter evolution** | `backend/organism/self_evolution.py` |
| **Brain persistence** | `backend/organism/brain_persistence.py` |
| **Governance controls** | `backend/organism/governance.py` |
| **Decision telemetry** | `backend/organism/decision_telemetry.py` |
| **API routes** | `backend/organism/routes.py` |
| **Broker integration** | `backend/integrations/alpaca_broker.py` |
| **WebSocket stream** | `backend/integrations/alpaca_market_data_stream.py` |
| **Order service** | `backend/services/order_service.py` |
| **Frontend dashboard** | `frontend/src/features/organism/OrganismDashboard.tsx` |
| **Frontend API** | `frontend/src/features/organism/organismApi.ts` |
| **Docker config** | `docker-compose.yml` |
| **CI/CD pipeline** | `.github/workflows/ci.yml` |
| **Environment template** | `.env.example` |

### Documentation

| Document | Path |
|----------|------|
| Platform overview | `README.md` |
| Complete guide | `docs/PLATFORM_COMPLETE_GUIDE.md` |
| Architecture | `docs/architecture/SYSTEM_OVERVIEW.md` |
| Organism blueprint | `docs/blueprints/EVOLVING_ORGANISM_BLUEPRINT.md` |
| Platform status | `docs/PLATFORM_STATUS.md` |
| Quick start | `docs/setup/QUICK_START.md` |
| Operations | `docs/operations/OPERATIONAL_CADENCE.md` |
| Incident response | `docs/runbooks/INCIDENT_RESPONSE.md` |
| Test strategy | `docs/testing/TEST_STRATEGY.md` |

### Test Files

| Test Suite | Path |
|------------|------|
| Organism live engine | `tests/test_organism_live_engine.py` |
| Decision telemetry | `tests/test_decision_telemetry.py` |
| Integration smoke | `tests/test_organism_integration_smoke.py` |
| Brain persistence | `tests/test_organism_blueprint_persistence.py` |
| Frontend organism | `frontend/src/features/organism/__tests__/` |
| Frontend ML models | `frontend/src/features/ml-models/components/__tests__/` |

---

## Appendix A: Recent Commit History

```
a1713d7 Fix numpy type serialization in decision telemetry to_dict() methods
3512916 Add decision telemetry dashboard: full transparency into tick-by-tick decisions
30f064a Weekend overhaul: 7 algorithm improvements, 5 UI components, 80 new tests
16dfc4e Add integration smoke tests, invariant assertions, and fix 4 audit bugs
ff6778d Fix state persistence bugs: restore tick counters and exit levels from brain
7045aeb Fix 7 critical live trading bugs: exits, fitness gate, order spam, retraining
bcd0a0f Fix governance: env vars take precedence over persisted state for limits
d90f445 Fix three live trading bugs: duplicate orders, trade stream parsing, and DB session
6492a6b Fix streaming provider: logger kwargs, WebSocket auth, and pass organism env vars
76b969d Production readiness audit: fix 12 verified bugs across engine, ML, and integrations
f1d9200 Phase 1: activate streaming data with REST pre-fill to eliminate cold start
0160b9a Pre-market audit: fix 11 production bugs, replace mock guardrail prices with live quotes
```

## Appendix B: Organism Engine Configuration (Current .env)

```
ORGANISM_TICK_INTERVAL_SECONDS=10
ORGANISM_LIVE_TIMEFRAME=1Min
ORGANISM_MAX_POSITIONS=15
ORGANISM_LONG_ONLY=true
ORGANISM_RETRAIN_INTERVAL=180
ORGANISM_ML_DECAY_RATE=0.005
ORGANISM_MAX_PER_SECTOR=4
ORGANISM_DRAWDOWN_KILL_PCT=0.08
ALPACA_PAPER=true
# 30 symbols in universe
```

## Appendix C: Deprecated Services Inventory

The following 26 service modules in `backend/services/` are deprecated blueprints (per `services/__init__.py`). They are NOT used by the organism engine:

| Module | Lines | Purpose |
|--------|-------|---------|
| backtest_service.py | 2,775 | Backtesting engine |
| indicators.py | 1,245 | Technical indicators |
| strategy_service.py | 892 | Strategy management |
| risk_manager.py | 775 | Risk calculations |
| market_data_service.py | 666 | Market data aggregation |
| trade_analytics_service.py | 616 | Trade analytics |
| cache.py | 589 | Multi-layer Redis cache |
| audit_service.py | 586 | Compliance audit trail |
| trade_service.py | 535 | Trade tracking |
| observability_service.py | 520 | Metrics & observability |
| slippage_model.py | 455 | Execution cost modeling |
| multi_strategy_live_runner.py | 429 | Multi-strategy execution |
| portfolio_service.py | 365 | Portfolio tracking |
| quote_manager.py | 351 | Real-time quote cache |
| lot_tracker_service.py | 321 | Position lot tracking |
| position_reconciliation_service.py | 245 | Position reconciliation |
| multi_strategy_live_scheduler.py | 229 | Strategy scheduling |
| auto_breakout_scanner.py | 224 | Breakout scanning |
| positions_service.py | 216 | Position management |
| scheduled_reconciliation.py | 203 | Periodic reconciliation |
| symbol_validator.py | 183 | Symbol validation |
| portfolio_sync_service.py | 168 | Alpaca → DB sync |
| position_import_service.py | 223 | External position import |
| trading_execution_mode.py | 142 | Runtime mode override |
| auto_breakout_scanner_scheduler.py | 101 | Breakout scan scheduling |

---

*End of report. This document should be read alongside the actual repository code for a complete audit.*
