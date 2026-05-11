# INTRA PLATFORM — COMPLETE SYSTEM MAP

> Every system, every flow, every threshold, every decision path. From raw market data to trade execution, from infrastructure to ML deployment.

---

## CURRENT PAPER RUNTIME NOTE (2026-05-06)

This file is the long-form architecture map. For the latest deploy truth, use
`docs/engineering/PHASE7_CLOSE_REPORT.md`, `docs/engineering/LIVE_AUDIT_INDEX.md`,
and the generated artifact pack first.

Current Phase 7 Track A close state:

- Branch: `codex/v13-phase2-expectancy`.
- Paper API container: `intra-api-1`.
- Paper DB container: `trading_platform_db_paper`.
- Redis container: `intra-redis-1`.
- Runtime SHA checked: `3fb3dd506e9e375205505cd11e126fe28bc355d4`.
- Build time checked: `2026-05-06T16:16:32Z`.
- Migration head: `20260503_000003`.
- Phase 5 and Phase 6 telemetry are enabled in shadow/advisory mode.
- Current strategy health is negative: PnL `-793.3359`, win rate `0.3327`,
  Sharpe `-1.3959`; no strategy promotion is justified by this map.
- Last post-deploy validation snapshot had `PSQ:60` open and data-integrity
  warning `realized=954`, `brain=527`; intraday counts can move.

---

## TABLE OF CONTENTS

### Layer 1: Architecture Overview
1. [System Architecture](#1-system-architecture)

### Layer 2: Trading Algorithm — Tick Lifecycle
2. [Tick Lifecycle Overview](#2-tick-lifecycle-overview)
3. [Phase 0: Preamble & Housekeeping](#3-phase-0-preamble--housekeeping)
4. [Phase 1: Governance Gate](#4-phase-1-governance-gate)
5. [Phase 2: Data Acquisition & Feature Engineering](#5-phase-2-data-acquisition--feature-engineering)
6. [Phase 3: Regime Detection](#6-phase-3-regime-detection)
7. [Phase 4: Portfolio State & Drawdown](#7-phase-4-portfolio-state--drawdown)
8. [Phase 5: Exit Decisions](#8-phase-5-exit-decisions)
9. [Phase 6: Pyramid Checks](#9-phase-6-pyramid-checks)
10. [Phase 7: New Entry Scanning](#10-phase-7-new-entry-scanning)
11. [Phase 8: Kelly Position Sizing](#11-phase-8-kelly-position-sizing)
12. [Phase 9: Order Submission](#12-phase-9-order-submission)
13. [Phase 10: Fill Reconciliation](#13-phase-10-fill-reconciliation)
14. [Phase 11: Retrain & Evolve](#14-phase-11-retrain--evolve)
15. [Phase 12: Brain Persistence](#15-phase-12-brain-persistence)

### Layer 3: Algorithm Deep Dives
16. [ML Signal Generation](#16-ml-signal-generation)
17. [Feature Engineering (79 Features)](#17-feature-engineering-79-features)
18. [Alpha Scanner](#18-alpha-scanner)
19. [Breakout Scanner](#19-breakout-scanner)
20. [Kelly Sizer](#20-kelly-sizer)
21. [Adaptive Exit Engine](#21-adaptive-exit-engine)
22. [Regime Detector](#22-regime-detector)
23. [Self-Evolution Engine](#23-self-evolution-engine)
24. [Universe & Sector Management](#24-universe--sector-management)
25. [Background Training & Transfer Learning](#25-background-training--transfer-learning)
25a. [Decision Telemetry](#25a-decision-telemetry)
25b. [Replay Simulator](#25b-replay-simulator)
25c. [Ensemble Models](#25c-ensemble-models)
25d. [Composite Indicators](#25d-composite-indicators)
25e. [Feature Store](#25e-feature-store)
25f. [Multi-Timeframe Features](#25f-multi-timeframe-features)

### Layer 4: External Integration — Alpaca Broker
26. [Order Submission Pipeline](#26-order-submission-pipeline)
27. [Outbox Dispatcher](#27-outbox-dispatcher)
28. [Idempotency & Deduplication](#28-idempotency--deduplication)
29. [WebSocket Trade Updates](#29-websocket-trade-updates)
30. [Market Data Stream](#30-market-data-stream)
31. [Historical Data & Positions](#31-historical-data--positions)
31a. [Production Stream Client](#31a-production-stream-client)

### Layer 5: Infrastructure
32. [Transactional Outbox & DLQ](#32-transactional-outbox--dlq)
33. [Order Guardrails](#33-order-guardrails)
34. [Resilience Layer](#34-resilience-layer)
35. [Alert System](#35-alert-system)
36. [Database Schema](#36-database-schema)
37. [Observability Stack](#37-observability-stack)

### Layer 6: ML Deployment Pipeline
38. [Promotion Controller](#38-promotion-controller)
39. [Training Orchestrator](#39-training-orchestrator)
40. [Nightly Scheduler](#40-nightly-scheduler)
41. [Attribution Service](#41-attribution-service)
42. [Walk-Forward Evaluator](#42-walk-forward-evaluator)

### Layer 7: Operations
43. [Docker Orchestration](#43-docker-orchestration)
44. [Engine Startup Sequence](#44-engine-startup-sequence)
45. [Streaming Data Provider](#45-streaming-data-provider)
46. [Diagnostic System](#46-diagnostic-system)
47. [API Surface & Security](#47-api-surface--security)
48. [Brain Persistence & Caching](#48-brain-persistence--caching)

### Layer 8: Platform Services & Architecture
49. [Dual-Path Engine Architecture](#49-dual-path-engine-architecture)
50. [Multi-Strategy Live System](#50-multi-strategy-live-system)
51. [Services Layer](#51-services-layer)
52. [Dual WebSocket Stacks](#52-dual-websocket-stacks)
53. [Trading Execution Mode](#53-trading-execution-mode)
54. [Redis Architecture](#54-redis-architecture)
55. [Risk Management System](#55-risk-management-system)
56. [Inter-Module Dependency Map](#56-inter-module-dependency-map)

### Layer 9: ML Infrastructure (backend/ml/)
57. [ML Pipeline Architecture](#57-ml-pipeline-architecture)
58. [Feature Engineering & Data Processing](#58-feature-engineering--data-processing)
59. [Model Training & Validation](#59-model-training--validation)
60. [Model Registry & Lifecycle](#60-model-registry--lifecycle)
61. [Ensemble Framework & Prediction Service](#61-ensemble-framework--prediction-service)
62. [Drift Detection & Monitoring](#62-drift-detection--monitoring)

### Appendices
A. [Configuration Reference](#a-configuration-reference)
B. [Key Thresholds Summary](#b-key-thresholds-summary)
C. [Data Flow Summary](#c-data-flow-summary)
D. [Error Handling Hierarchy](#d-error-handling-hierarchy)
E. [Module Index](#e-module-index)
F. [Full API Route Reference](#f-full-api-route-reference)
G. [ORM Models & Configuration](#g-orm-models--configuration)

---

# LAYER 1: ARCHITECTURE OVERVIEW

## 1. SYSTEM ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              INTRA PLATFORM                                      │
│                                                                                  │
│  ┌──────────────────────────┐    ┌────────────────────────────────────────────┐  │
│  │   FRONTEND (React/Vite)  │    │          BACKEND (FastAPI)                 │  │
│  │   Port 5173 (dev)        │    │          Port 8000                         │  │
│  │                          │    │                                            │  │
│  │  Ant Design UI           │◄──►│  REST API (/api/v1/*, 210+ endpoints)     │  │
│  │  Decision Dashboard      │    │  Socket.IO (order/portfolio updates)       │  │
│  │  Diagnostics Panel       │    │  WebSocket Manager (market data/scanner)   │  │
│  │  Organism Dashboard      │    │                                            │  │
│  └──────────────────────────┘    │  ┌──────── DUAL ENGINE PATHS ──────────┐  │  │
│                                   │  │                                      │  │  │
│                                   │  │  PATH A: OrganismScheduler           │  │  │
│                                   │  │    ENABLE_ORGANISM_SCHEDULER=1       │  │  │
│                                   │  │    OrganismLiveEngine tick loop (10s)│  │  │
│                                   │  │    ML → Alpha → Kelly → Exits        │  │  │
│                                   │  │                                      │  │  │
│                                   │  │  PATH B: MultiStrategyLiveScheduler  │  │  │
│                                   │  │    MULTI_STRATEGY_LIVE_ENABLED=1     │  │  │
│                                   │  │    10 independent strategies (300s)  │  │  │
│                                   │  │    OrganismRunner governance hooks   │  │  │
│                                   │  │                                      │  │  │
│                                   │  │  *** MUTUALLY EXCLUSIVE ***          │  │  │
│                                   │  └──────────────────────────────────────┘  │  │
│                                   │                                            │  │
│                                   │  ┌──────────────────────────────────────┐  │  │
│                                   │  │  SERVICES (services/, 27 modules)    │  │  │
│                                   │  │  OrderService → Outbox → Broker      │  │  │
│                                   │  │  Risk, Analytics, Audit, Lots, Cache │  │  │
│                                   │  └──────────────────────────────────────┘  │  │
│                                   │                                            │  │
│                                   │  ┌──────────────────────────────────────┐  │  │
│                                   │  │  INFRASTRUCTURE (infra/)              │  │  │
│                                   │  │  Outbox → Guardrails → Resilience     │  │  │
│                                   │  │  Auth (JWT) → Alerting → Metrics      │  │  │
│                                   │  └──────────────────────────────────────┘  │  │
│                                   └────────────────────────────────────────────┘  │
│                                                                                  │
│  ┌──────────────────────────┐    ┌──────────────────────────────────────────┐    │
│  │   PostgreSQL 16          │    │   Redis 7                                │    │
│  │   Docker (paper DB)      │    │   Docker (intra-redis-1)                │    │
│  │   Port 5432 (localhost)  │    │   Port 6379 (localhost)                 │    │
│  │   DB: algotrading        │    │   256MB maxmemory                       │    │
│  │   User: trading          │    │   allkeys-lru eviction                  │    │
│  │   27 tables              │    │   AOF persistence                       │    │
│  └──────────────────────────┘    └──────────────────────────────────────────┘    │
│                                                                                  │
│  ┌──────────────────────────────────────────────────────────────────────────┐    │
│  │                    EXTERNAL: ALPACA BROKER                                │    │
│  │  REST: paper-api.alpaca.markets/v2   (orders, positions, account)        │    │
│  │  WS:   paper-api.alpaca.markets/stream (trade updates)                   │    │
│  │  WS:   stream.data.alpaca.markets/v2/{feed} (quotes, trades, bars)       │    │
│  │  REST: data.alpaca.markets/v2 (historical bars)                          │    │
│  └──────────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Technology Stack

| Layer | Technology | Version |
|---|---|---|
| Frontend | React + Vite + Ant Design | TypeScript |
| Backend | FastAPI + async SQLAlchemy | Python 3.12 |
| Database | PostgreSQL | 16-alpine |
| Cache/Queue | Redis | 7-alpine |
| ML | XGBoost + LightGBM + scikit-learn | — |
| Broker | Alpaca Markets API v2 | Paper trading |
| Observability | Prometheus + Grafana + OpenTelemetry | Optional profile |
| Container | Docker Compose | 3 core + 3 observability |

### Data Flow Paths

```
ORDER EXECUTION:
  Engine Decision → DB Order → Outbox Event → Dispatcher → Alpaca REST
  Alpaca Fill → WebSocket Stream → DB Update → Socket.IO → Frontend

MARKET DATA:
  Alpaca WS (real-time bars) → StreamingDataProvider → Ring Buffer → Engine
  Alpaca REST (historical) → DataClient → Feature Engineering → ML/Alpha

BRAIN STATE:
  Engine State → JSON files (organism_brain/) → Load on restart
  ML Models → Pickle/JSON → Transfer Learning → Cross-run knowledge
```

---

# LAYER 2: TRADING ALGORITHM — TICK LIFECYCLE

## 2. TICK LIFECYCLE OVERVIEW

**Source**: `backend/organism/live_engine.py`

```
┌─────────────────────────────────────────────────────────────────────┐
│                 TICK BEGINS (code default: 60s, .env: 10s)          │
│                                                                     │
│  ┌──── ALWAYS ─────────────────────────────────────────────────┐   │
│  │  [0] Housekeeping: expire cooldowns, stream health          │   │
│  │  [0.5] Stale data gate: check streaming provider freshness  │   │
│  │        IF data > 2 min stale → block entries (exits still   │   │
│  │        run). Logs stale↔fresh transitions.                  │   │
│  │  [1] Governance halt check → entries_blocked?               │   │
│  │  [1.1] Warmup gate (first 5 ticks → entries_blocked)        │   │
│  │  [1.2] Stale data gate → entries_blocked if _data_stale     │   │
│  │  [1.5] Market scanner (every 6 ticks → inject up to 20      │   │
│  │        candidates into universe)                             │   │
│  │  [2] Fetch data + compute 79+18 features per symbol         │   │
│  │  [3] Detect market regime (3-tier priority)                 │   │
│  │  [4] Get positions + equity, drawdown kill check            │   │
│  │  [5] EXIT CHECKS for all open positions                     │   │
│  │      ├── Bar boundary detection per symbol (wall-clock minute)│   │
│  │      ├── Risk checks (max_loss, stop_loss) run EVERY tick   │   │
│  │      └── Time/profit exits run ONLY on new 1-min bars       │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌──── IF entries NOT blocked ─────────────────────────────────┐   │
│  │  [6] Pyramid checks on existing positions                   │   │
│  │  [7] Scan new entries: Alpha + Breakout + ML                │   │
│  │  [8] Kelly position sizing                                  │   │
│  │  [9] Submit entry orders                                    │   │
│  │  [9b] Exploration bucket (micro-size trades on rejects)     │   │
│  │  [11] Retrain ML + evolve parameters                        │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌──── ALWAYS (runs even when entries blocked) ────────────────┐   │
│  │  [10] Reconcile fills (detect closed + orphaned positions)  │   │
│  │  [12] Brain save (every 20 ticks, with walk-forward gate)   │   │
│  │  [POST] Equity curve, Prometheus, telemetry, invariants     │   │
│  │  [POST] Persist telemetry to DB (every 6th tick ≈ 1/min)   │   │
│  │  [POST] Cleanup old telemetry (every 2160 ticks, 7-day TTL) │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│                         TICK ENDS                                   │
└─────────────────────────────────────────────────────────────────────┘
```

**Critical insight**: Exits ALWAYS run, even when governance has halted trading. Only new entries are blocked.

---

## 3. PHASE 0: PREAMBLE & HOUSEKEEPING

```
START TICK
  │
  ├── Acquire async tick lock (serializes execution)
  ├── Increment _tick_count
  │
  ├── Expire cooldowns:
  │   ├── _exit_cooldown:   symbols older than 10 ticks removed
  │   ├── _pending_entry:   symbols older than 30 ticks removed
  │   └── _pending_exit:    symbols older than 3 ticks removed
  │
  └── Stream health check (every 30 ticks ≈ 5 min):
      └── IF streaming provider active:
          └── check_and_recover_stale_stream()
```

### Cooldown Constants

| Cooldown | Ticks | Real Time (~10s ticks) | Purpose |
|---|---|---|---|
| `_EXIT_COOLDOWN_TICKS` | 10 | ~100s | Prevents re-entering a recently exited symbol |
| `_PENDING_ENTRY_TICKS` | 30 | ~5 min | Prevents duplicate entry submissions |
| `_PENDING_EXIT_TICKS` | 3 | ~30s | Prevents duplicate exit submissions |

---

## 4. PHASE 1: GOVERNANCE GATE

**Source**: `backend/organism/governance.py`

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
| `ORGANISM_DRAWDOWN_KILL_PCT` | 0.05 | **0.03** (docker), **0.08** (.env) | Drawdown % that triggers kill switch |
| `ORGANISM_DRAWDOWN_COOLDOWN_S` | 3600 | **300** (docker) | Base cooldown after kill (code: 1hr, docker: 5min) |
| `ORGANISM_MAX_CHANGES_PER_DAY` | 100 | **500** (docker) | Daily evolution budget |
| `ORGANISM_HALT_TRADING` | 0 | 0 | Manual trading halt |
| `ORGANISM_FREEZE_ADAPTATION` | 0 | **1** | Freeze all adaptation (enabled during structural fixes) |
| `ORGANISM_ENABLED` | 0 | **0** (docker) | Opt-in flag for organism engine |
| `ENABLE_ORGANISM_SCHEDULER` | 0 | **0** (docker) | Opt-in flag for tick scheduler |
| `ORGANISM_BRAIN_DIR` | "organism_brain" | — | Brain persistence directory |
| `ORGANISM_DISABLED_STRATEGIES` | "" | — | Comma-separated strategies to disable |

---

## 5. PHASE 2: DATA ACQUISITION & FEATURE ENGINEERING

**Source**: `backend/organism/live_engine.py`, `backend/organism/ml_features.py`

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
  │   └── Compute features (79 + 18 MTF = 97 total):
  │       ├── compute_ml_features(raw_df, spy_df, bars_per_day)  → 79 base features
  │       │   └── bars_per_day flows from live_engine (390 for 1Min, 78 for 5Min, etc.)
  │       ├── add_multi_timeframe_features()         → additional MTF features
  │       ├── NaN/Inf → 0.0 (global safety net)
  │       └── _nan_missingness column: ratio of NaN/Inf in last row (for entry gate)
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
| `RETRAIN_INTERVAL` | 60 (daily), auto→200 (intraday) | **600** (docker-compose), **180** (.env production) |

---

## 6. PHASE 3: REGIME DETECTION

**Source**: `backend/organism/regime.py`

```
DETECT REGIME (only if features sufficient)
  │
  ├── Priority 1: Cross-Asset Regime
  │   ├── Needs sector ETF features (XLK, XLE, XLF, XLV, XLI, XLU, XLP, XLY, XLB, XLRE)
  │   ├── Each ETF must have >= 10 bars of features
  │   ├── Computes per-sector regimes, then breadth conditioning:
  │   │   ├── breadth_up > 0.5 → boost trending_up × (1 + 0.3 × breadth_up), suppress stress × 0.7
  │   │   ├── breadth_down > 0.5 → boost trending_down × (1 + 0.3 × breadth_down), suppress trending_up × 0.7
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

From feature data, 5 signals are extracted:

| Signal | Source | Daily Threshold | Intraday Threshold (×tf_scale) | Decision |
|---|---|---|---|---|
| Trend slope | SMA slope over 10 bars | ±0.02 | ±0.02 (no scaling) | > thresh → trending_up(+2), < -thresh → trending_down(+2), else → chop(+1.5) |
| Price vs SMA | (close - SMA) / SMA | ±0.02 | ±0.001 (1Min) | > thresh → trending_up(+1), < -thresh → trending_down(+1), else → chop(+0.5) |
| Volatility | `atr_14` (ATR(14)/price) | 0.04 / 0.015 | 0.002 / 0.0008 (1Min) | ATR > high → high_vol(+2), ATR < low → low_vol(+1.5) |
| Returns vol | returns std | 0.03 | 0.0015 (1Min) | ret_vol > thresh → high_vol(+1) |
| Stress (a) | Volume anomaly + ATR | vol_anomaly > 0.5 AND ATR > 0.04 | vol_anomaly > 0.5 AND ATR > atr_high | stress(+2) |
| Stress (b) | Extreme vol anomaly | vol_anomaly > 1.0 | vol_anomaly > 1.0 | stress(+1) |

**Intraday threshold scaling**: `tf_scale = 1 / sqrt(bars_per_day)`. For 1-min bars (390 bpd), tf_scale ≈ 0.0507. This scales per-bar thresholds to match the magnitude of single-bar returns/volatility at that timeframe. Lookback periods are separately scaled 4× via `is_intraday`.

Scores → softmax → EMA smoothing (α=0.3) → argmax = primary regime.

### Regime Labels

`trending_up`, `trending_down`, `chop`, `high_vol`, `low_vol`, `stress`, `unknown`

---

## 7. PHASE 4: PORTFOLIO STATE & DRAWDOWN

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

## 8. PHASE 5: EXIT DECISIONS

**This is the most critical phase. It ALWAYS runs, even when entries are blocked.**

**Source**: `backend/organism/adaptive_exits.py`, `backend/organism/live_engine.py`

```
FOR EACH OPEN POSITION:
  │
  ├── FILTER: LONG_ONLY and side != "long" → SKIP (artifact short)
  ├── FILTER: sym in _pending_exit → SKIP (exit already submitted)
  │
  ├── PATH A: No features available for this symbol
  │   ├── Get broker_price and avg_entry from position data
  │   ├── Compute pnl_pct = (broker_price - entry) / entry × direction
  │   ├── IF pnl_pct <= -max_loss_pct (8%) → SAFETY NET EXIT
  │   │   └── Submit full exit, reason: "safety_net_no_features"
  │   └── ELSE → no action (can't evaluate without features)
  │
  ├── PATH B: Features available but NO exit_levels for this symbol
  │   ├── Get avg_entry from position data
  │   ├── Compute pnl_pct
  │   ├── IF pnl_pct <= -max_loss_pct (8%) → SAFETY NET EXIT
  │   │   └── Submit full exit, reason: "max_loss_safety_net"
  │   └── ELSE → no action (position adopted mid-session, exits will be created)
  │
  └── PATH C: Normal exit check (features + exit_levels both available)
      │
      ├── Bar boundary detection (per symbol):
      │   ├── Use wall-clock UTC minute boundary (not Alpaca bar timestamp — avoids 2-3 min lag)
      │   ├── Compare current minute to _last_bar_times[symbol]
      │   ├── is_new_bar = True when minute changes (exactly 1 bar per minute)
      │   └── Update _last_bar_times[symbol] on new bar only
      │
      ├── Run adaptive exit engine: check_exit(exit_levels, price, regime, is_new_bar)
      │   │
      │   │  ═══ ALWAYS (every 10s tick): risk checks ═══
      │   │
      │   ├── Update highest_favorable price tracking
      │   │
      │   ├── Priority 0: MAX LOSS safety net (8% intraday, 8% daily via for_timeframe)
      │   │   └── pnl_pct <= -max_loss_pct → EXIT, reason: "max_loss_limit"
      │   │
      │   ├── Priority 1: HARD STOP LOSS
      │   │   ├── Long: price <= stop_loss → EXIT
      │   │   └── Short: price >= stop_loss → EXIT
      │   │
      │   ├── ** SUB-TICK FAST PATH: if NOT is_new_bar → return no-exit **
      │   │   (Risk checks above always run; time/profit exits below only on new bars)
      │   │
      │   │  ═══ NEW BAR ONLY: advance bars_held + run profit/time exits ═══
      │   │
      │   ├── Save price_at_prior_bar = current_price (for FTF momentum check)
      │   ├── Increment bars_held by 1 (now counts 1-min bars, NOT 10s ticks)
      │   │
      │   ├── ** MIN_HOLD gate: dynamic = max(prediction_horizon // 3, 3) **
      │   │   └── For H=15: min_hold = 5 bars (5 min). Was static 18 ticks (3 min).
      │   │       All profit exits below are SUPPRESSED until bars_held >= min_hold.
      │   │       (Only stop loss and max_loss_limit bypass this gate)
      │   │
      │   ├── Priority 1.5: PROFIT LOCK (2R, one-shot)
      │   │   ├── Triggers when favorable move >= 2× initial risk
      │   │   ├── Moves stop to entry + 1R (locks in 1R of profit)
      │   │   └── Sets profit_locked = True (never fires again)
      │   │
      │   ├── Priority 2: PARTIAL TAKE PROFIT (3R, fires once)
      │   │   ├── **DISABLED in learning mode** (improve9 A4): stops clipping small winners
      │   │   ├── Long: price >= partial_tp → SELL 20% (intraday) / 25% (daily)
      │   │   ├── Short: price <= partial_tp → COVER 20%/25%
      │   │   ├── (Base class default is 30% but for_timeframe() overrides)
      │   │   └── Side effect: move stop to BREAKEVEN
      │   │
      │   ├── Priority 3: FULL TAKE PROFIT
      │   │   └── price crosses TP level → EXIT
      │   │
      │   ├── Priority 4: ATR TRAILING STOP
      │   │   ├── Activates when price moves 2.0× ATR from entry (via for_timeframe; base default 3.0)
      │   │   ├── Trail distance: ATR × regime_trail_atr_mult
      │   │   ├── Ratchet: only tightens, never loosens
      │   │   ├── Long trail floor: never below entry price
      │   │   └── price crosses trail → EXIT
      │   │
      │   ├── Priority 4b: FAILURE TO FOLLOW THROUGH (horizon-delay + regime R)
      │   │   ├── **SKIPPED entirely when trailing_active = True** (trailing governs)
      │   │   ├── Horizon delay (regime-adaptive):
      │   │   │   ├── chop: max(H × 4/5, 5) = **12 bars** for H=15 (don't judge early in chop)
      │   │   │   └── other: max(H // 2, 3) = **7 bars** for H=15
      │   │   ├── Multi-bar momentum: tracks price_at_prior_bar AND price_two_bars_ago
      │   │   ├── Regime-dependent R thresholds:
      │   │   │   ├── trending_up / low_vol / high_vol: **DISABLED** (let winners run)
      │   │   │   ├── chop: 0.15R — **REDESIGNED (improve7)**:
      │   │   │   │   ├── If PnL ≤ 0 AND 2-bar negative momentum → EXIT "failure_to_follow"
      │   │   │   │   ├── If PnL > 0 AND not yet tightened → TIGHTEN stop (ftf_stop_tighten)
      │   │   │   │   │   └── Moves stop to midpoint between entry and current price (one-shot)
      │   │   │   │   └── If already tightened or no momentum signal → HOLD (do not exit)
      │   │   │   ├── stress: 0.10R
      │   │   │   └── trending_down / unknown: 0.25R (original logic: exit if no positive momentum)
      │   │   └── New ExitLevels fields: ftf_stop_tightened (bool), price_two_bars_ago (float)
      │   │
      │   ├── Priority 4c: HORIZON TIMEOUT (improve9 A3, learning mode only)
      │   │   ├── If bars_held >= 18 (H=15 + 3 grace) → EXIT, reason: "horizon_timeout"
      │   │   └── Aligns exits to thesis horizon — prevents slow-bag losers beyond prediction window
      │   │
      │   ├── Priority 5: TIME-BASED EXIT (regime-adaptive, 1-min bar units)
      │   │   ├── max_bars varies by regime (0=disabled for trending_up AND low_vol; trending_down=45)
      │   │   └── Only exits positions IN PROFIT (losers stay)
      │   │
      │   ├── Priority 5b: LOSER TIME-STOP
      │   │   ├── loser_ref = max_bars if max_bars > 0 else 120 (fallback = 2 hours)
      │   │   ├── loser_max = loser_ref × 1.5 (losers get extra time, not infinite)
      │   │   └── If bars_held >= loser_max AND pnl <= 0 → EXIT, reason: "loser_time_stop"
      │   │
      │   ├── Priority 6: TIME DECAY (non-exiting, tightens stop)
      │   │   ├── After decay_start bars: stop tightens 0.3%/bar (was 1%/tick — 6× too fast)
      │   │   └── Maximum tightening: 40%
      │   │
      │   └── Priority 7: STRESS REGIME TIGHTENING (one-time)
      │       ├── Fires if regime changes to stress mid-trade AND regime_at_entry != "stress"
      │       └── Tightens stop by 40% of distance from CURRENT PRICE to stop (not entry-to-stop)
      │
      ├── ML Reversal Check (if exit engine says NO exit):
      │   ├── Condition: ML trained AND signal flips direction
      │   │   AND confidence > 0.60 (intraday) / 0.65 (daily)
      │   │   AND symbol NOT in _ml_reversal_used set (one-shot guard per position)
      │   └── IF reversal detected → PARTIAL EXIT 30% (intraday) / 25% (daily)
      │       ├── reason: "ml_reversal"
      │       └── Add symbol to _ml_reversal_used (cleared when position fully closes)
      │
      └── IF exit signal fired:
          ├── Compute shares to sell (full or partial)
          ├── Submit exit order via _submit_exit_order():
          │   ├── Store exit reason in _last_exit_reason[symbol] for trade attribution
          │   ├── Capture synchronous fill price in _last_exit_fill_price[symbol]
          │   └── Set cooldowns (_exit_cooldown, _pending_exit)
          └── Reasons: "stop_loss", "trailing_stop", "take_profit", "partial_take_profit",
              "failure_to_follow", "loser_time_stop", "ml_reversal", "max_loss_limit",
              "eod_flatten" (improve7: forced close at market close), etc.
```

### Exit Regime Parameters (REGIME_* lookup tables in adaptive_exits.py)

**Units**: Max Bars and Decay Start are now in **1-minute bars** (not 10s ticks). bars_held only increments on new bar boundaries.

| Regime | Stop ATR | TP R-Multiple | Trail ATR | Max Bars (1-min) | Decay Start (1-min) |
|---|---|---|---|---|---|
| `trending_up` | 3.5 | 6.0 | 5.0 | ∞ (0) | 0 (none) |
| `trending_down` | 2.5 | 3.0 | 3.5 | 45 (45 min) | 30 (30 min) |
| `chop` | 2.5 | 2.5 | 3.0 | 30 (30 min) | 20 (20 min) |
| `high_vol` | 4.0 | 3.0 | 4.5 | 45 (45 min) | 30 (30 min) |
| `low_vol` | 3.0 | 5.0 | 4.5 | ∞ (0) | 0 (none) |
| `stress` | 2.5 | 2.0 | 3.0 | 20 (20 min) | 15 (15 min) |
| `unknown` | 3.0 | 4.0 | 4.0 | 60 (60 min) | 40 (40 min) |

Note: Stop and Trail ATR values were ~2× scaled for 1-min intraday bars (improve9 pre-fix). Old values (trending_up stop=2.0, chop=1.2, etc.) were effectively daily-bar logic ported into 1-min engine, causing stops only cents from entry.

### for_timeframe() Factory Overrides (used by live engine)

These override the base class defaults when the engine calls `AdaptiveExitEngine.for_timeframe()`:

| Parameter | Base Default | Intraday (1Min/5Min/15Min/1Hour) | Daily |
|---|---|---|---|
| `atr_multiplier` | 1.5 | **1.0** | 1.5 |
| `profit_r_multiple` | 4.0 | **3.0** | 4.0 |
| `trailing_start_atr` | 3.0 | **2.0** | **2.0** |
| `trailing_distance_atr` | 2.5 | **1.5** | 2.5 |
| `max_bars_held` | 40 | **60** (1 hr) | 40 |
| `time_decay_start` | 30 | **40** (40 min) | 30 |
| `partial_tp_r` | 3.0 | 3.0 | 3.0 |
| `partial_tp_pct` | 0.30 | **0.20** | **0.25** |
| `max_loss_pct` | 0.15 | **0.08** | **0.08** |
| `profit_lock_r` | 2.0 | 2.0 | 2.0 |

### Additional Exit Constants

| Constant | Value | Effect |
|---|---|---|
| `_min_hold_bars()` | `max(H//3, 3)` = **5** for H=15 | Dynamic minimum hold before profit exits. Was static 18 ticks (~3 min). |
| `prediction_horizon` | 15 (1Min default) | Stored on ExitLevels, drives min_hold and failure_to_follow timing |
| `_LOSER_MAX_FALLBACK` | **120** (2 hours) | Loser time-stop uses 120 bars when max_bars=0. Was 200 ticks (~33 min). |
| `TIME_DECAY_RATE` | **0.003** (0.3%/bar) | Tightens stop after decay_start bars. Was 1%/tick (6× too fast). |
| Time decay floor | 0.6 | Maximum 40% tightening from time decay |
| Failure-to-follow R thresholds | Regime-dependent | trending_up/low_vol/high_vol=**disabled**; chop=0.15R (**losers-only exit + stop tighten for winners**); stress=0.10R; others=0.25R |
| Failure-to-follow delay | chop: `max(H×4/5, 5)` = **12**; other: `max(H//2, 3)` = **7** for H=15 | Chop gets longer delay (don't judge 15-bar thesis at 7 bars) |
| FTF stop tighten (chop) | midpoint(entry, current) | One-shot: if PnL > 0 in chop, tighten stop instead of exiting. Sets `ftf_stop_tightened = True`. |
| ATR fallback | 2% of entry | Used when ATR data unavailable |
| ATR computation | EMA-based (α=2/(period+1)), init=mean of first period TRs | Falls back to abs(close.diff()).mean() |
| `is_new_bar` | `self._now_fn()` minute boundary | Risk checks (max_loss, stop_loss) run every 10s tick; all other exits only on new 1-min bars. Uses `_now_fn()` (live = wall clock, replay = simulated time) for consistent 1-bar/min counting. |
| `_is_entry_bar` (improve9 A6) | `self._now_fn()` minute boundary | New entries gated to bar boundaries — separate from exit bar tracking. Same clock source as `is_new_bar`. |

**Exit levels brain persistence**: ExitLevels (trailing state, partial_tp_taken, stress_tightened, profit_locked, last_bar_time, prediction_horizon flags) are saved to `extra_counters["exit_levels"]` and restored on startup. Symbols with brain-restored exit levels skip `_reconstruct_position_state()` to preserve richer state.

**Evolution scaling**: Exit params can drift during live operation. The evolution engine multiplies `_base_*` fields by evolved `*_scale` factors (stop_atr_scale, trailing_start_atr_scale, trailing_distance_scale, partial_tp_r_scale). Note: `profit_lock_r` is NOT evolved — fixed at 2.0R forever.

**Partial TP side effect**: After partial TP, stop moves to breakeven BUT only if it tightens (uses max() for longs). Never downgrades an existing profit lock.

**Trailing stop floor**: Long trail never below entry price; short trail never above entry price.

---

## 9. PHASE 6: PYRAMID CHECKS

**Only runs if entries NOT blocked.**

**Source**: `backend/organism/pyramider.py`

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

## 10. PHASE 7: NEW ENTRY SCANNING

**Only runs if entries NOT blocked.**

### Pre-Scan Entry Gates (before scanning begins)

```
PRE-SCAN GATES (NOTE: these are scattered across the tick, not a single block)
  │
  ├── Warmup gate [step 1.1, BEFORE data fetch]: first 5 ticks after engine start → entries_blocked
  │   (_WARMUP_TICKS = 5 — lets data/features populate before trading)
  │
  ├── Equity-zero gate [step 4, AFTER data fetch + regime]: 3+ consecutive zero-equity readings → entries_blocked
  │   (_EQUITY_ZERO_THRESHOLD = 3 — detects stale broker data; auto-recovers)
  │
  ├── EOD entry block [step 1.3] (intraday only, improve7):
  │   ├── After 15:45 ET → entries_blocked = True (no new entries)
  │   └── After 15:58 ET → _eod_flatten_triggered = True
  │       └── Force close ALL open positions, reason: "eod_flatten"
  │       (prevents overnight exposure; aligns intraday mandate with equity curve)
  │
  ├── Background training timeout: _BG_TRAINING_TIMEOUT_TICKS = 30 (~5 min at 10s/tick)
  │   (auto-cancels stuck background retrain jobs)
  │
  ├── Opening 30-min block [AFTER exit checks] (intraday only):
  │   └── 9:30-10:00 AM ET → entries_blocked = True
  │       (avoids noisy open auction; lets regime/features stabilize)
  │
  ├── Regime sit-out gate [AFTER exit checks] (LONG_ONLY mode):
  │   ├── Active in: high_vol, stress regimes
  │   ├── Runs ML predict_batch on all symbols
  │   └── IF all bearish (direction < 0) AND zero bullish → _regime_sit_out = True (separate variable)
  │       (prevents catching falling knives when everything is selling)
  │
  └── Entry throttle [AFTER exit checks] (dynamic entries/hour):
      ├── Tracks timestamps of recent entries (rolling 3600s window)
      ├── Learning mode (< 200 completed trades): max 12 entries/hour
      ├── Production mode: max(3, 6 - open_positions) entries/hour
      └── IF >= effective_max entries in last hour → _throttled = True
          (prevents rapid-fire entry cascades; relaxed in learning for data collection)

  Burst cap [improve8]: rolling 15-min window, max 4 entries per 15 minutes

  Bar-boundary entry gate [improve9 A6]:
      Entries only on completed 1-min bar boundaries (self._now_fn() minute changes)
      Exits/risk checks still run every 10s tick. Reduces same-bar churn.

  Final gating check: `if not entries_blocked and not _regime_sit_out and not _throttled and not _burst_capped and _is_entry_bar`
  (5 independent gating variables)
```

**Source**: `backend/organism/alpha_scanner.py`, `backend/organism/breakout_scanner.py`, `backend/organism/ml_signal.py`

```
ENTRY SCANNING PIPELINE
  │
  ├── [7a] BREAKOUT SCAN
  │   ├── Filter: symbols with >= 60 bars (scan) + >= 50 bars (score); secondary 50-bar check in _score_symbol
  │   ├── 6 detectors scored and weighted (see §19)
  │   └── Returns top-N BreakoutSignals with composite >= 0.20 (N=MAX_OPEN_POSITIONS: code 8, docker 15)
  │
  ├── [7b] ML PREDICTIONS
  │   ├── Batch predict on all symbols with features
  │   └── Returns MLSignal per symbol: direction, confidence, predicted_return
  │
  ├── [7c] ALPHA SCAN
  │   ├── Combines ML + 6 other factors (see §18)
  │   └── Returns top-5 AlphaCandidates with composite >= 0.15 (improve9 B2: raised from 3 to reduce concentration)
  │
  ├── [7d] FILTER CANDIDATES (12 gates):
  │   │
  │   │  For each AlphaCandidate:
  │   ├── Gate 1: Already have position? → REJECT
  │   ├── Gate 2: In exit cooldown? → REJECT (wash trade prevention)
  │   ├── Gate 3: Pending entry order? → REJECT (duplicate prevention)
  │   ├── Gate 4: Already in entry_metadata? → REJECT
  │   ├── Gate 5: LONG_ONLY and direction < 0? → REJECT
  │   ├── Gate 6: Sector gate (max 4 per sector)? → REJECT
  │   ├── Gate 7: Symbol fitness gate (improve9 B1: unified canonical system):
  │   │   ├── Learning mode: NO hard gate (fitness = soft ranking only, A5)
  │   │   └── Production: REJECT if fitness < 0.45 AND symbol has 10+ closed trades
  │   ├── Gate 8: Liquidity gate (avg 20-bar volume < 10,000)? → REJECT
  │   ├── Gate 9: Symbol circuit breaker (improve7/8)? → REJECT
  │   │   └── Banned if: (a) 2+ consecutive losses AND 0 wins today, OR
  │   │       (b) daily P&L ≤ -max($25, 0.10% equity), OR (c) 2+ stop-loss exits in 30 min
  │   ├── Gate 10: Missingness gate (last-row NaN/Inf > 25%)? → REJECT
  │   ├── Gate 11: Confidence gate (improve7):
  │   │   └── MIN_MAIN_CONF = 0.45 in chop/high_vol/trending_down, 0.40 otherwise
  │   │       Below threshold → LOGGED only (improve9 A7: exploration queue removed)
  │   └── Gate 12: Alpha+breakout bad-regime defensive filter (2026-05-08):
  │       └── alpha+breakout candidates in chop/trending_down → REJECT when
  │           ORGANISM_ALPHA_BREAKOUT_BAD_REGIME_FILTER_ENABLED=true (default)
  │
  │   IF passes all 12 gates:
  │   ├── Compute blended confidence (additive, mode-dependent):
  │   │   ML-ISOLATED MODE (learning or production_guarded):
  │   │   confidence = 0.65 × breakout_score
  │   │              + 0.35 × min(tension, 1.0)
  │   │   (ML weight = 0%; guarded mode uses this until realized expectancy
  │   │    clears the production promotion floors)
  │   │
  │   │   PRODUCTION MODE:
  │   │   confidence = 0.50 × ML_confidence
  │   │              + 0.30 × breakout_score
  │   │              + 0.20 × min(tension, 1.0)
  │   │   (no cap needed — weighted sum of [0,1] inputs stays in [0,1])
  │   └── Add to candidate list
  │
  ├── [7e] PURE BREAKOUT ADDITIONS (not in alpha candidates):
  │   ├── Max per tick: _MAX_PURE_BREAKOUT = 2
  │   ├── Gates (shares safety gates with alpha path — improve9 hardening):
  │   │   ├── Not in alpha candidates, not in open positions
  │   │   ├── Not in exit cooldown, pending entry, or entry_metadata
  │   │   ├── Not in _symbol_banned (circuit breaker, improve7)
  │   │   ├── composite_score >= 0.55
  │   │   ├── fitness gate: learning=pass always, production=0.45 for 10+ trades (B1)
  │   │   ├── Liquidity gate (shared with alpha path)
  │   │   ├── Confidence threshold gate (shared with alpha path)
  │   │   ├── Sector gate allows
  │   │   └── ML direction not negative, only when ML influence is enabled
  │   │   (NOTE: skips missingness gate; uses baseline confidence only, not defensive tier)
  │   ├── Forced direction = +1.0 (always long)
  │   └── predicted_return:
  │       ├── Full production + ML present: pass through ML return if direction agrees
  │       └── ML-isolated / ML absent: 0.005 + 0.015 × breakout_score
  │           (0.5%–2.0% range)
  │
  └── [7f] SORT + TRUNCATE
      ├── Sort by breakout_score × confidence (descending)
      └── Truncate to: MAX_POSITIONS - current_positions
```

### SPY MA Filter (Currently Disabled)

A broad market gate that blocks all long entries when SPY < SMA(50). Infrastructure exists but `_spy_filter_enabled = False` since commit 2a92ec6. Individual stock gates (ML, alpha, breakout, regime, sector) are more granular.

### Entry Filter Funnel (Typical Numbers)

```
22 symbols in universe (improve9 B4: +SH, +PSQ inverse ETFs)
  → ~20 with sufficient features
    → ~5 pass alpha threshold (0.15)
      → ~3-4 pass all 11 gates (improve7: +circuit breaker, +confidence gate)
        → low-confidence candidates logged (improve9 A7: exploration queue removed)
        → ~2-3 after Kelly sizing
          → ~1-2 orders submitted
```

---

## 11. PHASE 8: KELLY POSITION SIZING

**Only runs if entries NOT blocked and candidates exist.**

**Source**: `backend/organism/kelly_sizer.py`

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
  │   │   ├── direction == 0 or NaN/Inf → SKIP
  │   │   ├── predicted_return < 1e-6 (after floor) → SKIP
  │   │   │   └── Floor: breakout with predicted_return=0 → 0.5% (untrained) or 1.0% (trained)
  │   │   ├── Features < 30 rows → SKIP
  │   │   └── < 20 usable returns (last 60 bars lookback) → SKIP
  │   │   (NOTE: _nan_missingness > 0.25 gate is pre-Kelly, in live_engine step 7b before sizing)
  │   │
  │   ├── PRE-STEP: atr_pct computed UNCONDITIONALLY before regime branch
  │   │   └── atr_pct = std(returns, ddof=1) or 0.01 fallback (used by signal-Kelly AND risk-budget floor)
  │   │
  │   ├── STEP 1: Raw Kelly (capped at 1.0)
  │   │   ├── Preferred: Regime-stratified (if >= 10 trades in regime)
  │   │   │   ├── Kelly = win_rate - (1 - win_rate) / payoff_ratio
  │   │   │   └── Returns None (→ fallback) if: all wins, loss amount < 1e-8, or payoff_ratio <= 0
  │   │   └── Fallback: max(signal_kelly, unconditional_kelly)
  │   │       ├── Signal-based Kelly: predicted_return / max((atr_pct × √horizon_bars)², 1e-6)
  │   │       │   (horizon_bars=15 for 1Min; scales per-bar variance to match prediction horizon)
  │   │       ├── Unconditional Kelly: mean(dir_returns) / var(dir_returns) (ddof=1)
  │   │       │   ├── dir_returns = returns × direction (sign-flipped for shorts)
  │   │       │   ├── Uses last 60 bars of returns
  │   │       │   └── Guards: var < 1e-8, mean <= 0, or non-finite → kelly = 0
  │   │       └── kelly_raw = min(max(signal_kelly, unconditional_kelly), 1.0)
  │   │
  │   ├── STEP 2: Half-Kelly + Edge Gate + Floors
  │   │   ├── kelly_half = kelly_raw × 0.5
  │   │   ├── Edge-over-cost gate (state-dependent cost model):
  │   │   │   ├── spread_cost = _estimate_spread_cost(symbol, quote_provider, features)
  │   │   │   │   ├── base_spread = (ask - bid) / mid_price  (fallback: 10bps if no quote)
  │   │   │   │   ├── time_mult = get_slippage_multiplier()  (2.0 pre-mkt, 1.5 open, 0.9 morning, 1.0 midday, 0.95 afternoon, 1.3 close, 2.5 after-hrs)
  │   │   │   │   ├── liquidity_mult = 1.0 + max(0, 1.0 - vol_sma_ratio) × 0.5  (up to 1.5×)
  │   │   │   │   ├── spread_cost = base_spread × time_mult × liquidity_mult
  │   │   │   │   └── Clamped to [3bps, 50bps]
  │   │   │   ├── edge_clears_cost = predicted_return >= spread_cost × 2
  │   │   │   └── If NOT edge_clears_cost AND kelly < 0.005 → kelly = 0 (skip)
  │   │   ├── Breakout floor: kelly < 0.005 AND breakout >= 0.55 AND edge_clears_cost
  │   │   │   → kelly_half = max(kelly, 0.003 × breakout_score)
  │   │   └── ML floor: kelly < 0.005 AND conf >= 0.5 AND regime_has_edge AND edge_clears_cost
  │   │       (regime_has_edge = True UNLESS regime has >= 5 trades AND total_pnl <= 0)
  │   │       ├── Trained ML:   kelly_half = max(kelly, 0.04 × confidence)
  │   │       └── Untrained ML: kelly_half = max(kelly, 0.02 × confidence)
  │   │
  │   ├── STEP 3: Drawdown Scaling
  │   │   └── Linear: 1.0 at 0% drawdown → 0.1 at 25% drawdown
  │   │
  │   ├── STEP 4: Volatility Targeting (timeframe-aware)
  │   │   ├── ann_vol = std(returns) × sqrt(252 × bars_per_day)
  │   │   │   bars_per_day: 390 (1Min), 78 (5Min), 26 (15Min), 7 (1Hour), 1 (1Day)
  │   │   └── vol_scale = 0.15 / ann_vol (capped at 2.0)
  │   │
  │   ├── STEP 5: Regime Scaling
  │   │   ├── Hardcoded fallbacks in kelly_sizer.py:
  │   │   │   trending_up: 1.20  trending_down: 0.60  chop: 0.50
  │   │   │   high_vol: 0.80    low_vol: 1.00        stress: 0.40
  │   │   │   unknown: 0.70
  │   │   ├── Evolved_params overrides (from brain):
  │   │   │   chop: 0.485  high_vol: 0.70  stress: 0.30
  │   │   │   (other regimes inherit hardcoded values; values evolve over time)
  │   │   ├── **Evolution freeze (improve7)**: Evolved scales ONLY used when:
  │   │   │   ├── Total trades across all regimes >= 200
  │   │   │   └── Trades in THIS specific regime >= 30
  │   │   │   Otherwise: hardcoded fallbacks used (early evolved scales are unstable)
  │   │   ├── **Full evolution freeze (improve9 B5)**: All evolution frozen until 300+ trades
  │   │   └── NOTE: evolved_params take precedence when present AND statistically stable
  │   │
  │   │
  │   │   ══ MODE SPLIT (improve9 A1) ══════════════════════════════════
  │   │
  │   │   FIXED-RISK MODE (learning <200 trades OR production_guarded):
  │   │   ├── No Kelly, no confidence scaling, no breakout bonus
  │   │   ├── risk_rate = 0.10% equity (_RISK_BUDGET_PER_TRADE_LEARNING)
  │   │   ├── stop_distance = atr_pct × _RISK_BUDGET_STOP_ATR
  │   │   ├── target_weight = risk_rate / stop_distance
  │   │   ├── target_weight *= drawdown_scale × regime_scale
  │   │   └── Deterministic sizing: no noise from uncalibrated ML/returns
  │   │
  │   │   FULL PRODUCTION MODE: FULL KELLY STACK
  │   │   ├── Requires >=300 strategy trades AND passing promotion floors:
  │   │   │   total_pnl >= 0, last_50_mean_pnl >= 0,
  │   │   │   last_50_win_rate >= 0.35, sharpe_per_trade >= 0
  │   ├── STEP 6: Confidence Scaling (production only)
  │   │   ├── scale = 0.3 + confidence × 1.2 → range [0.3, 1.5]
  │   │   └── IF ML untrained: capped at 0.9
  │   │
  │   ├── STEP 7: Breakout Bonus (production only)
  │   │   ├── < 0.50: ×1.0    0.70-0.85: ×1.5-2.0
  │   │   ├── 0.50-0.70: ×1.0-1.5   >= 0.85: ×2.0
  │   │   └── IF ML untrained: capped at ×1.5
  │   │
  │   ├── COMBINE (production only):
  │   │   target_weight = kelly_half × dd_scale × vol_scale
  │   │                   × regime_scale × conf_scale × brk_bonus
  │   │
  │   ├── PRE-KELLY RISK-BUDGET FLOOR (production, trade_count < 200):
  │   │   ├── risk_weight = 0.25% equity / (atr_pct × 1.5 stop_mult)
  │   │   ├── Applied after Kelly combine, before caps
  │   │   ├── **Confidence-scaled**: risk_weight × dd_scale × conf_floor_scale
  │   │   │   └── conf_floor_scale = clamp(0.5 + 0.8 × confidence, 0.5, 1.1)
  │   │   └── target_weight = max(kelly_target, scaled_risk_budget_weight)
  │   │
  │   ├── CAPS + FILTERS:
  │   │   ├── Per-position cap: 8% intraday / 10% daily (of equity)
  │   │   ├── Portfolio cap: running total cannot exceed 95%
  │   │   ├── Minimum weight: 0.05%
  │   │   │   └── Rejects captured in _exploration_rejects (reason="weight_too_small")
  │   │   ├── StrategyGovernor hard gate before OrderService entry submit:
  │   │   │   ├── Unknown strategy_id blocks live orders
  │   │   │   ├── Shadow-only / live-disabled strategies block live orders
  │   │   │   └── Alpha baseline remains the only current live-enabled policy
  │   │   ├── Minimum notional: $500 intraday / $2,000 daily
  │   │   │   └── Rejects captured in _exploration_rejects (reason="below_min_notional")
  │   │   └── Minimum shares: 1
  │   │
  │   └── OUTPUT: PositionSize dataclass:
  │       ├── symbol, target_weight, shares, notional, kelly_raw, kelly_half
  │       ├── drawdown_scale, vol_scale, regime_scale, direction
  │       ├── confidence (real blended, NOT 0.6 default)
  │       ├── predicted_return (H-bar-ahead, from ML or floor)
  │       └── breakout_score (from breakout scanner)
  │
  └── INTRADAY SEASONALITY FILTER:
      ├── 3:45-3:58 ET: ALL sizes × 0.60 (entries still blocked by EOD gate above)
      └── 3:58+ ET: EOD FLATTEN triggered — all open positions force closed (improve7)
```

---

## 12. PHASE 9: ORDER SUBMISSION

```
SUBMIT ENTRY ORDERS
  │
  ├── Re-fetch positions from broker (catch partial fills)
  │   └── Guard: len(fresh_positions) >= MAX_OPEN_POSITIONS → SKIP ALL remaining entries
  │
  ├── FOR EACH SIZED POSITION:
  │   ├── Already have position at broker? → SKIP
  │   │
  │   ├── Pyramid initial sizing: shares × 0.60 (layer 0)
  │   │   └── Fallback: full shares if pyramid < 1
  │   │
  │   ├── Submit order:
  │   │   ├── Type: MARKETABLE LIMIT (limit order with 0.1% slippage cap above ask/below bid)
  │   │   │   └── Fallback to MARKET if no live quote available from streaming provider
  │   │   ├── TIF: DAY
  │   │   ├── Idempotency key: organism_{sym}_{date}_{session}_{tick}
  │   │   └── Attributes: source=organism, reason, confidence=sz.confidence (real blended), tick
  │   │
  │   ├── POST-ORDER SETUP (if features available):
  │   │   ├── Create ExitLevels (stop, TP, trailing, partial TP)
  │   │   ├── Create PyramidPosition (layer 0, target = shares/0.6)
  │   │   └── Create _entry_metadata record:
  │   │       ├── entry_price, entry_tick, entry_time (wall clock), direction
  │   │       ├── filled_shares, predicted_return, confidence
  │   │       ├── entry_source: "alpha", "breakout", "alpha+breakout", or "exploration" (improve7)
  │   │       └── regime_at_entry: regime label at entry time (improve7)
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

### Phase 9b: Exploration Bucket (DISABLED — improve9 A7)

**Source**: `backend/organism/live_engine.py` (step 9b)

**improve9 A7 + hardening**: Exploration execution block completely removed from live_engine step 9b. No code path exists that can submit a live order for exploration-classified candidates. Low-confidence candidates are logged only.

Previously, micro-size trades on Kelly-rejected and confidence-gated candidates were auto-enabled for intraday modes. That entire execution block has been deleted (not just disabled). kelly_sizer._exploration_rejects is preserved for diagnostics only.

Configuration (legacy, no effect):
  ORGANISM_EXPLORATION_ENABLED      = false
  ORGANISM_EXPLORATION_MAX_NOTIONAL = 200.0
  ORGANISM_EXPLORATION_MAX_POSITIONS = 3

---

## 13. PHASE 10: FILL RECONCILIATION

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
  │       │
  │       ├── Get exit price (4-tier fill price chain):
  │       │   ├── 1st: _last_exit_fill_price (synchronous fill from exit order response)
  │       │   ├── 2nd: _lookup_exit_fill_from_db() (DB query: most recent filled sell
  │       │   │        order with source=organism, ordered by updated_at DESC)
  │       │   ├── 3rd: features DataFrame close price / broker quote midpoint
  │       │   └── 4th: SKIP trade record (no phantom 0-PnL trades)
  │       │
  │       ├── Get shares (pyramid layers fallback to filled_shares)
  │       ├── Compute PnL = (exit - entry) × shares × direction
  │       │
  │       ├── Create TradeRecord with:
  │       │   ├── exit_reason = _last_exit_reason.pop(sym, "live_close")
  │       │   │   (real reason from _submit_exit_order, NOT hard-coded)
  │       │   ├── confidence = real blended confidence from entry metadata
  │       │   ├── is_exploration = meta.get("exploration", False)
  │       │   └── Causal provenance fields (improve7):
  │       │       ├── entry_source: from entry metadata ("alpha"/"breakout"/"alpha+breakout"/"exploration")
  │       │       ├── regime_at_entry: from entry metadata
  │       │       ├── regime_at_exit: current regime at close
  │       │       ├── mfe: (highest_favorable - entry) × direction × shares ($)
  │       │       ├── mae: stop_distance × shares ($, conservative proxy)
  │       │       ├── bars_held_at_exit: from ExitLevels.bars_held
  │       │       └── time_in_trade_seconds: wall-clock from entry_time to now
  │       │
  │       ├── Update symbol circuit breaker (improve7, non-exploration only):
  │       │   ├── _symbol_daily_pnl[sym] += pnl
  │       │   ├── _symbol_consecutive_losses[sym] (reset on win, increment on loss)
  │       │   └── BAN if: consec_losses >= 2 OR daily_pnl <= -$15
  │       │
  │       ├── Record to continuous_learner (ALL trades including exploration)
  │       ├── Record to kelly_sizer (regime-stratified) — SKIP if exploration trade
  │       │   (prevents micro-size trades from polluting Kelly statistics)
  │       ├── Record to signal_gen calibration
  │       │
  │       ├── Immediate brain save after fills (prevent data loss on crash)
  │       └── Clean up _exit_levels, _pyramid_positions, _ml_reversal_used,
  │           _last_exit_reason, _last_exit_fill_price
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

## 14. PHASE 11: RETRAIN & EVOLVE

**Source**: `backend/organism/background_trainer.py`, `backend/organism/continuous_learner.py`, `backend/organism/self_evolution.py`

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
  │   │   └── 10 evolution sub-steps (see §23)
  │   └── Universe rotation
  │
  └── Validation Gate (continuous_learner):
      ├── Composite score = hit_rate×0.4 + accuracy×0.3 + max(dir_acc-0.5, 0.0)×0.6
      ├── No old model: accept if score > 0.25
      └── Old model exists: accept if improvement >= 5% OR
          (score >= 0.40 AND hit_rate >= 0.48)
```

---

## 15. PHASE 12: BRAIN PERSISTENCE

**Source**: `backend/organism/brain_persistence.py`

```
BRAIN SAVE (every 20 ticks ≈ 3.3 min)
  │
  ├── Walk-forward gate:
  │   ├── Checks last 100 trades (needs >= 10)
  │   ├── Regression threshold: 0.95
  │   └── IF gate rejects → DO NOT SAVE (prevents persisting regression)
  │
  ├── Full save → see §48 for complete contents list
  │   └── ML models, learning state, evolved params, exits, Kelly stats, calibration
  │
  ├── Persistence constants:
  │   ├── BRAIN_FORMAT_VERSION = 2
  │   ├── MAX_BACKUPS = 5 (rotated backups of brain state)
  │   ├── MAX_TRADE_ROWS = 10,000 (trade_history.csv, archived beyond this)
  │   └── LOCK_FILE = .brain.lock (prevents concurrent writes)
  │
  └── Transfer learning:
      └── Record run snapshot for cross-run knowledge transfer (20 snapshots max)
```

---

# LAYER 3: ALGORITHM DEEP DIVES

## 16. ML SIGNAL GENERATION

**Source**: `backend/organism/ml_signal.py`, `backend/organism/ensemble_models.py`

### Multi-Bar Prediction Horizon

The ML model predicts **H-bar-ahead** returns, not next-bar returns. This aligns the prediction horizon with the typical holding period and transaction costs.

```
prediction_horizon (H) defaults by timeframe:
  1Min  → H=15  (~15 minutes ahead)
  5Min  → H=6   (~30 minutes ahead)
  15Min → H=3   (~45 minutes ahead)
  1Hour → H=2   (~2 hours ahead)
  1Day  → H=1   (next day)

Configurable via: ORGANISM_PREDICTION_HORIZON env var
Passed to: MLSignalGenerator(prediction_horizon=PREDICTION_HORIZON)

Training targets:
  y_dir = 1 if close[t+H] > close[t] else 0
  y_ret = (close[t+H] - close[t]) / close[t]
  Feature matrix: X = features[:-H]  (last H rows dropped, no target available)
```

### Dual-Model Architecture

```
Features (79)
  │
  ├── XGBClassifier → P(up) ∈ [0, 1]
  │   ├── Time-decay weighted: ratio depends on train_window (code=200 → 2.7×, docker=100 → 1.6×, class default=250 → 3.5×)
  │   ├── Hyperparams: n_estimators=200, max_depth=5, learning_rate=0.05,
  │   │   min_child_weight=5, subsample=0.8, colsample_bytree=0.8,
  │   │   reg_alpha=0.1, reg_lambda=1.0, random_seed=42
  │   └── Fallback: sklearn GradientBoostingClassifier if XGBoost not installed
  │
  ├── XGBRegressor → predicted_return (H-bar-ahead return; training targets clipped to [-0.5, 0.5], inference unclamped)
  │   └── Same time-decay weighting + same hyperparams + sklearn fallback
  │
  ├── Optional Ensemble (40% blend):
  │   ├── Random Forest (30% weight within ensemble)
  │   ├── LightGBM (25% weight, if installed)
  │   └── XGBoost (45% weight)
  │
  └── Final blend (only when ensemble is_trained, otherwise 100% primary):
      ├── p_up = 0.6 × primary + 0.4 × ensemble
      ├── pred_return = 0.6 × primary + 0.4 × ensemble
      └── Feature mismatch at inference: missing columns zero-padded with warning
```

### Direction Decision

| P(up) | Direction | Meaning |
|---|---|---|
| > 0.52 | +1.0 (BUY) | Model is bullish |
| < 0.48 | -1.0 (SELL) | Model is bearish |
| 0.48 — 0.52 | 0.0 (HOLD) | Dead zone, no signal |

Thresholds are evolved by the evolution engine. Range [0.50, 0.70] for buy.

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
- Per-symbol: >= max(60, H+10) bars required (where H = prediction_horizon)
- Feature selection: features with evolved weight < 0.20 dropped (if fewer than 15 survive, restore top 30 by weight)
- Temporal split: 80% train, 20% validation (per-symbol to avoid cross-contamination)

---

## 17. FEATURE ENGINEERING (79 FEATURES)

**Source**: `backend/organism/ml_features.py`, `backend/organism/composite_indicators.py`, `backend/organism/multi_timeframe.py`

### 79 Features by Category

**Price Action (15):** ret_1d, ret_2d, ret_3d, ret_5d, ret_10d, ret_20d, log_ret_1d, momentum_accel, close_to_high, close_to_low, range_pct, gap_pct, body_ratio, upper_shadow, lower_shadow

**Trend (8):** sma_5, sma_10, sma_20, sma_50 (all as ratio to price), macd, macd_signal, macd_hist (all /close, normalized to price scale), adx_14

**Mean Reversion (8):** rsi_14, rsi_5 (both /100 → [0,1]), bb_position, bb_width, z_score_20, z_score_50, stoch_k, stoch_d

**Volatility (10):** atr_14 (ATR/price), atr_ratio (ATR5/ATR20), realized_vol_5, realized_vol_20, vol_ratio_5_20, parkinson_vol, garman_klass_vol, vol_regime (percentile rank), bb_squeeze (percentile rank), vol_expansion (ratio) — only realized_vol_5/20, parkinson_vol, garman_klass_vol are annualized with `sqrt(252 × bars_per_day)`; others are ratios/ranks

**Volume (8):** vol_sma_ratio, obv_slope (z-scored over 10-bar window), vol_momentum_5, vol_momentum_10, mfi_14 (/100 → [0,1]), vwap_distance, volume_breakout, pv_divergence

**Cross-Sectional (5, requires SPY):** rel_strength_spy, beta_20d, corr_to_market, idio_vol, sector_momentum

**Microstructure (5):** spread_proxy, price_impact, tick_direction, close_location, true_range_pct

**Temporal (5):** day_of_week (/4 → [0,1]), month_sin, month_cos, pct_from_52w_high, pct_from_52w_low — intraday: uses session window (bars_per_day) instead of rolling(252); daily: true 252-bar window

**Regime (4):** trend_strength, choppiness, hurst, regime_encoded

**Momentum Persistence (4):** ret_autocorr_1, ret_autocorr_5, ret_autocorr_10, hurst_exponent

**Composite Indicators (7):** comp_squeeze_momentum, comp_vol_price_div, comp_trend_alignment, comp_institutional_acc, comp_mean_rev_extreme, comp_breakout_readiness, comp_momentum_quality

### Global NaN Safety

All features: `inf → NaN → 0.0` (at the end of compute_ml_features)

### Feature Store

**Source**: `backend/organism/feature_store.py`

- SHA256 config hashing (16 chars) for versioning
- QA gates: missing bar rate > 10% = issue, NaN rate > 20% = issue, outlier count > 5 (>10 std) = issue
- DB snapshot persistence for audit trail

---

## 18. ALPHA SCANNER

**Source**: `backend/organism/alpha_scanner.py`

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

**Production mode weights** (ml_is_trained=True):

| Factor | Weight | Computation | Score Range |
|---|---|---|---|
| ML Score | 0.25 | `effective_confidence × abs(predicted_return) × 20`, cap 1.0 | [0, 1] |
| Breakout | 0.20 | `breakout_readiness × 0.6 + squeeze_momentum × 0.4` | [0, 1] |
| Institutional | 0.15 | `comp_institutional_acc` composite | [0, 1] |
| Momentum | 0.15 | Cross-sectional percentile rank of ret_20d | [0, 1] |
| Mom Quality | 0.10 | `comp_momentum_quality` composite | [0, 1] |
| Volume | 0.10 | `0.5 × vol_surge + 0.5 × vol_price_div` | [0, 1] |
| Regime | 0.05 | Regime-direction alignment table (symbol-aware for inverse ETFs) | [0.2, 1.0] |

**ML-isolated weights** (learning mode and production_guarded: ML = 0):

| Factor | Weight | Notes |
|---|---|---|
| ML Score | **0.00** | Shadow only until promotion floors pass |
| Breakout | **0.40** | Primary signal |
| Institutional | 0.15 | Same |
| Momentum | **0.20** | Boosted to compensate ML=0 |
| Mom Quality | 0.10 | Same |
| Volume | 0.10 | Same |
| Regime | 0.05 | Same |

Dynamic ML weight (full production only): if avg_conf < 0.10, ml_weight drops to 0.05; excess redistributed 60% breakout / 40% momentum.

### Modifiers

- **ML Hold penalty (full production, trained)**: direction == 0 → composite × 0.30 (70% penalty)
- **ML-isolated direction derivation**: learning or production_guarded derives direction from momentum (ret_5d > 0.005 or breakout_readiness > 0.6 → long; ret_5d < -0.005 → short), composite × 0.70 (mild 30% penalty). In this mode `ml_signal` is not carried into the candidate.
- **Symbol fitness** (improve9 B1): composite × (0.8 + fitness × 0.4) → range [0.84×, 1.18×]. Was [0.6, 1.45] — too wide for bootstrap data.
- **Stocks in Play boost** (improve9 B3): `_stocks_in_play_score()` uses vol_sma_ratio and gap_pct. Boost range [1.0×, 1.25×]. Relative volume >1.5x starts boosting (3x = max), gap >0.5% starts boosting (2% = max). 60% rvol + 40% gap weighting.
- **NaN guard**: each factor individually checked; NaN → default (0.0 or 0.5)
- **Regime stress threshold**: MIN_COMPOSITE raised to 0.50 in stress, 0.25 in high_vol
- **Inverse ETF regime flip** (improve9 B4): For SH, PSQ, DOG, RWM — regime_alignment flips trending_down↔trending_up so buying these in bearish tapes is scored as aligned.

### Selection Gate

- Minimum composite: **0.15**
- Minimum bars: 50
- Top-N: **5** candidates (improve9 B2: raised from 3 to reduce concentration risk)

---

## 19. BREAKOUT SCANNER

**Source**: `backend/organism/breakout_scanner.py`

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
- **Trend-fighting penalty**: shorting with RS > 0.5 → squeeze & pivot halved
- **Pre-filter**: composite < 0.15 → not created
- **Post-filter**: composite < 0.20 → filtered out
- **Top-N**: MAX_OPEN_POSITIONS breakout signals (code default: 8, docker: 15)

---

## 20. KELLY SIZER

**Source**: `backend/organism/kelly_sizer.py`

### Complete Sizing Formula

```
spread_cost = _estimate_spread_cost(symbol, quote_provider, features)  # [3bps, 50bps] — per-symbol dynamic cost
            = base_spread × time_mult × liquidity_mult  # bid-ask × time-of-day × volume ratio
edge_clears_cost = predicted_return >= spread_cost × 2  # edge must clear 2× cost

target_weight = (kelly_raw × 0.5)                     # Half-Kelly (requires edge-over-cost gate)
              × drawdown_scale(dd)                      # [0.1, 1.0]
              × vol_scale(stock_vol, bars_per_day)      # [0, 2.0] — ann_vol = std × √(252 × bpd)
              × regime_scale(regime)                     # [0.40, 1.20] (hardcoded) or [0.05, 1.50] (evolved range)
              × confidence_scale(conf, ml_trained)      # [0.3, 1.5]
              × breakout_bonus(brk_score, ml_trained)   # [1.0, 2.0] (capped 1.5 when untrained)
```

### Example Calculation

```
Scenario: stress regime, 5% drawdown, per-bar std 0.001 on 1-min bars,
          ML confidence 0.6, breakout score 0.4, regime Kelly = 0.12

kelly_raw = 0.12
kelly_half = 0.06
dd_scale = 1.0 - (0.05/0.25) × 0.9 = 0.82
ann_vol = 0.001 × √(252 × 390) = 0.001 × 313.5 = 0.3135 (31.4%)
vol_scale = min(0.15/0.3135, 2.0) = 0.48
regime_scale = 0.30 (stress, from evolved_params; hardcoded fallback would be 0.40)
conf_scale = 0.3 + 0.6 × 1.2 = 1.02
brk_bonus = 1.0 (< 0.5)

target_weight = 0.06 × 0.82 × 0.48 × 0.30 × 1.02 × 1.0 = 0.0072 (0.72%)

On $112K equity: notional = $806
→ SKIP: below $2,000 minimum

With hardcoded fallback (stress=0.40):
target_weight = 0.06 × 0.82 × 0.48 × 0.40 × 1.02 × 1.0 = 0.00964 (0.96%)
notional = $1,079 → Still below $2,000 minimum

NOTE: Before fix, vol was computed as 0.001 × √252 = 0.016 (1.6%, absurdly low),
causing vol_scale to hit the 2.0 cap and over-size positions by ~4×.
```

---

## 21. ADAPTIVE EXIT ENGINE

**Source**: `backend/organism/adaptive_exits.py`

### ExitLevels Dataclass (v5, improve7)

```
ExitLevels fields:
  symbol, direction, entry_price, stop_loss, take_profit, trailing_stop,
  atr_at_entry, regime_at_entry, highest_favorable, bars_held (1-min bars, NOT 10s ticks),
  partial_tp_price, partial_tp_taken, trailing_active, stress_tightened, profit_locked,
  last_bar_time (v3: bar boundary tracking), prediction_horizon (v3: ML horizon, default=15),
  price_at_prior_bar (v4: FTF momentum confirmation — tracks price at previous bar),
  ftf_stop_tightened (v5: True after FTF tightened stop in chop, one-shot),
  price_two_bars_ago (v5: 2-bar-ago price for multi-bar FTF momentum check)
```

### Exit Level Creation from Entry

```
entry_price = $150.00
ATR(14) = $3.00
regime = "unknown" (default)
prediction_horizon = 15 (1-min bars)

risk_distance = $3.00 × 1.5 (unknown stop ATR) = $4.50

stop_loss     = $150.00 - $4.50 = $145.50
take_profit   = $150.00 + $4.50 × 4.0 (unknown TP R) = $168.00
partial_tp    = $150.00 + $4.50 × 3.0 = $163.50
trailing_stop = $145.50 (starts at stop loss)
trailing_activation = $150.00 + $3.00 × 2.0 = $156.00  (for_timeframe sets 2.0 for both intraday/daily)

min_hold = max(15 // 3, 3) = 5 bars (5 min)
failure_to_follow_delay = chop: max(15 × 4/5, 5) = 12 bars; other: max(15 // 2, 3) = 7 bars
```

### Trailing Stop Mechanics

```
When price reaches $156 (2 ATR above entry, via for_timeframe):
  → trailing_active = True

At peak $165 (regime still "unknown"):
  trail_distance = $3.00 × 2.5 = $7.50
  new_trail = $165 - $7.50 = $157.50
  trailing_stop = max($145.50, $157.50) = $157.50  ← RATCHETED UP

If price drops to $157.50 → EXIT via trailing stop
```

---

## 22. REGIME DETECTOR

**Source**: `backend/organism/regime.py`

### Feature Extraction → Probability → Smoothing → Label

```
Raw Data → 4 Signals (RegimeDetector defaults: sma_period=50, vol_lookback=20, churn_window=20):
  ├── Trend slope (SMA slope over 10 bars, threshold=±0.02 daily)
  │   **improve7**: trend_threshold now scaled by 1/√bpd for intraday
  │   (was static 0.02, which effectively prevented trending_up from ever triggering on 1-min bars)
  ├── Price vs SMA distance (threshold=±0.02, scaled by 1/√bpd for intraday)
  ├── atr_14 (ATR(14)/price): atr_high=0.04, atr_low=0.015 (scaled for intraday)
  │   + returns vol threshold=0.03 (scaled for intraday)
  └── Volume anomaly

  Intraday scaling: 4× lookback periods, ALL thresholds × (1/√bpd) including trend
  For 1Min (bpd=390): trend=~0.001, pct_above=~0.001, atr_high=~0.002, atr_low=~0.0008, ret_vol=~0.0015
  (trend threshold reduction allows micro-trends to be detected, preventing permanent chop classification)

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

### Additional Components

- **RegimeConditionedEnsemble**: Blends strategy weights per regime, probability-weighted across all regimes, clamped to [0.10, 2.50]:

| Regime | momentum | regime_mom | breakout | mean_rev | stat_arb |
|---|---|---|---|---|---|
| trending_up | 1.4 | 1.5 | 1.3 | 0.7 | 0.8 |
| trending_down | 0.7 | 0.6 | 0.8 | 1.3 | 1.2 |
| chop | 0.8 | 0.7 | 0.6 | 1.4 | 1.3 |
| high_vol | 0.9 | 0.8 | 1.1 | 1.0 | 0.9 |
| low_vol | 1.1 | 1.2 | 1.0 | 1.1 | 1.0 |
| stress | 0.5 | 0.4 | 0.7 | 1.5 | 1.4 |

- **DriftDetector**: PSI-based feature drift detection (threshold=0.10, n_bins=10)
- **Churn Detection**: Window of 20 labels (intraday: ×4 = 80); changes / (window - 1) = churn rate
- **Volume Anomaly**: `(mean(volume[-5:]) / mean(volume[-50:])) - 1.0`, requires >= 20 bars
- **History truncation**: `churn_window × 2` entries (40 daily, 160 intraday)
- **SMA column fallback**: tries sma_50 → sma_20 → SMA_50 → SMA_20 → close
- **ATR column fallback**: tries atr_14 → atr_14_ratio → ATR_ratio → default 0.02

---

## 23. SELF-EVOLUTION ENGINE

**Source**: `backend/organism/self_evolution.py`

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
  ├── Step 5: Symbol Fitness (improve9 B1: canonical unified system)
  │   ├── symbol_trade_counts tracked per symbol (canonical source: trade recording)
  │   ├── <10 trades: fitness locked at neutral (0.5) — insufficient data
  │   ├── 10+ trades: EMA-smoothed fitness update from win_rate × avg_pnl
  │   ├── Decay is trade-count-based (not epoch): <10: snap neutral, 10-30: 15%, 30+: 5%
  │   └── Fitness bounds: 0.10 – 0.95
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
  │   ├── Losing + long holds → shorten periods
  │   └── Losing + short holds → lengthen periods
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

```
delta = α × new + (1-α) × old - old
max_delta = |old| × 0.20 + 0.005     # max 20% shift per step
clamped_delta = clamp(delta, -max_delta, max_delta)
result = old + clamped_delta
```

### Key Evolved Parameters

`stop_atr_scale`, `trailing_start_atr_scale`, `trailing_distance_scale`, `partial_tp_r_scale`, `partial_tp_pct`, `regime_size_scales` (7-regime dict), `shorts_enabled`, `direction_threshold_buy`, `direction_threshold_sell`, `alpha_weight_ml/volume/momentum/breakout/regime`, `breakout_weight_squeeze/volume/contraction/rs/pivot/flow`, `breakout_bb_period/atr_short/atr_long/pivot_lookback/vol_avg_period/rs_period`, XGBoost hyperparams (`n_estimators`, `max_depth`, `learning_rate`, `subsample`, `colsample_bytree`)

### EvolvedParams Defaults vs Runtime Defaults

NOTE: Several parameters have **different defaults** in the evolution engine vs the runtime modules:

| Parameter | EvolvedParams Default | Runtime Module Default | Active Source |
|---|---|---|---|
| `direction_threshold_buy` | 0.55 | 0.52 (ml_signal.py) | Evolved overrides runtime |
| `direction_threshold_sell` | 0.45 | 0.48 (ml_signal.py) | Evolved overrides runtime |
| `partial_tp_pct` | 0.20 | 0.30 (adaptive_exits base) | Evolved overrides base |
| `alpha_weight_ml` | 0.35 | 0.25 (alpha_scanner.py) | Evolved overrides scanner |
| `alpha_weight_volume` | 0.20 | 0.10 (alpha_scanner.py) | Evolved overrides scanner |
| `alpha_weight_momentum` | 0.20 | 0.15 (alpha_scanner.py) | Evolved overrides scanner |
| `alpha_weight_breakout` | 0.15 | 0.20 (alpha_scanner.py) | Evolved overrides scanner |
| `alpha_weight_regime` | 0.10 | 0.05 (alpha_scanner.py) | Evolved overrides scanner |

When `ORGANISM_FREEZE_ADAPTATION=1`, evolved_params do NOT update but still override runtime defaults.
The brain file `organism_brain/evolved_params.json` stores the current evolved state.

### Evolution Parameter Bounds

| Parameter | Lower Bound | Upper Bound |
|---|---|---|
| `stop_atr_scale` | 0.6 | 1.8 |
| `trailing_distance_scale` | 0.5 | 1.6 |
| `partial_tp_r_scale` | — | 1.8 |
| `partial_tp_pct` | 0.15 | 0.50 |
| `regime_size_scales` (each) | 0.05 | 1.50 |
| `direction_threshold_buy` | 0.50 | 0.70 |
| `direction_threshold_sell` | loosely coupled: 1.0 - buy | — |
| `symbol_fitness` | 0.10 | 0.95 |
| `breakout_weight_*` (each) | 0.10 | 0.40 |
| `alpha_weight_momentum` | 0.05 | 0.35 |
| `alpha_weight_regime` | — | 0.25 |
| `xgb_n_estimators` | 100 | 500 |
| `xgb_max_depth` | 3 | 8 |
| `xgb_learning_rate` | 0.01 | 0.15 |
| `xgb_subsample` | 0.60 | 1.0 |
| `xgb_colsample_bytree` | 0.60 | 1.0 |

Breakout period bounds: `breakout_bb_period (10,40)`, `breakout_atr_short (5,20)`, `breakout_atr_long (20,80)`, `breakout_pivot_lookback (10,40)`, `breakout_vol_avg_period (10,40)`, `breakout_rs_period (10,40)`.

Hard floor enforcement on restore: `high_vol >= 0.70`, `stress >= 0.30` (from `EvolvedParams.from_dict()`).

**Regime evolution freeze (improve7)**: `_regime_scale()` in kelly_sizer only uses evolved scales when total trades >= 200 AND trades in the specific regime >= 30. Below that threshold, hardcoded static scales are used. This prevents statistically unstable early evolved values from causing mis-sizing.

**Full evolution freeze (improve9 B5)**: ALL self-evolution (signal weights, exit params, regime scales, breakout weights, XGB hyperparams, direction thresholds, feature selection, symbol fitness EMA) is frozen until at least **300** clean post-reset trades. Only ML retraining + calibration map updates run. Symbol trade counts continue incrementing at the trade recording source (B1) regardless of freeze.

Step 2 guard: stop tightening requires `>= 2` stop-loss trades.
Step 7 detail: after adjusting individual breakout weights, `_normalize_breakout_weights()` re-normalizes all 6 to sum=1.0; each clamped to [0.10, 0.40] before normalization.

### Additional Evolved Fields

- `symbol_trade_counts: dict[str, int]` — per-symbol closed trade counts (improve9 B1: canonical source, incremented at trade recording, NOT in evolution)
- `short_win_rate`, `short_avg_pnl`, `short_trade_count` — EMA-tracked short-side stats
- `evolution_generation`, `total_adaptations` — metadata counters
- `profit_lock_r` — has `_base_profit_lock_r` field but is NOT evolved (fixed at 2.0R)

---

## 24. UNIVERSE & SECTOR MANAGEMENT

**Source**: `backend/organism/universe_selector.py`, `backend/organism/sector_map.py`, `backend/organism/market_scanner.py`

### Dynamic Universe Rotation

```
ROTATION (on retrain):
  │
  ├── Update fitness from recent trades:
  │   └── fitness = 0.6 × win_rate + 0.4 × (0.5 + pnl_norm/2)
  │
  ├── Decay all fitness toward 0.50 (trade-count-based, improve9 B1: <10 trades snap neutral, 10-30: 15%, 30+: 5%)
  │
  ├── DROP (up to 5 symbols):
  │   ├── No open position
  │   ├── >= 3 total_trades (MIN_OBSERVATIONS)
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
| ETF | SPY, QQQ, IWM, XLK, XLE, **SH**, **PSQ** | 4 |
| Healthcare | LLY | 4 |
| Energy | XOM | 4 |
| Industrials | CAT | 4 |
| Financials | COIN, SQ | 4 |
| Unknown | Any new scanner finds | NEVER BLOCKED |

Tracks `planned_entries` within a single tick to prevent multiple same-sector entries in one cycle.

### Market Scanner

```
MARKET SCANNER (every 6 ticks ≈ 60s)
  │
  ├── 3 concurrent API calls:
  │   ├── Most-actives by volume (top 100)
  │   ├── Top gainers (top 50)
  │   └── Top losers (top 50)
  │
  ├── Exclusion: 28 leveraged/inverse ETFs
  ├── Price filter: [$10, $1500]
  ├── Volume filter: >= 500,000 (daily volume)
  ├── Market cap filter: >= $1B (SCAN_MIN_MARKET_CAP)
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

## 25. BACKGROUND TRAINING & TRANSFER LEARNING

**Source**: `backend/organism/background_trainer.py`, `backend/organism/transfer_learning.py`

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

---

## 25a. DECISION TELEMETRY

**Source**: `backend/organism/decision_telemetry.py`

Per-tick transparency layer capturing every indicator, threshold, and decision gate for frontend visualization.

### Data Structures

```
SymbolAlphaDetail:
  - 7-factor alpha breakdown with composite score
  - min_composite_threshold: 0.15
  - fitness_gate: 0.0 (learning, no gate) / 0.45 (production, 10+ trades only); telemetry uses matching value

SymbolBreakoutDetail:
  - 6-pattern breakout breakdown (squeeze, volume, contraction, RS, pivot, flow)
  - min_breakout_threshold: 0.20

PositionExitDetail:
  - Per-position exit proximity (stop_loss, take_profit, trailing_stop, partial_tp, time)
  - ATR info, regime_at_entry, nearest_exit condition

KellySizingDetail:
  - Per-candidate 8-stage pipeline: kelly_raw → kelly_half → drawdown_scale →
    vol_scale → regime_scale → confidence_scale → breakout_bonus → final_weight
  - ml_floor_applied flag, shares, notional, direction

FilteringSummary:
  - Funnel counts: total_universe → had_features → alpha_scored → above_alpha_threshold
    → breakout_scored → above_breakout_threshold → passed_sector_gate → passed_fitness_gate
    → passed_cooldown → passed_position_limit → kelly_sized → orders_submitted
  - Per-gate rejection counters (11):
    open_position, exit_cooldown, pending_entry, entry_metadata, long_only,
    sector_gate, fitness_gate, liquidity, missingness, cost_gate, min_notional
  - entries_blocked_reason: "" | "governance_halt" | "warmup" | "insufficient_data" |
    "equity_zero" | "drawdown_kill" | "spy_ma_filter" | "opening_block" |
    "regime_sitout" | "throttle" | "stale_data"
  - learning_mode: bool (True when < 200 completed trades)
  - trading_phase: "learning" | "production_frozen" | "production_guarded" | "production"
  - guarded_mode / ml_isolation_mode / fixed_risk_sizing: bool flags from trading_phase
  - promotion_blockers: list of realized-expectancy floors blocking full production
  - strategy_total_trades / strategy_cumulative_pnl / strategy_win_rate /
    strategy_sharpe_ratio_per_trade: reconciliation-artifact-filtered stats
    used by the promotion gate
  - `/api/v1/health/strategy` top-level expectancy uses the same
    strategy-only scope; when reconciliation rows are present it also
    exposes `all_records_expectancy` and `excluded_reconciliation_artifacts`
    so operators can reconcile headline strategy PnL against raw ledger PnL.
  - effective_max_entries_per_hour: int (12 in learning, max(3, 6-open_positions) in production)
  - effective_fitness_gate: float (0.0 in learning = no gate, 0.45 in production for 10+ trade symbols)
  - burst_cap_remaining: int (entries left in rolling 15-min window, max 4)
  - cost_gate and min_notional wired from kelly_sizer._exploration_rejects

DecisionSnapshot:
  - tick_number, timestamp, duration_s
  - regime (primary, probabilities, confidence, features)
  - governance (equity, peak_equity, drawdown_pct, is_halted, is_frozen)
  - evolution (generation, params summary)
  - alpha_details: list[SymbolAlphaDetail]
  - breakout_details: list[SymbolBreakoutDetail]
  - exit_details: list[PositionExitDetail]
  - kelly_details: list[KellySizingDetail]
  - filtering: FilteringSummary
  - open_positions, max_positions

Ring Buffer:
  - Capacity: 360 ticks (~1 hour at 10s intervals)
  - In-memory ring buffer for real-time API access

DB Persistence (TickTelemetry table):
  - Written every 6th tick (~1/min at 10s intervals)
  - Fields: tick_number, timestamp, regime, equity, drawdown_pct, open_positions,
    entries_blocked_reason, orders_submitted, gate_rejections (JSON),
    top_candidates (JSON), exit_decisions (JSON)
  - 7-day retention with daily cleanup (every 2160 ticks ≈ 6 hours)
  - ~1.2 MB/day at 390 rows/day (~390 trading minutes)
  - Table created by Alembic migration `20260303_000001_add_tick_telemetry`

TradeRecord (continuous_learner.py):
  - symbol, direction, entry_price, exit_price, entry_bar, exit_bar
  - shares, pnl, exit_reason, predicted_return, actual_return, confidence
  - is_exploration: bool (False for main trades, True for exploration bucket)
  - Causal provenance fields (improve7):
    - entry_source: str ("alpha", "breakout", "alpha+breakout", "exploration")
    - regime_at_entry: str (regime label at position open)
    - regime_at_exit: str (regime label at position close)
    - mfe: float (max favorable excursion in $)
    - mae: float (max adverse excursion in $)
    - bars_held_at_exit: int (actual 1-min bars held)
    - time_in_trade_seconds: float (wall-clock duration)
```

### Safe Type Conversion

```python
_f(val)  # numpy.float64 → Python float (handles NaN/inf → 0.0, NOT None)
_b(val)  # numpy.bool_ → Python bool (via bool(v) — truthy values return True)
```

Required because FastAPI cannot serialize numpy types.

### API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/organism/decisions` | Latest decision snapshot |
| GET | `/organism/decisions/history` | Full ring buffer contents |
| GET | `/organism/decisions/symbol/{sym}` | Symbol-specific decision trail |
| GET | `/organism/decisions/exits` | Exit decision history |
| GET | `/organism/evolution/history` | Evolution parameter history |

---

## 25b. REPLAY SIMULATOR

**Source**: `backend/organism/replay_simulator.py`

Historical bar replay engine for backtesting. Feeds historical bars through the actual `live_tick()` pipeline one-at-a-time.

### Components

```
SimulatedBroker:
  - Implements PositionsService + OrderService interfaces
  - Tracks: fills, positions, cash, equity
  - Configurable slippage_bps (default: 0)
  - initial_cash: $100,000

HistoricalBarProvider:
  - Feeds bars sequentially from historical data
  - One bar per tick (no look-ahead)

ReplayEngine:
  - Orchestrates replay through OrganismLiveEngine.live_tick()
  - Uses real engine code path — not a separate backtester

ReplayResult:
  - trades: list of executed trades
  - equity_curve: time series of portfolio value
  - metrics: Sharpe, max drawdown, win rate, etc.
```

### CLI Usage

```bash
python -m backend.organism.replay_simulator \
  --symbols AAPL,MSFT,SPY \
  --start 2026-02-01 \
  --end 2026-02-25
```

---

## 25c. ENSEMBLE MODELS

**Source**: `backend/organism/ensemble_models.py`

Phase 4.4 — Wraps XGBoost with Random Forest + optional LightGBM using soft-vote strategy.

### Soft-Vote Ensemble

```
EnsemblePredictor:
  │
  ├── Model A: XGBoost classifier → P(up)_A, return_A
  ├── Model B: RandomForest → P(up)_B, return_B
  └── Model C: LightGBM (optional) → P(up)_C, return_C

  Final P(up) = Σ(weight_i × P(up)_i) / Σ(weight_i)
  Final return = Σ(weight_i × return_i) / Σ(weight_i)

  Weights: start equal, adapted by EvolutionEngine
           based on per-model accuracy
```

### Optional Dependencies

- XGBoost (primary)
- sklearn RandomForest + GradientBoosting
- LightGBM (optional, gracefully degraded)
- Model stubs return neutral predictions (0.0) when libraries unavailable

---

## 25d. COMPOSITE INDICATORS

**Source**: `backend/organism/composite_indicators.py`

7 proprietary composite trading indicators combining 3-5 base indicators into normalized [0, 1] scores.

### Composites

| # | Name | What It Measures |
|---|---|---|
| 1 | Squeeze Momentum | Volatility compression + directional energy |
| 2 | Volume-Price Divergence | Smart money vs dumb money flow |
| 3 | Trend Alignment | Multi-timeframe trend consensus |
| 4 | Institutional Accumulation | Large block flow detection |
| 5 | Mean Reversion Extremity | Multi-indicator oversold/overbought |
| 6 | Breakout Readiness | Pre-breakout tension scoring |
| 7 | Momentum Quality | Sustainable vs fading momentum |

### Normalization

```
_norm_01(series, window=60):
  60-bar rolling percentile rank → [0, 1]
  Uses ranking rather than min/max to handle outliers
```

---

## 25e. FEATURE STORE

**Source**: `backend/organism/feature_store.py`

Phase 2 — Versioned feature store ensuring online/offline parity.

### Architecture

```
FeatureStore:
  │
  ├── Config versioning (hash-based)
  │     feature_groups: [trend, mean_reversion, volatility, liquidity, regime]
  │     feature_mode: "realtime_light"
  │     enable_heavy_features: false
  │     enable_autocorr_features: false
  │
  ├── Snapshot persistence (disk-based)
  │
  └── Data QA gates:
      FeatureQAReport:
        - passed: bool
        - nan_pct: float (% missing values)
        - outlier_count: int
        - issues: list[str]
        - row_count validation
```

---

## 25f. MULTI-TIMEFRAME FEATURES

**Source**: `backend/organism/multi_timeframe.py`

Phase 4.2 — Derives higher-timeframe features from bar stream without lookahead bias.

### Resampling Rules

| Input Timeframe | Higher TF 1 | Higher TF 2 |
|---|---|---|
| Daily bars | Weekly (5 bars) | Monthly (21 bars) |
| 15Min bars | Daily (26 bars) | Weekly (130 bars) |

### Implementation

```
Rolling aggregation (NOT calendar resample):
  - Uses N-bar rolling window to prevent lookahead bias
  - Feature naming: mtf_{timeframe}_{indicator}
  - Examples: mtf_w_rsi_14, mtf_m_sma_trend

Bars-per-day map:
  1min: 390, 5min: 78, 15min: 26, 30min: 13, 1hour: 7
```

---

# LAYER 4: EXTERNAL INTEGRATION — ALPACA BROKER

## 26. ORDER SUBMISSION PIPELINE

**Source**: `backend/integrations/alpaca_broker.py`

### Place Order Parameters

```python
symbol:          str          # Uppercase stock symbol
side:            str          # "buy"/"sell"/"long"/"short" (mapped to buy/sell)
qty:             int          # Number of shares (integer)
type:            str          # "market" (default), "limit", "stop", "stop_limit"
tif:             str          # "day" (default), "gtc", "opg", "cls", "ioc", "fok"
limit_price:     float|None   # Required for limit/stop_limit orders
stop_price:      float|None   # Required for stop/stop_limit orders
client_order_id: str|None     # Optional idempotency key
```

### HTTP Request to Alpaca

```
POST {base_url}/v2/orders
  Paper: https://paper-api.alpaca.markets/v2/orders
  Live:  https://api.alpaca.markets/v2/orders

Payload:
{
  "symbol": "AAPL",
  "side": "buy" | "sell",
  "type": "market" | "limit" | "stop" | "stop_limit" | "trailing_stop",
  "time_in_force": "day" | "gtc" | "opg" | "cls" | "ioc" | "fok",
  "qty": "100",                        # String (not integer)
  "client_order_id": "order_abc12345", # For idempotency
  "limit_price": "150.25",            # Optional, string
  "stop_price": "149.50"              # Optional, string
}
```

### Response Format

```json
{
  "id": "uuid-order-id",
  "client_order_id": "order_abc12345",
  "status": "new" | "accepted" | "partially_filled" | "filled" | "canceled" | "expired" | "rejected",
  "symbol": "AAPL",
  "qty": "100",
  "filled_qty": "50",
  "filled_avg_price": "150.24" | null,
  "type": "market",
  "side": "buy",
  "time_in_force": "day",
  "created_at": "2025-02-26T14:30:00Z"
}
```

### Retry Strategy

```
max_retries: 3
backoff_factor: 1.0
  Attempt 0: 1s
  Attempt 1: 2s
  Attempt 2: 4s
  Attempt 3: Final, no retry

Retryable: 429, 500, 502, 503, 504, TimeoutException, ConnectError
Non-retryable: 400-499 (except 429)
```

### Order Status Mapping (Alpaca → Internal)

| Alpaca Status | Internal Status |
|---|---|
| new | submitted |
| accepted | accepted |
| pending_new | pending |
| pending_cancel | pending_cancel |
| partially_filled | partially_filled |
| filled | filled |
| canceled | cancelled |
| expired | expired |
| rejected | rejected |

---

## 27. OUTBOX DISPATCHER

**Source**: `backend/integrations/alpaca_outbox.py`

### Smart Time-In-Force Selection

- Default to `day` (intraday-only system prevents overnight exposure)
- Check market hours: 9:30 AM - 4:00 PM ET, Monday-Friday
- GTC only used when explicitly requested
- Falls back to `day` if timezone parsing fails

### Dispatch Flow

```
AlpacaOutboxDispatcher:
  1. Routes to mock broker (if USE_MOCK_BROKER=true) OR real Alpaca
  2. Extracts: symbol, side, qty, order_type, limit_price, stop_price, client_key
  3. Converts qty to int: int(float(event_data.get("qty", 0)))
  4. Calls broker.place_order() with smart TIF
  5. Returns: {success, broker_order_id, status, message}
```

---

## 28. IDEMPOTENCY & DEDUPLICATION

**Source**: `backend/integrations/alpaca_broker.py`

```
BEFORE PLACING ORDER:
  1. Check if order already exists: get_order(client_order_id)
  2. If found → return existing order (idempotent)
  3. If not found (404/422/502) → proceed with placement

ON DUPLICATE (422 "client_order_id must be unique"):
  → GET /v2/orders:by_client_order_id?client_order_id={id}
  → Return recovered existing order instead of failing
```

---

## 29. WEBSOCKET TRADE UPDATES

**Source**: `backend/integrations/alpaca_stream.py`

### Connection

```
WebSocket URL:
  Paper: wss://paper-api.alpaca.markets/stream
  Live:  wss://api.alpaca.markets/stream

Parameters:
  ping_interval: 30s
  ping_timeout: 10s
  close_timeout: 10s

Auth: {"action": "auth", "key": "{API_KEY}", "secret": "{SECRET}"}
Subscribe: {"action": "listen", "data": {"streams": ["trade_updates"]}}
```

### Incoming Trade Update Format (Alpaca v2)

```json
{
  "T": "trade_updates",
  "data": {
    "event": "fill" | "partial_fill" | "canceled" | "rejected",
    "order": {
      "id": "broker-order-uuid",
      "client_order_id": "order_abc12345",
      "status": "filled",
      "filled_qty": "100",
      "filled_avg_price": "150.24"
    }
  }
}
```

### Processing Pipeline

```
1. Extract order data: event_data.get("order", event_data)
2. Map status: _map_alpaca_status(status)
3. Find order in DB:
   - Primary: get_by_broker_order_id(broker_order_id)
   - Fallback: get_by_client_key(client_order_id)
   - Backfill broker_order_id if found via client_key
4. Update DB: attach_broker_result(order_id, status, filled_qty, avg_fill_price)
5. Broadcast to frontend via Socket.IO
```

### Queue Management

- Unbounded asyncio.Queue (trade updates MUST NOT be dropped)
- High water mark tracking at 500 items
- Queue overflow triggers warning

### Reconnection Strategy

```
reconnect_delay: 1.0s (initial)
max_reconnect_delay: 60.0s
reconnect_multiplier: 2.0x
max_reconnect_attempts: 10

Schedule: 1s → 2s → 4s → 8s → 16s → 32s → 60s (capped)

Slow-Retry Mode (after 10 failures):
  5m → 10m → 20m → 30m (capped)
  Emits CRITICAL alert
```

### Heartbeat

- Ping every 30s
- Stale detection: no heartbeat in 60s → warning

---

## 30. MARKET DATA STREAM

**Source**: `backend/integrations/alpaca_market_data_stream.py`

### Connection

```
WebSocket URL: wss://stream.data.alpaca.markets/v2/{feed}
  feed: "sip" (paid, full consolidated) or "iex" (free, single exchange)

Parameters:
  ping_interval: 20s
  ping_timeout: 10s
  close_timeout: 10s
```

### Subscription Types

```
Bars:   {"action": "subscribe", "bars": ["AAPL", "TSLA"]}
Quotes: {"action": "subscribe", "quotes": ["AAPL", "TSLA"]}
Trades: {"action": "subscribe", "trades": ["AAPL", "TSLA"]}
```

### Message Formats

**Bar** (`T: "b"`): open, high, low, close, volume, trade_count, vwap, timestamp
**Quote** (`T: "q"`): bid/ask price+size+exchange, conditions, mid (calculated), spread (calculated)
**Trade** (`T: "t"`): price, size, exchange, conditions, tape, timestamp

### Callbacks

```python
on_quote: Callable[[str, dict], Any]  # (symbol, quote_data)
on_trade: Callable[[str, dict], Any]  # (symbol, trade_data)
on_bar:   Callable[[str, dict], Any]  # (symbol, bar_data)
on_error: Callable[[str], Any]        # (error_msg)
```

### Reconnection

```
INITIAL_BACKOFF: 1.0s
MAX_BACKOFF: 300.0s (5 minutes)
BACKOFF_MULTIPLIER: 1.5x
MAX_RECONNECT_ATTEMPTS: 10
Jitter: ±10% random

On reconnect: snapshot desired subscriptions → clear tracking → re-subscribe all
```

---

## 31. HISTORICAL DATA & POSITIONS

**Source**: `backend/integrations/alpaca_data.py`, `backend/integrations/alpaca_broker.py`

### Historical Bars

```
GET {data_url}/v2/stocks/{symbol}/bars
  data_url: https://data.alpaca.markets/v2

Parameters:
  timeframe:  "1Day" | "1Hour" | "5Min" | "15Min" | "1Min"
  adjustment: "split"
  limit:      lookback × 2 (filtering buffer)
  sort:       "asc"
  feed:       "sip" | "iex"

Retry: 2 attempts, 200ms base backoff (fail-fast for HFT)
```

### Positions

```
GET /v2/positions         → List[Position] (all open positions)
GET /v2/positions/{sym}   → Position | None (404 = no position, not error)
GET /v2/account           → Account (equity, cash, buying_power, etc.)
DELETE /v2/orders/{id}    → 204 success, 404/422 already filled/expired
```

### Order Cancellation Response Handling

- 204: Success (order canceled)
- 404: Order not found (already filled or expired)
- 422: Order cannot be canceled
- 502/503: Server error (retryable)

---

## 31a. PRODUCTION STREAM CLIENT

**Source**: `backend/integrations/alpaca_stream_production.py`

Production-hardened WebSocket stream with gap-filling and robustness enhancements beyond `alpaca_stream.py`.

### Features Beyond Base Stream

```
StreamState (persistent):
  - Tracks last_event_ts in DB for gap detection
  - load_from_db() on startup
  - update_last_event() on each message

Gap-Fill on Reconnect:
  - Queries REST API for events since last_event_ts
  - Default: start from 1 hour ago if no events exist
  - Deduplicates against order_events table

Robustness:
  - Jittered exponential backoff for reconnections
  - Comprehensive error classification
  - Circuit breaker integration (infra/resilience.py)
  - Event deduplication using order_events table
```

### Dependencies

Uses `TransactionalGuardrails`, `OrdersRepo`, `AlpacaBrokerClient`, and `LotTracker` for fill processing within DB transactions.

---

# LAYER 5: INFRASTRUCTURE

## 32. TRANSACTIONAL OUTBOX & DLQ

**Source**: `backend/infra/outbox.py`, `backend/infra/outbox_worker.py`

### Outbox Pattern

```
APPLICATION TRANSACTION:
  1. Create Order in DB
  2. Enqueue OutboxEvent (topic="order.submitted") in SAME transaction
  3. Commit — both or neither persist (atomicity)

OUTBOX WORKER (background, 100ms poll):
  1. claim_batch(10) with FOR UPDATE SKIP LOCKED (no contention)
  2. For each event:
     ├── Route by topic: "order.submitted" → broker dispatch
     ├── Shadow/dry_run/mock/real broker based on execution mode
     ├── Success → mark_sent()
     ├── Retryable failure → mark_retry() with backoff
     └── Max retries (5) or validation error → DLQ
  3. DLQ: mark_failed() + broadcast "order.rejected" via WebSocket
```

### Backoff Calculator

```
base_delay_ms: 200
max_delay_ms: 10000
jitter_ms: 150
delay = min(base × 2^attempt + random(0, jitter), max_delay)
```

### Outbox Worker Config

| Parameter | Value | Purpose |
|---|---|---|
| `poll_interval` | 0.1s (100ms) | HFT-optimized polling |
| `max_retries` | 5 | Before DLQ |
| `initial_backoff` | 1.0s | First retry delay |
| `max_backoff` | 300s | Cap on retry delay |
| `jitter_factor` | 0.1 | Prevents thundering herd |

### Prometheus Metrics

`outbox_polled_total`, `outbox_dispatched_total[topic,status]`, `outbox_dispatch_latency_seconds[topic]`, `outbox_queue_gauge[status]`, `broker_submit_total[result]`, `broker_submit_latency_seconds`

---

## 33. ORDER GUARDRAILS

**Source**: `backend/infra/guardrails.py`, `backend/infra/guardrails_production.py`, `backend/infra/order_guardrails.py`

### 8-Layer Validation (Pre-Submission)

```
ORDER REQUEST
  │
  ├── Layer 1: Trading paused? → REJECT
  ├── Layer 2: Within trading window? (9:30-16:00 ET) → REJECT
  ├── Layer 3: Symbol in whitelist? → REJECT
  ├── Layer 4: Order size <= max? (100 shares default) → REJECT
  ├── Layer 5: Daily order count <= max? (100/day default) → REJECT
  ├── Layer 6: Daily notional <= cap? ($10K default) → REJECT
  ├── Layer 7: Rate limit? (10/min default) → REJECT
  └── Layer 8: Circuit breaker open? → REJECT
```

### Production Guardrails (Atomic)

```
TransactionalGuardrails:
  - SELECT FOR UPDATE on DailyLedger (race-condition-free)
  - Atomic check + increment of daily counters
  - Circuit breaker: opens after 10 consecutive BROKER_DOWN/NETWORK_ERROR in 5 min
  - Deduplication via unique constraint
```

### Post-Submission Safety

```
OrderGuardrails:
  - ALPACA_ORDER_TIMEOUT: 30s (submission timeout)
  - ALPACA_VERIFY_TIMEOUT: 10s (verification timeout)
  - STALE_PENDING_THRESHOLD: 5 min → mark as failed
  - STALE_ACCEPTED_THRESHOLD: 24 hr → flag for reconciliation
  - Stale cleanup runs every 15 min
```

### Guardrail Config

| Parameter | Default | Env Variable |
|---|---|---|
| Symbol whitelist | AAPL,MSFT,GOOGL,TSLA,NVDA,SPY,QQQ | `SYMBOL_WHITELIST` |
| Daily notional cap | $10,000 | `DAILY_NOTIONAL_CAP_USD` |
| Max daily orders | 100 | `MAX_DAILY_ORDERS` |
| Max order size | 100 shares | `MAX_ORDER_SIZE` |
| Max orders/min | 10 | `MAX_ORDERS_PER_MINUTE` |
| Circuit breaker | 5.0% | `CIRCUIT_BREAKER_PCT` |
| Admin override | true | `RISK_ALLOW_ADMIN_OVERRIDE` |
| Fallback price | $500/share | (hardcoded, conservative) |

---

## 34. RESILIENCE LAYER

**Source**: `backend/infra/resilience.py`

### Circuit Breaker

```
States: CLOSED → OPEN → HALF_OPEN → CLOSED (or back to OPEN)

Config:
  failure_threshold: 5 consecutive failures → OPEN
  recovery_timeout: 60s in OPEN → try HALF_OPEN
  success_threshold: 3 successes in HALF_OPEN → CLOSED
  timeout: 30s per call

Prometheus: state_changes_total, requests_total, timeout_occurrences_total
```

### Exponential Backoff

```
RetryConfig:
  max_attempts: 3
  base_delay: 1.0s
  max_delay: 60s
  backoff_multiplier: 2.0
  jitter: True (prevents thundering herd)

delay = min(base × multiplier^attempt + random_jitter, max_delay)
```

### Retry Manager

- Executes with retry around any async function
- Best-effort session rollback between attempts
- DLQ on max retries exhausted
- Prometheus: `retry_attempts_total`, `dlq_messages_total`, `backoff_delay_seconds`

### OrderService Circuit Breaker (Redis-Backed)

**Source**: `backend/services/order_service.py`

A **separate** circuit breaker from infra/resilience.py, with Redis persistence for distributed state.

```
OrderService CircuitBreaker:
  │
  ├── States: CLOSED → OPEN → HALF_OPEN → CLOSED
  │
  ├── Trip Conditions (ANY):
  │   ├── 5 failures (not necessarily consecutive) within 300s window → OPEN
  │   └── Daily PnL loss > 5% (strictly greater than) → OPEN (PnL-triggered kill)
  │
  ├── reduce_only Bypass:
  │   └── Exit orders (reduce_only=True) skip the ENTIRE circuit breaker — never block risk-reducing orders
  │
  ├── Daily Reset:
  │   └── Auto-resets PnL + failure counts at 9:30 AM ET on new trading day (Redis key TTL: 24h)
  │
  ├── Recovery:
  │   ├── 60s in OPEN → transition to HALF_OPEN
  │   └── 3 successes in HALF_OPEN → CLOSED
  │
  ├── Redis Keys:
  │   ├── circuit_breaker:order_flow:state
  │   ├── circuit_breaker:order_flow:failures
  │   ├── circuit_breaker:order_flow:opened_at
  │   ├── circuit_breaker:order_flow:daily_pnl
  │   └── circuit_breaker:order_flow:last_reset_date
  │
  └── Fallback: In-memory state if Redis unavailable
      └── Uses both epoch (persistence) and monotonic (time windows) clocks
```

| Parameter | Value | Purpose |
|---|---|---|
| `failure_threshold` | 5 | Failures to trip |
| `success_threshold` | 3 | Successes to recover |
| `timeout_seconds` | 60 | Time before half-open attempt |
| `window_seconds` | 300 | Failure counting window |
| `loss_threshold_pct` | 5% | Daily PnL loss kill switch |

**Key difference from infra/resilience.py**: This circuit breaker is **PnL-aware** — it trips on financial losses, not just technical failures. The infra circuit breaker only tracks call failures.

### OrderService Internals

| Detail | Value |
|---|---|
| Idempotency TTL | 3600s (1 hour) |
| Max cache entries | 10,000 |
| Symbol max chars | 10, alphanumeric + dot only |
| Max qty per order | 1,000,000 |
| Max price | $1,000,000 |
| Per-symbol locks | asyncio.Lock (prevents duplicate orders without cross-symbol blocking) |
| Order modification | Cancel-and-replace pattern (Alpaca doesn't support modification) |
| 429 retry | MAX_RETRIES=3, backoff=2^attempt, multiplicative jitter [0.5, 1.5] |
| Smart TIF | Always 'day' (market hours check is logging only, not TIF selection) |

---

## 35. ALERT SYSTEM

**Source**: `backend/infra/alerting.py`

### Alert Architecture

```
AlertManager (global singleton)
  │
  ├── Channels:
  │   ├── Slack (via webhook): all severities
  │   └── PagerDuty (via routing key): ERROR + CRITICAL always, WARNING in prod only
  │
  ├── Deduplication:
  │   ├── SHA-256 content hash
  │   ├── 300s dedup window
  │   └── Async lock for thread safety
  │
  ├── Rate Limiting:
  │   ├── Sliding window: 30 alerts/min
  │   └── Excess alerts dropped with warning
  │
  └── Market Hours Suppression:
      ├── Extended hours: 4:00 AM - 8:00 PM ET
      └── INFO/WARNING suppressed outside extended hours
      └── ERROR/CRITICAL always delivered
```

### Alert Categories

| Category | Examples |
|---|---|
| RISK_VIOLATION | Drawdown kill, position limit, notional cap |
| ORDER_FAILURE | Broker reject, timeout, DLQ |
| SYSTEM_ERROR | DB down, Redis down, unhandled exception |
| CONNECTIVITY | WebSocket disconnect, API timeout |
| PERFORMANCE | Tick latency, queue overflow |
| SECURITY | Auth failure, rate limit, suspicious activity |

### Convenience Methods

`risk_violation()`, `order_failure()`, `system_error()`, `connectivity_issue()`

---

## 36. DATABASE SCHEMA

**Source**: `backend/infra/schemas.py`, `backend/infra/repositories/`

### Tables (25 ORM tables)

| Table | Key Columns | Purpose |
|---|---|---|
| `users` | id, username (unique), email (unique), hashed_password, roles (ARRAY), failed_login_attempts, locked_until | Auth + RBAC |
| `orders` | id (UUID), user_id, client_idempotency_key (unique), symbol, side, qty, order_type, tif, status, broker_order_id, attributes (JSONB) | Order lifecycle |
| `executions` | id (UUID), order_id (FK), fill_qty, fill_price, ts, venue | Fill records |
| `outbox_events` | id, topic, payload (JSONB), status, attempts, next_attempt_at, last_error | Transactional outbox |
| `model_lifecycle_events` | id, model_id, model_name, model_version, event_type, payload | ML model audit trail |
| `signals` | id, symbol, model_name, signal_type, direction, strength, confidence, target_price, expiry | Trading signals |
| `positions` | id, symbol, qty, avg_cost, market_value, unrealized_pnl, attributes | Position state |
| `audit_logs` | id, action, entity, entity_id, actor, ts | Audit trail |
| `model_registry` | id, name, version, model_type, status, metadata, config, performance_metrics | ML model registry |
| `strategies` | id, name, strategy_type, description, status, symbols, parameters, total_pnl, win_rate | Strategy config |
| `risk_limits` | id (UUID), user_id (FK), limit_name, limit_value, warning_threshold (80%), critical_threshold (95%), enabled | Risk limit definitions |
| `risk_metrics` | id (UUID), user_id (FK), metric_name, current_value, limit_value, percent_used, status (normal/warning/critical/breached) | Live risk measurements |
| `risk_violations` | id (UUID), user_id (FK), metric_name, violation_type, current_value, limit_value, severity, message, resolved | Risk breach records |
| `emergency_stops` | id (UUID), user_id (FK), triggered_by (FK), reason, strategies_stopped, orders_cancelled, status (active/resolved) | Emergency stop events |
| `portfolio_history` | id, user_id (FK), timestamp, total_equity, cash, positions_value, daily_pnl, daily_pnl_percent, snapshot_type | Equity time series |
| `position_lots` | id (UUID), user_id (FK), symbol, qty, remaining_qty, cost_basis, order_id (FK), open_date, status (open/closed) | FIFO tax lot tracking |
| `realized_trades` | id (UUID), user_id (FK), symbol, qty, open_price, close_price, realized_pnl, realized_pnl_percent, lot_id (FK) | Closed trade records |
| `backtests` | id (UUID), strategy_id (FK), user_id, start/end_date, initial_capital, parameters, metrics (JSON), status, equity_curve (JSON) | Backtest results |
| `order_events` | id, order_id (FK), event_type, data (JSONB), ts | Order lifecycle event log |
| `model_monitoring_snapshots` | id, model_id (FK), metrics (JSONB), ts | ML model performance snapshots |
| `watchlists` | id, user_id (FK), name, symbols (ARRAY), created_at | User watchlists |
| `watchlist_symbols` | id, watchlist_id (FK), symbol, added_at | Watchlist symbol membership |
| `chart_templates` | id, user_id (FK), name, config (JSONB), created_at | Saved chart configurations |
| `drawings` | id, user_id (FK), symbol, drawing_type, data (JSONB), created_at | TradingView-style chart drawings |
| `tick_telemetry` | id, tick_number, timestamp (indexed), regime, equity, drawdown_pct, open_positions, entries_blocked_reason, orders_submitted, gate_rejections (JSON), top_candidates (JSON), exit_decisions (JSON) | Persisted per-tick telemetry (~1/min, 7-day retention) |

### Repositories

| Repository | Key Operations |
|---|---|
| `OrdersRepo` | `upsert_by_idempotency()`, `attach_broker_result()`, `get_by_broker_order_id()`, `batch_create_orders()` |
| `PositionsRepo` | `upsert_position()`, `update_market_data()`, `get_portfolio_summary()`, `batch_update_market_data()` |
| `ExecutionsRepo` | `upsert_by_execution_id()`, `get_volume_weighted_avg_price()`, `calculate_pnl_impact()` |
| `SignalsRepo` | `get_high_confidence_signals(min_conf=0.8)`, `get_consensus_signals()`, `expire_signals_by_model()` |
| `ModelsRepo` | `register_model()`, `promote_model_to_production()`, `get_model_performance_comparison()` |
| `AuditsRepo` | `log_order_action()`, `get_security_events()`, `cleanup_old_logs(90 days)` |
| `StrategiesRepo` | Strategy CRUD, lifecycle management, dedup |

### Repository Pattern

All repositories follow async SQLAlchemy pattern with:
- Custom exceptions: `{Entity}NotFoundError`, `Duplicate{Entity}Error`
- IntegrityError handling for concurrent writes
- Decimal precision for financial values
- Composite query support (`and_`/`or_` composition)

**Source**: `backend/infra/repositories.py` (base) + `backend/infra/repositories/{entity}.py`

### ORM Models

**Source**: `backend/infra/schemas.py` (SQLAlchemy tables), `backend/models/*.py` (Pydantic validation)

| Model File | Key Models | Purpose |
|---|---|---|
| `models/backtest.py` | `BacktestRequest`, `EquityPoint`, `Trade` | Backtest I/O validation (capital: 1K-10M, max 5yr) |
| `models/ml_models.py` | `ModelTrainingRequest`, `ModelStatus`, `TrainingStatus` | ML model management (6 model types, 5 statuses) |
| `models/risk.py` | `RiskStatus`, `ViolationType`, `Severity`, `EmergencyStopStatus` | Risk metric enums + request models |
| `models/order_integrity.py` | Order FSM, audit log, idempotency | Order state machine + Prometheus metrics (5 counters) |
| `models/ensemble_model.py` | Ensemble model stubs | LSTM+XGBoost+RF combination with graceful degradation |

### Input Validation

**Source**: `backend/infra/validation.py`

| Validator | Rules |
|---|---|
| `validate_symbol()` | Max 10 chars, letters/numbers/dots/hyphens, case-insensitive |
| `validate_price()` | Positive, max $100M/share, 4 decimal places max |

### User Management

**Source**: `backend/infra/users.py`

```
UserRepository (DB-backed):
  - Brute force protection: 5 failed attempts → 15 min lockout
  - Fields: id, username, email, hashed_password, roles, is_active,
            failed_login_attempts, locked_until, last_login
  - SQLite compatibility for test environments
```

---

## 37. OBSERVABILITY STACK

**Source**: `backend/infra/observability.py`, `backend/infra/metrics.py`, `backend/infra/logging.py`, `backend/infra/observability_contracts.py`

### Prometheus Metrics

```
Namespace: "intraday"

HTTP:
  http_requests_total{method, route, status}
  http_request_duration_seconds{method, route}

Alpaca:
  alpaca_http_latency_seconds{endpoint, method}
  alpaca_http_requests_total{endpoint, method, status}

Outbox:
  outbox_polled_total, outbox_dispatched_total{topic, status}
  outbox_dispatch_latency_seconds{topic}
  outbox_queue_gauge{status}

Broker:
  broker_submit_total{result}
  broker_submit_latency_seconds

Resilience:
  resilience_circuit_breaker_state_changes_total
  resilience_circuit_breaker_requests_total
  resilience_retry_attempts_total
  resilience_timeout_occurrences_total
  resilience_dlq_messages_total
  resilience_backoff_delay_seconds

Organism Engine:
  organism_tick_duration_seconds (Histogram)
  organism_generation (Gauge)
  organism_direction_accuracy (Gauge)
  organism_sharpe (Gauge)
  organism_total_trades (Gauge)
  organism_orders_submitted_total (Counter)
  organism_errors_total (Counter)
  organism_halted_with_positions_total (Counter)
  organism_exits_skipped_no_data_total (Counter)
  organism_sector_cap_blocked_total (Counter)
  organism_safety_net_triggered_total (Counter)
  organism_entries_blocked_total (Counter)

Object Pool:
  object_pool_acquisitions_total{pool_name, source}
  object_pool_releases_total{pool_name}
  object_pool_size{pool_name}
  object_pool_acquisition_seconds{pool_name} (Histogram)

Additional (in LABEL_ALLOWLIST):
  db_health_checks_total{result}, db_query_duration_seconds{operation}
  readyz_db_ms, readyz_broker_ms
  websocket_connections_total{client_type}, websocket_messages_total{message_type, direction}
  auth_attempts_total{result}, auth_token_validations_total{result}
  risk_allows_total, risk_blocks_total{reason}, risk_decision_latency_seconds
  feature_compute_latency_seconds{path}, feature_schema_validations_total{result}
```

Label cardinality is enforced via `LABEL_ALLOWLIST` and `LABEL_VALUE_ALLOWLIST`.

### OpenTelemetry Tracing

- Default sampler: `traceidratio=0.5` (50% of requests traced)
- OTLP export: every 30s to `otel-collector:4317`
- Auto-instrumentation: FastAPI, requests, SQLAlchemy, asyncpg
- `trace_span(name, attributes)` context manager for custom spans

### Structured Logging

```
Format: JSON with fields: timestamp, level, message, service, version, trace_id, span_id
Service: "intraday-trading", version "2.0.0"

Domain methods:
  log_http_request(), log_database_operation(), log_alpaca_request(),
  log_order_event(), log_outbox_event(), log_auth_event()

Noise reduction: uvicorn.access, sqlalchemy.engine, asyncpg → WARNING
```

### Histogram Bucket Definitions

| Metric Type | Buckets (ms) |
|---|---|
| HTTP requests | 1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000 |
| Alpaca latency | 50ms–60s range (timeout-aware) |
| Outbox dispatch | 1ms–250ms range |
| Object pool acquire | 0.01, 0.05, 0.1, 0.5, 1, 5, 10 ms |

---

# LAYER 6: ML DEPLOYMENT PIPELINE

## 38. PROMOTION CONTROLLER

**Source**: `backend/organism/promotion.py`

### 6-Stage State Machine

```
SHADOW → PAPER_EXECUTE → CANARY → RAMP → ACTIVE → (ROLLED_BACK)

Each transition:
  1. Validate minimum stage duration met
  2. Check rollback triggers not firing
  3. Persist as ModelLifecycleEvent
  4. Apply new risk caps
```

### Stage Configuration

| Stage | Risk Cap (Exposure) | Min Duration | Description |
|---|---|---|---|
| SHADOW | 0% | 1 hour | Model runs but no orders placed |
| PAPER_EXECUTE | 20% | 24 hours | Paper trades only |
| CANARY | 5% | 24 hours | Small real allocation |
| RAMP | 15% | 48 hours | Gradual ramp-up |
| ACTIVE | 25% | — | Full production |
| ROLLED_BACK | 0% | — | Emergency stop |

### Rollback Triggers

| Trigger | Threshold | Action |
|---|---|---|
| Max drawdown | 8% | Immediate rollback |
| Max slippage | 50 bps | Immediate rollback |
| Max turnover ratio | 10.0× | Immediate rollback |
| Max regime churn rate | 0.50 | Immediate rollback |

Rollback auto-freezes governance to prevent further parameter changes.

---

## 39. TRAINING ORCHESTRATOR

**Source**: `backend/organism/training.py`

### "Slow Brain" Training Pipeline

```
TRAINING ORCHESTRATOR:
  │
  ├── 1. Attribution: compute per-strategy reward signals from DB fills
  ├── 2. Candidate Weights:
  │       new_w = current_w × (1 + alpha × reward)
  │       normalized, clamped to [0.10, 2.50]
  │       alpha = 0.3
  ├── 3. Walk-forward evaluation: test candidate vs baseline
  ├── 4. IF accepted → register new weights
  └── 5. IF rejected → keep baseline

Regime boost: +0.05 weight for strategies aligned with current regime
Default universe (22 symbols, improve9 B4): AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA, AMD, AVGO, CRM, COST, WMT, LLY, XOM, CAT, SPY, QQQ, IWM, XLK, XLE, SH, PSQ
```

---

## 40. NIGHTLY SCHEDULER

**Source**: `backend/organism/nightly_scheduler.py`

### Configuration

```
ORGANISM_NIGHTLY_ENABLED: 0 (off by default)
ORGANISM_NIGHTLY_INTERVAL_S: 86400 (24 hours)

Backoff on failure:
  _BASE_BACKOFF_S: 60
  _MAX_BACKOFF_S: 3600
  _JITTER_FRACTION: 0.25

Loop: _nightly_loop() → _run_nightly_tick() → full retrain cycle
```

---

## 41. ATTRIBUTION SERVICE

**Source**: `backend/organism/attribution.py`

### Per-Strategy Reward Signals

```
TradeAttribution:
  - Links fills from DB to strategy that generated them
  - Computes PnL per strategy per time window

AttributionSummary:
  - Aggregated metrics for training orchestrator
  - Drives weight updates in §39
```

---

## 42. WALK-FORWARD EVALUATOR

**Source**: `backend/organism/walk_forward.py`

### Sliding Window Evaluation

```
WalkForwardEvaluator:
  │
  ├── Split data into walk-forward windows
  ├── Train on window N, test on window N+1
  ├── Compare candidate vs baseline policy
  │
  └── AcceptanceGates:
      ├── Minimum composite score
      ├── No regression vs baseline
      └── Stable across multiple windows
```

### Brain Save Gate

- Checks last 100 trades (needs >= 10)
- Regression threshold: 0.95
- Rejects brain save if model is regressing

---

# LAYER 7: OPERATIONS

## 43. DOCKER ORCHESTRATION

**Source**: `docker-compose.yml`

### Services

| Service | Image | Port | Health Check |
|---|---|---|---|
| **api** | Custom Dockerfile | 8000:8000 | `curl /healthz` every 30s, 3 retries, 60s start |
| **db** | postgres:16-alpine | 127.0.0.1:5432 | `pg_isready` every 10s |
| **redis** | redis:7-alpine | 127.0.0.1:6379 | `redis-cli ping` every 10s |
| **otel-collector** | otel/opentelemetry-collector-contrib | 4317, 4318, 8889 | Profile: observability |
| **prometheus** | prom/prometheus | 9090 | 200h retention, profile: observability |
| **grafana** | grafana/grafana | 3000 | Profile: observability |

### Database Tuning (PostgreSQL)

```
shared_buffers: 256MB
work_mem: 16MB
effective_cache_size: 768MB
maintenance_work_mem: 128MB
statement_timeout: 30000ms
log_min_duration_statement: 500ms
checkpoint_completion_target: 0.9
idle_in_transaction_session_timeout: 60000ms
```

### Redis Configuration

```
maxmemory: 256mb
eviction: allkeys-lru
persistence: AOF (appendonly yes)
password: requirepass
```

### Network

`trading-network` (bridge, subnet `172.20.0.0/16`). DB and Redis bound to `127.0.0.1` only.

---

## 44. ENGINE STARTUP SEQUENCE

**Source**: `backend/api/lifespan.py`

### Boot Order

```
APPLICATION STARTUP (lifespan context manager):
  │
  ├──  1. Observability (OTel + Prometheus) — non-critical
  ├──  2. SLO metrics collector — non-critical
  ├──  3. Database init + pool pre-warming (5 connections)
  ├──  4. Outbox worker start (if DB available, not reload mode)
  ├──  5. Living strategy policy (LIVING_STRATEGY_ENABLED=true, opt-out)
  ├──  6. Living organism (ORGANISM_ENABLED=0, opt-in)
  ├──  7. Multi-strategy runner (MULTI_STRATEGY_LIVE_ENABLED=0, opt-in)
  │       └── Skipped if organism active (mutually exclusive)
  ├──  8. Auto breakout scanner (AUTO_BREAKOUT_SCAN_ENABLED=0, opt-in)
  ├──  9. ML lifecycle scheduler (ENABLE_ML_LIFECYCLE_SCHEDULER=0, opt-in)
  ├── 10. Organism scheduler (ENABLE_ORGANISM_SCHEDULER=0, opt-in)
  │       └── Also cancels stale open Alpaca orders before start
  ├── 11. Alpaca WebSocket stream (real broker only)
  ├── 12. Reconciliation scheduler (15-min default)
  ├── 13. Portfolio sync
  └── 14. Order sync from Alpaca (500 most recent)

SHUTDOWN: Reverse order with individual error handling
```

### Middleware Stack (installed order)

```
1. CORS (CORSMiddleware) — credentials, 14 local origins (localhost + 127.0.0.1, ports 3000/3001/5173/5174)
2. GZip (minimum 500 bytes)
3. Request deduplication (TTL=300s, max_cache=10000)
4. Rate limiting (exempt: health/metrics/docs)
5. HTTP metrics (counter + histogram)
NOTE: SecurityHeadersMiddleware class exists in infra/security_hardening.py but is NOT installed in the middleware chain.
```

---

## 45. STREAMING DATA PROVIDER

**Source**: `backend/organism/streaming_data_provider.py`

### Ring Buffer Architecture

```
StreamingDataProvider:
  │
  ├── Manages Alpaca WebSocket bar stream
  ├── Ring buffer per symbol (size: 2000 entries ≈ 33 hours of 1-min bars)
  ├── Prefill from REST on subscribe (ORGANISM_LIVE_LOOKBACK=100, ORGANISM_LIVE_TIMEFRAME)
  │
  ├── On new bar:
  │   ├── Append to ring buffer
  │   ├── Update _last_bar_ts[symbol] = time.time()
  │   ├── Update last_update_time = time.time()  (global, used by engine stale gate)
  │   └── Available immediately for next tick
  │
  ├── Quote data stored per symbol:
  │   └── bid, ask, bid_size, ask_size, mid, spread, timestamp
  │
  ├── Stale detection (threshold: 300 seconds / 5 minutes):
  │   ├── check_and_recover_stale_stream() every 30 ticks
  │   └── Only triggers when ALL tracked symbols are stale (prevents false positives)
  │   └── Recovery: cleanup_connection() + connect() for forced reconnect
  │
  ├── Dynamic subscription:
  │   └── update_subscriptions() for universe rotation (add/remove symbols)
  │
  └── Reconnect:
      └── Re-subscribe all symbols on WebSocket reconnect
```

---

## 46. DIAGNOSTIC SYSTEM

**Source**: `backend/organism/diagnostics.py`, `backend/organism/diagnostic_checks.py`, `backend/organism/diagnostic_scheduler.py`

### 36 Diagnostic Checks Across 8 Categories

```
DiagnosticEngine:
  │
  ├── WIRING: component connectivity, dependency injection, signal flow
  ├── STATE_PERSISTENCE: brain save/load, exit levels, evolved params integrity
  ├── ORDER_FLOW: stuck orders, zombie orders, DLQ depth, outbox health
  ├── DATA_PIPELINE: bar freshness, NaN rates, feature completeness
  ├── STREAMING: WebSocket health, staleness, reconnection status
  ├── GOVERNANCE: drawdown proximity, halt state, change budget
  ├── BROKER_SYNC: broker vs DB sync, orphaned positions, fill reconciliation
  └── INFRASTRUCTURE: Redis, DB, tick latency, memory usage
```

### Entry Points

- `run_preflight_check()` — pre-market comprehensive check
- `run_continuous_check()` — lightweight check during trading
- `run_diagnostics()` — full 36-check suite

### Scheduled Runs

```
DiagnosticReportStore:
  - Ring buffer: 50 reports max
  - Persisted to: organism_brain/diagnostics/history.json

ScheduledDiagnosticRunner:
  - Pre-open: 9:25 AM ET
  - Post-close: 4:05 PM ET
  - Skips weekends and holidays
  - Date-idempotent (won't re-run same day/trigger)

Alert Rules:
  Pre-open critical  → CRITICAL (Slack + PagerDuty, bypasses market hours)
  Pre-open warnings  → WARNING (Slack)
  Pre-open all-pass  → INFO "Engine ready" (Slack)
  Post-close critical → CRITICAL
  Post-close warnings → WARNING
  Post-close all-pass → no alert (noise reduction)
```

---

## 47. API SURFACE & SECURITY

**Source**: `backend/organism/routes.py`, `backend/api/routes_setup.py`, `backend/infra/security.py`, `backend/infra/security_hardening.py`

### API Routes (210+ endpoints across 28 route files)

**Organism Engine** (prefix `/api/v1/organism`):
- `GET /status` — engine state, regime, positions
- `GET /attribution` — per-strategy attribution
- `GET /analytics` — performance analytics
- `GET /brain` — brain state summary
- `GET /universe` — current symbol universe
- `GET /scanner` — market scanner results
- `GET /decisions` — latest tick decisions
- `GET /decisions/history` — decision history buffer
- `GET /decisions/symbol/{sym}` — per-symbol decisions
- `GET /decisions/exits` — exit decisions
- `GET /evolution/history` — evolution timeline
- `GET /diagnostics` — latest diagnostic report
- `GET /diagnostics/history` — diagnostic history
- `POST /tick` — manual tick trigger
- `POST /train` — manual retrain
- `POST /freeze` / `POST /unfreeze` — adaptation control
- `POST /halt` / `POST /resume` — trading control
- `POST /promote` / `POST /rollback` — model promotion
- `POST /close-shorts` — emergency legacy-short cover; dry-run by default,
  live cover requires `dry_run=false&confirm=CLOSE_SHORTS`
- `POST /cleanup-orders` — expire stuck orders
- `POST /diagnostics/run` — manual diagnostic run
- `POST /compute-attribution` — manual attribution
- `GET /policy` — current living policy snapshot
- `GET /runs` — recent organism run history
- `GET /scanner/history` — raw scanned stock details
- `GET /orders` — organism-submitted orders

**Core Platform** (prefix `/api/v1`): See [Appendix F](#f-full-api-route-reference) for complete endpoint listing.

| Route File | Endpoints | Domain |
|---|---|---|
| `auth.py` | 11 | Login, register, token refresh, password reset, /me |
| `orders.py` | 10 | Place, list, cancel, bulk, audit, close-position |
| `risk.py` | 10 | Dashboard, metrics, limits, violations, emergency stop |
| `scanner.py` | 10 | Scan, presets (CRUD), export (CSV/JSON), WebSocket |
| `strategy.py` | 16 | CRUD, start/stop/pause, performance, signals, templates |
| `models.py` | 21 | ML model registry, train, predict, lifecycle, health |
| `watchlists.py` | 9 | CRUD, symbols, reorder, quotes |
| `observability.py` | 8 | Health probes (live/ready), metrics, dashboard, alerts |
| `system.py` | 8 | Status, metrics, health, SLI |
| `settings.py` | 7 | Organism/trading/ML settings CRUD, engine restart |
| `audit.py` | 6 | Compliance audit trail queries |
| `chart_templates.py` | 6 | Chart template CRUD, apply |
| `drawings.py` | 5 | TradingView-style drawings CRUD |
| `signals.py` | 5 | Signal storage, retrieval, act |
| `backtest.py` | 5 | Create, list, results, delete |
| `positions.py` | 4 | List, import preview, import, close |
| `market_data.py` | 4 | Stats, health, bars, WebSocket |
| `lots.py` | 4 | Open lots, realized trades, cost basis, unrealized PnL |
| `trades.py` | 3 | Trade history retrieval |
| `admin_trading.py` | 3 | Execution mode GET/PUT/DELETE |
| `position_import.py` | 3 | Preview, import, clear |
| `optimizations.py` | 3 | Strategy optimization runs |
| `indicators.py` | 2 | Calculate, list available |
| `auto_breakout_scanner.py` | 2 | Latest scan, manual trigger |
| `monitoring.py` | 2 | SLI metrics, SLO status |
| `multi_strategy_live.py` | 1 | Manual run-once trigger |

### Per-Endpoint Rate Limiting

**Source**: `backend/api/middleware/rate_limit.py`

Sliding window algorithm with sub-second precision. Key format: `user:{id}:{path}` or `ip:{client_ip}:{path}`.

| Endpoint Pattern | Requests/Min | Burst | Purpose |
|---|---|---|---|
| `/api/v1/auth/login` | 5 | 3 | Brute-force protection |
| `/api/v1/auth/token` | 5 | 3 | Token auth throttle |
| `/api/v1/auth/register` | 3 | 2 | Account creation throttle |
| `/api/v1/auth/password-reset` | 3 | 2 | Reset abuse prevention |
| `/api/v1/orders` | 30 | 5 | Order submission throttle |
| `/api/v1/portfolio` | 120 | 10 | Portfolio reads |
| `/api/v1/positions` | 120 | 10 | Position reads |
| `/api/v1/trades` | 60 | 10 | Trade history |
| `/api/v1/models` | 30 | 5 | ML model operations |
| `/api/v1/strategies` | 60 | 10 | Strategy management |
| `/api/v1/health` | 300 | 50 | Health probes (monitoring) |
| `/api/v1/system` | 120 | 20 | System status |
| **Default** | 60 | 15 | All other endpoints |

Response headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`. Returns `429 + Retry-After` on limit breach. Exempt: `/health`, `/metrics`, `/docs`, `/openapi.json`.

### Request Deduplication

**Source**: `backend/api/middleware/deduplication.py`

Prevents duplicate POST/PUT/PATCH requests (double-submit protection).

```
REQUEST DEDUPLICATION:
  │
  ├── Applies to: POST, PUT, PATCH methods
  │
  ├── Key Generation:
  │   ├── Explicit: X-Idempotency-Key header → user_id:{key}
  │   └── Automatic (strict paths only): SHA-256(body)[:16]
  │       └── Strict paths: /api/v1/orders, /api/v1/trades
  │
  ├── Cache:
  │   ├── TTL: 300 seconds (5 minutes)
  │   ├── Max entries: 10,000 (LRU eviction)
  │   ├── ~1KB per entry
  │   └── Only caches 2xx responses
  │
  └── On cache hit:
      └── Return cached response + X-Idempotency-Status: cached
```

### Security Stack

```
JWT Authentication:
  Algorithm: HS256
  Issuer: "algotrading-platform"
  Audience: "algotrading-api"
  Clock skew: 60s
  Refresh tokens: 7 day expiry
  Blacklist: dual Redis + in-memory (fail-CLOSED)

Password:
  bcrypt hashing, rejects > 72 bytes
  Brute-force protection: 5 attempts → 15 min lockout

Rate Limiting:
  60 req/min per IP (burst: 10)
  10 orders/sec per user
  Exempt: /health, /healthz, /readyz, /metrics

Security Headers:
  HSTS: max-age=31536000
  X-Frame-Options: DENY
  X-Content-Type-Options: nosniff
  CSP: default-src 'self'
  Referrer-Policy: strict-origin-when-cross-origin
  CORS: no wildcard in production

RBAC Roles:
  require_admin — admin-only endpoints
  require_trader — trading endpoints
  require_api — API access
```

---

## 48. BRAIN PERSISTENCE & CACHING

### Brain Persistence

**Source**: `backend/organism/brain_persistence.py`

```
Storage: organism_brain/ (gitignored)
Format: JSON + CSV files

Save contents:
  ├── ML models (classifier + regressor, HMAC-signed via secure_pickle)
  ├── Learning state (learning_state.json) + trade history (CSV) + equity curve (CSV)
  ├── Evolved params (evolved_params.json) + governance state (governance_state.json)
  ├── Regime detector state (regime_state.json)
  ├── extra_counters.json (single file containing):
  │   ├── Exit levels + entry metadata (incl. v3 fields: last_bar_time, prediction_horizon)
  │   ├── Kelly regime-stratified stats
  │   ├── Universe selector state
  │   ├── ML calibration data
  │   ├── tick_count, bars_since_retrain, entry_timestamps
  │   └── NOTE: transfer_learning is separate (transfer_knowledge.json, NOT in brain save)
  └── Manifest (manifest.json): format version, generation, trade count, best Sharpe

Save frequency: every 20 ticks (~3.3 min) + event-driven (after fill reconciliation)
Gate: walk-forward check must pass (regression threshold 0.95)
  └── If gate rejects: best_sharpe decayed by 5% to prevent permanent blocking
Startup: reconstruct trades from DB if brain has no records
Format migration: auto-migrates v1 → v2; hard error if brain is from newer version
Trade history: archived to gzipped CSV when > MAX_TRADE_ROWS (10,000), max 10 archives

Brain Validation Gates (5 integrity checks on load):
  1. NaN/Inf check in evolved_params
  2. Alpha weight normalization (sum ≈ 1.0, tolerance 0.05)
  3. Breakout weight normalization check
  4. ML model sanity (predict_proba test on zeros)
  5. Feature schema drift detection (added/removed features)
```

### Caching Architecture

**Source**: `backend/infra/cache.py`, `backend/infra/performance.py`

```
HOT DATA CACHE (global singleton):
  max_size: 5000 entries
  default_ttl: 30s
  cleanup_interval: 60s

PRE-CONFIGURED CACHES:
  quote_cache:     1000 entries, 1s TTL (HFT-grade freshness)
  position_cache:  500 entries,  5s TTL
  order_cache:     2000 entries, 30s TTL
  indicator_cache: 10000 entries, 60s TTL

OBJECT POOL (order objects):
  initial: 20, max: 200
  Purpose: reduce GC pressure in hot order paths
  Prometheus-instrumented
```

---

# LAYER 8: PLATFORM SERVICES & ARCHITECTURE

## 49. DUAL-PATH ENGINE ARCHITECTURE

**Source**: `backend/organism/runner.py`, `backend/organism/scheduler.py`, `backend/api/lifespan.py`

The platform has **two mutually exclusive** engine paths. Only one runs at a time, controlled by environment flags.

```
ENGINE PATH SELECTION (lifespan.py startup):
  │
  ├── PATH A: OrganismScheduler
  │   ├── Flag: ENABLE_ORGANISM_SCHEDULER=1
  │   ├── Creates: OrganismLiveEngine (full pipeline)
  │   ├── Tick interval: ORGANISM_TICK_INTERVAL_SECONDS (default 60s, prod 10s)
  │   ├── Market hours: 9:28 AM – 4:01 PM ET (strict)
  │   ├── Signal generation: Single unified pipeline
  │   │   └── ML → Alpha Scan → Breakout → Kelly → Exits → Evolution
  │   ├── Order routing: LiveEngine → OrderService → Outbox → Broker
  │   └── Includes: Diagnostic scheduler (pre-open/post-close)
  │
  ├── PATH B: MultiStrategyLiveScheduler
  │   ├── Flag: MULTI_STRATEGY_LIVE_ENABLED=1
  │   ├── Creates: MultiStrategyLiveRunner (10 strategies)
  │   ├── Tick interval: MULTI_STRATEGY_LIVE_INTERVAL_SECONDS (default 300s)
  │   ├── Signal generation: 10 independent strategies in parallel
  │   ├── Order routing: Runner → StrategyEngine → OrderService → Outbox → Broker
  │   └── Integrates: OrganismRunner governance hooks (if ORGANISM_ENABLED=1)
  │
  └── MUTUAL EXCLUSION:
      └── If ENABLE_ORGANISM_SCHEDULER=1, MultiStrategyLiveScheduler is SKIPPED
          (explicit check in lifespan.py step 7)
```

### OrganismRunner (Governance Layer)

**Source**: `backend/organism/runner.py`

**Not an engine** — a governance wrapper used by the multi-strategy path.

```
OrganismRunner (activated by ORGANISM_ENABLED=1):
  │
  ├── Manages 4 subsystems:
  │   ├── GovernanceController — halt/resume, drawdown kill
  │   ├── RegimeDetector — 7-label regime classification
  │   ├── RegimeConditionedEnsemble — regime-aware weight blending
  │   └── DriftDetector — periodic feature drift (PSI, default 3600s)
  │
  ├── pre_execution_hook() — called BEFORE strategy tick:
  │   ├── Check governance halts
  │   ├── Detect regime, blend strategy weights
  │   ├── Run periodic drift checks
  │   └── Returns: {final_weights, regime, trading_allowed, drift}
  │
  └── post_execution_hook() — called AFTER strategy tick:
      ├── Monitor drawdown vs limit
      ├── Trigger kill switch if breached
      └── Returns: list of triggered actions
```

### OrganismScheduler (Full Engine)

**Source**: `backend/organism/scheduler.py`

```
OrganismScheduler:
  │
  ├── Creates OrganismLiveEngine with injected dependencies:
  │   ├── data_client (Alpaca)
  │   ├── order_service (OrderService)
  │   ├── positions_service (PositionsService)
  │   └── brain_dir, universe, use_streaming
  │
  ├── _run_loop():
  │   ├── Run scheduled diagnostics (regardless of market hours)
  │   ├── Check market hours (9:28 AM – 4:01 PM ET)
  │   ├── Call engine.live_tick() with 60s timeout
  │   ├── Broadcast result via WebSocket + Socket.IO
  │   └── Exponential backoff on errors (2s → 30s)
  │
  └── Market hours: skips weekends + US market holidays (2026 calendar)
```

### Comparison Table

| Feature | OrganismScheduler (Path A) | MultiStrategyLive (Path B) |
|---|---|---|
| **Flag** | `ENABLE_ORGANISM_SCHEDULER=1` | `MULTI_STRATEGY_LIVE_ENABLED=1` |
| **Tick interval** | 10-60s | 300s |
| **Signal source** | Single unified ML pipeline | 10 independent strategies |
| **Universe** | 22 symbols (ORGANISM_LIVE_SYMBOLS, +SH/PSQ B4) | Dynamic (base + breakout candidates) |
| **Market hours** | Strict 9:28 AM – 4:01 PM ET | Not explicitly enforced |
| **Governance** | Built-in (GovernanceController) | Via OrganismRunner hooks |
| **Diagnostics** | Integrated scheduler | Not included |
| **Brain persistence** | Every 20 ticks | Not applicable |
| **ML retraining** | Automatic (RETRAIN_INTERVAL) | Not applicable |

---

## 50. MULTI-STRATEGY LIVE SYSTEM

**Source**: `backend/services/multi_strategy_live_runner.py`, `backend/services/multi_strategy_live_scheduler.py`

### 10 Independent Strategies

| # | Key | Class | Style |
|---|---|---|---|
| 1 | `momentum` | MomentumStrategy | Trend following |
| 2 | `mean_reversion` | MeanReversionStrategy | Statistical mean reversion |
| 3 | `stat_arb` | StatisticalArbitrageStrategy | Pairs/statistical arbitrage |
| 4 | `regime_momentum` | RegimeFilteredMomentumStrategy | Regime-conditioned momentum |
| 5 | `breakout` | BreakoutStrategy | Range breakout detection |
| 6 | `adaptive_regime` | AdaptiveRegimeMomentumStrategy | Adaptive regime-aware momentum |
| 7 | `order_flow` | OrderFlowImbalanceStrategy | Order flow imbalance |
| 8 | `vol_structure` | VolatilityStructureStrategy | Volatility term structure |
| 9 | `cross_momentum` | CrossSectionalMomentumStrategy | Cross-sectional momentum |
| 10 | `microstructure` | MicrostructureAlphaStrategy | Microstructure alpha |

### Execution Pipeline

```
MultiStrategyLiveRunner.run_once():
  │
  ├── Fetch price_df for each symbol (parallel, semaphore-limited)
  │   ├── Validate freshness: reject bars > 3 days stale
  │   └── Filter illiquid: min 50K avg daily volume
  │
  ├── Compute features (realtime_light mode)
  │
  ├── For each strategy (independent, exception-isolated):
  │   ├── strategy.generate_signal(features)
  │   └── Failure in one strategy does NOT block others
  │
  ├── Record signal directions (30-bar rolling correlation)
  │   └── Log warning if two strategies > 80% correlated
  │
  └── Route all signals → OrderService.plan_and_submit()
```

### Scheduler Coordination

```
MultiStrategyLiveScheduler (background asyncio task):
  │
  ├── Interval: MULTI_STRATEGY_LIVE_INTERVAL_SECONDS (default 300s)
  ├── Lookback: MULTI_STRATEGY_LIVE_LOOKBACK (default 200 bars)
  │
  ├── Dynamic universe construction:
  │   ├── Base symbols (MULTI_STRATEGY_LIVE_SYMBOLS)
  │   └── + Breakout candidates (score >= 55, limit 20)
  │       └── LIVING_STRATEGY_MAX_TOTAL_POSITIONS: 40
  │
  ├── Pre-execution: organism_runner.pre_execution_hook()
  │   ├── Get regime-conditioned weights
  │   └── Check trading_allowed (governance gate)
  │
  ├── Execute: MultiStrategyLiveRunner.run_once()
  │
  └── Post-execution: organism_runner.post_execution_hook()
      └── Drawdown kill-switch monitoring
```

### Configuration

| Variable | Default | Purpose |
|---|---|---|
| `MULTI_STRATEGY_LIVE_ENABLED` | 0 | Enable multi-strategy path |
| `MULTI_STRATEGY_LIVE_INTERVAL_SECONDS` | 300 | Tick interval (5 min) |
| `MULTI_STRATEGY_LIVE_LOOKBACK` | 200 | Historical bars to fetch |
| `MULTI_STRATEGY_LIVE_TIMEFRAME` | 1Day | Bar timeframe |
| `LIVING_STRATEGY_INCLUDE_BREAKOUT_CANDIDATES` | 1 | Extend universe with breakouts |
| `LIVING_STRATEGY_BREAKOUT_CANDIDATES_LIMIT` | 20 | Max breakout candidates |
| `LIVING_STRATEGY_BREAKOUT_MIN_SCORE` | 55.0 | Min breakout score for inclusion |
| `LIVING_STRATEGY_MAX_TOTAL_POSITIONS` | 40 | Total position limit |

---

## 51. SERVICES LAYER

**Source**: `backend/services/` (27 modules)

### Service Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      SERVICES LAYER                          │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ OrderService  │  │ RiskManager  │  │ AuditService     │  │
│  │ (orders,     │  │ (metrics,    │  │ (SEC 17a-4,      │  │
│  │  outbox, CB) │  │  limits,     │  │  hash chain,     │  │
│  └──────┬───────┘  │  emergency)  │  │  compliance)     │  │
│         │          └──────────────┘  └──────────────────┘  │
│         ▼                                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ LotTracker   │  │ SlippageModel│  │ InstitutionalAn. │  │
│  │ (FIFO lots,  │  │ (Almgren-    │  │ (Sharpe, Sortino │  │
│  │  cost basis, │  │  Chriss,     │  │  Calmar, profit  │  │
│  │  tax lots)   │  │  time-of-day)│  │  factor, streaks)│  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ CacheService │  │ StrategyServ.│  │ BreakoutScanner  │  │
│  │ (3-layer     │  │ (CRUD, ver-  │  │ (auto, $5-2K,    │  │
│  │  Redis+mem)  │  │  sioning,    │  │  20-bar lookback, │  │
│  │              │  │  rollback)   │  │  0-100 score)    │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Key Services

**OrderService** (`order_service.py`):
- Creates orders in DB + enqueues outbox events atomically
- Redis-backed circuit breaker (5% daily PnL kill, see §34)
- Idempotency via `client_idempotency_key`

**ComplianceAuditService** (`audit_service.py`):
- SEC 17a-4 compliance audit trail
- SHA-256 hash chain: each record includes hash of previous (tamper detection)
- 24 action types across 8 entity categories (ORDER, POSITION, STRATEGY, MODEL, USER, RISK, CONFIG, SYSTEM)
- `verify_chain_integrity()` — validates entire hash chain
- `export_for_compliance()` — SEC/FINRA export format

**LotTracker** (`lot_tracker_service.py`):
- FIFO lot matching for accurate cost basis
- `create_lot()` on buy → `close_lots_fifo()` on sell
- Supports partial lot closes
- RealizedTrade records with `realized_pnl_percent` for tax reporting
- Tax-loss harvesting support (wash-sale detection via realized trades)

**InstitutionalAnalytics** (`trade_analytics_service.py`):
- Sharpe, Sortino, Calmar ratios (annualized, √252)
- Max drawdown (%, $, duration)
- Profit factor, expectancy, recovery factor
- Win/loss streak analysis
- Monthly return breakdown
- R-multiple distribution

**SlippageModel** (`slippage_model.py`):
- Total slippage = (base + market_impact + spread_cost + volatility_cost + timing) × condition_mult × urgency_mult
- Almgren-Chriss market impact: `α × σ × √(Q/V)` (α=0.1, exponent=0.5)
- Defaults: DEFAULT_ADV=1,000,000 shares, DEFAULT_SPREAD_BPS=5.0, DEFAULT_VOLATILITY=0.20, base_slippage_bps=1.0, spread_crossing_pct=0.5
- Volatility cost: `volatility × 100 × 0.1` (10% of daily vol as uncertainty premium)
- Time-of-day adjustments: pre-market 2.0×, open_auction 1.5×, morning 0.9×, midday 1.0×, afternoon 0.95×, close_auction 1.3×, after-hours 2.5×
- Market condition multipliers: normal 1.0×, high_vol 1.5×, low_liquidity 2.0×, stress 3.0×
- Order urgency: passive 0.5×, normal 1.0×, aggressive 1.5×, urgent 2.5×
- Self-calibrating: `record_actual_slippage()` tracks last 1000 observations
- Confidence interval: `low = total × 0.5`, `high = total × (1 + √participation + volatility)`

**CacheService** (`cache.py`):
- 3-layer Redis cache: L1 quotes (5s), L2 bars (60s), L3 indicators (30s)
- High availability: standalone, Sentinel (auto-failover), Cluster (horizontal scaling)
- In-memory fallback when Redis unavailable
- Connection pool: 50 max, 1s socket timeout

**StrategyService** (`strategy_service.py`):
- Strategy lifecycle: inactive → active → paused → inactive (or error)
- Version snapshots with compare and rollback
- WebSocket broadcasts on state changes

**AutoBreakoutScanner** (`auto_breakout_scanner.py`):
- Scores 0-100: base 50 + breakout strength (+35) + volume expansion (+25) + type bonus
- Types: standard, atr_expansion (+8 bonus), volume_climax (-5 penalty)
- Filters: price $5-2K, volume spike ≥1.5×, data completeness
- Persists `_latest_scan` for living scheduler integration

**TechnicalIndicators** (`indicators.py`):
- 25+ indicators: SMA, EMA, MACD, RSI, Stochastic, ADX, ATR, Bollinger, Keltner, OBV, MFI, VWAP, Ichimoku, Parabolic SAR, etc.
- Squeeze detection (BB inside KC)
- Pivot points: standard, fibonacci, woodie, camarilla

**Additional Services**:
- `PositionsService` — wraps Alpaca position API, portfolio value, buying power
- `PositionImportService` — imports pre-existing Alpaca positions with dedup (skips if filled buy orders exist)
- `SignalService` — signal cache/relay layer (real generation in MultiStrategyLiveRunner)
- `TradeService` — trade history, CSV export, institutional analytics integration
- `SymbolValidator` — validates against Alpaca `/v2/assets/{symbol}` (tradable + active), fail-open on API errors
- `QuoteManager` — Redis-cached real-time quotes (5s TTL)
- `PortfolioService` — portfolio aggregation
- `PortfolioSyncService` — Alpaca → DB position sync on startup
- `PositionReconciliationService` — DB vs broker discrepancy detection
- `ScheduledReconciliation` — 15-min reconciliation scheduler
- `ObservabilityService` — aggregated health checks
- `MarketDataService` — Alpaca market data wrapper
- `BacktestService` — strategy backtesting engine

---

## 52. DUAL WEBSOCKET STACKS

**Source**: `backend/api/socketio_server.py`, `backend/api/websocket_manager.py`

The platform runs **two separate** real-time communication systems in parallel.

```
┌───────────────────────────────────────────────────────────────┐
│                   DUAL WEBSOCKET ARCHITECTURE                  │
│                                                                │
│  ┌─────────────────────────────┐  ┌─────────────────────────┐ │
│  │  SOCKET.IO (ASGI mount)     │  │  NATIVE FASTAPI WS      │ │
│  │  Port 8000 (shared)         │  │  Port 8000 (shared)      │ │
│  │                             │  │                           │ │
│  │  Purpose:                   │  │  Purpose:                 │ │
│  │  - Order status updates     │  │  - Market data stream     │ │
│  │  - Portfolio updates        │  │  - Scanner WebSocket      │ │
│  │  - Strategy state changes   │  │  - Client management      │ │
│  │  - Settings broadcasts      │  │                           │ │
│  │                             │  │  Backpressure:            │ │
│  │  Auth: JWT in auth.token    │  │  - Queue per client (100) │ │
│  │  Ping: 25s interval/20s TO  │  │  - Drop oldest on full   │ │
│  │  Rooms: topic-based (O(1))  │  │  - Heartbeat: 30s        │ │
│  │  Session: async sio.session │  │  - Stale timeout: 60s    │ │
│  └─────────────────────────────┘  └─────────────────────────┘ │
└───────────────────────────────────────────────────────────────┘
```

### Socket.IO Server

7 broadcast functions:

| Function | Purpose | Target |
|---|---|---|
| `broadcast_to_topic(topic, event, data)` | Room-based broadcast | All subscribers in topic room |
| `broadcast_to_user(user_id, event, data)` | Per-user delivery | All sessions of a user |
| `broadcast_to_all(event, data)` | Global broadcast | All connected clients |
| `broadcast_portfolio_update(user_id, data)` | Portfolio state change | Specific user |
| `broadcast_order_update(user_id, data)` | Order fill/status | Specific user |
| `broadcast_strategy_update(topic, data)` | Strategy state change | Topic subscribers |
| `broadcast_settings_update(data)` | Settings broadcast | All clients |

Events: `connect`, `disconnect`, `subscribe`, `unsubscribe`, `heartbeat`, `connected`.

4 callers of `broadcast_order_update`: lifespan startup, alpaca_stream, alpaca_stream_production, orders route.

### WebSocket Manager

- Per-client bounded queue: `asyncio.Queue(maxsize=100)` + internal unbounded send queue
- Backpressure: drop oldest message on full, increment `ws_messages_dropped_total` counter
- Heartbeat: `websocket.ping()` per client, auto-remove stale connections after timeout
- Prometheus: `websocket_connections_total`, `websocket_messages_total`, `ws_messages_dropped_total`

---

## 53. TRADING EXECUTION MODE

**Source**: `backend/services/trading_execution_mode.py`

Controls how orders flow through the outbox worker to the broker.

```
EXECUTION MODE ROUTING (outbox_worker._process_order_submitted):
  │
  ├── "execute" (real mode):
  │   └── Orders sent to Alpaca broker (real or paper API)
  │
  ├── "shadow" (intent-only):
  │   └── Records intent in DB, skips broker entirely
  │       └── Used for monitoring model performance without risk
  │
  ├── "dry_run" (simulated):
  │   └── Simulates broker response (_simulate_broker_order)
  │       └── Returns fake fill at current price
  │
  └── Additional: USE_MOCK_BROKER=true
      └── Uses mock broker client (testing)
```

### Mode Management

```
TradingExecutionModeState:
  │
  ├── mode: "execute" | "shadow" | "dry_run"
  ├── source: "override" | "env"
  │
  ├── Override (runtime, thread-safe):
  │   ├── set_trading_execution_mode_override(mode, actor="admin")
  │   └── clear_trading_execution_mode_override(actor="admin")
  │
  └── Default: from environment or "execute"
      └── Aliases: "paper" → "execute", "live" → "execute"
```

Admin API: `GET/PUT/DELETE /api/v1/admin/execution-mode`

---

## 54. REDIS ARCHITECTURE

**Source**: Multiple files across backend

Redis serves **6 distinct roles** in the platform:

```
REDIS USAGE MAP:
  │
  ├── 1. TOKEN BLACKLIST (infra/security.py)
  │   ├── Keys: token:blacklist:{jti}
  │   ├── TTL: 7 days
  │   ├── Fail-CLOSED: denies access if Redis unavailable and token not in memory
  │   └── In-memory fallback: 10K max entries
  │
  ├── 2. MULTI-LAYER CACHE (services/cache.py)
  │   ├── L1: quote:* (5s TTL) — hot quote data
  │   ├── L2: bars:* (60s TTL) — historical bar data
  │   ├── L3: indicators:* (30s TTL) — indicator calculations
  │   ├── HA modes: standalone / Sentinel / Cluster
  │   └── Serialization: pickle (ephemeral data)
  │
  ├── 3. QUOTE CACHE (services/quote_manager.py)
  │   ├── 5s TTL per symbol
  │   ├── Connection pool: 50 max
  │   └── In-memory fallback if unavailable
  │
  ├── 4. CIRCUIT BREAKER STATE (services/order_service.py)
  │   ├── Keys: circuit_breaker:order_flow:*
  │   ├── State, failures, opened_at, daily_pnl, last_reset_date
  │   └── Pipelined load on startup
  │
  ├── 5. SOCKET.IO SESSION (api/socketio_server.py)
  │   └── Client auth/roles storage via sio.session(sid)
  │
  └── 6. DIAGNOSTIC STATE (organism/diagnostic_checks.py)
      └── Diagnostic caching
```

### Redis Configuration

| Setting | Value | Source |
|---|---|---|
| Host | `redis` (Docker) or `localhost` | `REDIS_HOST` |
| Port | 6379 | `REDIS_PORT` |
| Password | required | `REDIS_PASSWORD` |
| Max memory | 256MB | Docker config |
| Eviction | allkeys-lru | Docker config |
| Persistence | AOF (appendonly) | Docker config |
| Connection pool | 50 max | cache.py |
| Socket timeout | 1.0s | cache.py |
| HA mode | standalone / sentinel / cluster | `REDIS_MODE` |

### Failover Strategy

- **Cache layers**: Graceful degradation to in-memory dict
- **Token blacklist**: Fail-CLOSED (denies access if Redis down and token not in memory)
- **Circuit breaker**: Fall back to in-memory state
- **Quotes**: In-memory fallback with same TTL

---

## 55. RISK MANAGEMENT SYSTEM

**Source**: `backend/services/risk_manager.py`

### Three Risk Manager Classes

The platform has **three separate** RiskManager implementations:

```
RISK MANAGEMENT:
  │
  ├── 1. Platform RiskManager (services/risk_manager.py)
  │   ├── DB-backed (RiskLimit, RiskMetric, RiskViolation tables)
  │   ├── Metrics: daily_loss, max_drawdown, position_count,
  │   │           total_exposure, order_count_daily, buying_power_used
  │   ├── Dashboard: GET /api/v1/risk/dashboard
  │   ├── Limits: configurable per-user with warning/critical thresholds
  │   ├── Violations: recorded with severity (low/medium/high/critical)
  │   └── Emergency stop:
  │       ├── POST /api/v1/risk/emergency-stop
  │       ├── Stops all strategies, cancels open orders
  │       └── Records strategies_stopped + orders_cancelled
  │
  ├── 2. AsyncRiskManager (risk/risk_manager.py)
  │   ├── Async-first, institutional-grade risk controls
  │   ├── Risk profiles: strict / staging / relaxed (from base_settings.py)
  │   │   ├── max_symbol_exposure: 15% (strict), 60% (staging), 90% (relaxed)
  │   │   └── circuit_breaker_pct: 5% (strict), 20% (staging), 50% (relaxed)
  │   ├── VaR (5% confidence, z-score approximation: 1%=-2.33, 5%=-1.645, 10%=-1.28)
  │   ├── CVaR / Expected Shortfall (requires 10+ samples)
  │   ├── Kelly fraction sizing (ceiling=0.20, floor=0.0)
  │   ├── EWMA volatility (lambda=0.94, annualized by √252)
  │   ├── Concentration limits: 15% per symbol, 30% per sector
  │   ├── Daily loss limit: $5,000 default
  │   ├── Drawdown limit: 10% default
  │   ├── Position limit: 50% of portfolio
  │   └── Portfolio value fallback: $250,000 in non-production
  │
  └── 3. Organism Governance (organism/governance.py)
      ├── In-memory state (brain-persisted)
      ├── Drawdown kill switch (code default: 5%, docker: 3%, .env: 8%)
      │   └── Persistence: env vars override persisted values on restore
      ├── Adaptive cooldown (code: 1-3hr base; docker default: 5-15min due to 300s base)
      ├── Trading halt (manual or automatic)
      ├── Adaptation freeze
      └── Change budget (100/day, env overrides persisted)
```

### Platform RiskManager Details

| Metric | Computation | Status Levels |
|---|---|---|
| `daily_loss` | Today's realized + unrealized PnL | normal → warning (80%) → critical (95%) → breached |
| `max_drawdown` | Peak-to-trough equity decline | Same 4 levels |
| `position_count` | Active open positions | Same 4 levels |
| `total_exposure` | Sum of absolute position values / equity | Same 4 levels |
| `order_count_daily` | Orders placed today | Same 4 levels |
| `buying_power_used` | (equity - buying_power) / equity | Same 4 levels |

Emergency stop workflow:
1. Admin triggers via API
2. All active strategies → stopped
3. All open orders → cancelled via broker
4. EmergencyStop record created (status=active)
5. Manual resolution required (POST /emergency-stop/{id}/resolve)

---

## 56. INTER-MODULE DEPENDENCY MAP

### Order Flow (Critical Path)

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        ORDER EXECUTION FLOW                               │
│                                                                           │
│  LiveEngine.live_tick()                                                   │
│       │                                                                   │
│       ▼                                                                   │
│  OrderService.submit_symbol_order()                                       │
│       │                                                                   │
│       ├── 1. Check CircuitBreaker (Redis-backed, 5% PnL kill)            │
│       │       └── Bypassed if reduce_only=True (exit orders)            │
│       ├── 2. Create Order record in DB (status: submitted)               │
│       ├── 3. Enqueue OutboxEvent (topic: order.submitted) — SAME TX      │
│       └── 4. Return immediately (async, <1ms)                            │
│                                                                           │
│  OutboxWorker._dispatcher() (100ms poll loop)                            │
│       │                                                                   │
│       ├── 5. Claim batch (10 events, FOR UPDATE SKIP LOCKED)             │
│       ├── 6. Resolve execution mode (execute/shadow/dry_run)             │
│       │       ├── shadow → record intent, skip broker                    │
│       │       ├── dry_run → simulate fill                                │
│       │       └── execute → continue to broker                           │
│       ├── 7. Call AlpacaOutboxDispatcher                                 │
│       │       └── broker.place_order() → Alpaca REST API                 │
│       ├── 8. Update Order status in DB (broker_order_id, fill data)      │
│       └── 9. Broadcast via Socket.IO (only on DLQ/rejection; fills via step 13) │
│                                                                           │
│  AlpacaStream (WebSocket listener)                                        │
│       │                                                                   │
│       ├── 10. Receive fill/cancel/reject from Alpaca                     │
│       ├── 11. Find order in DB (by broker_order_id or client_key)        │
│       ├── 12. Update DB with fill details                                │
│       └── 13. Broadcast via Socket.IO                                    │
└──────────────────────────────────────────────────────────────────────────┘
```

### Engine → Component Dependencies

```
OrganismLiveEngine (constructor injection):
  │
  ├── data_client ────────────→ AlpacaDataClient (REST bars)
  ├── order_service ──────────→ OrderService → OutboxRepo → DB
  ├── positions_service ──────→ PositionsService → Alpaca REST
  │
  ├── Internal (created by engine):
  │   ├── MLSignalGenerator ──→ XGBClassifier + XGBRegressor + Ensemble
  │   ├── AlphaScanner ───────→ 7-factor scoring (ML + breakout + momentum)
  │   ├── BreakoutScanner ────→ 6-detector scoring
  │   ├── KellySizer ─────────→ Regime-stratified Kelly + scaling
  │   ├── AdaptiveExitEngine ─→ 8-priority exit levels
  │   ├── MomentumPyramider ──→ 3-layer pyramid management
  │   ├── RegimeDetector ─────→ 7-label detection + EMA smoothing
  │   ├── GovernanceController → Kill switch + halt + freeze
  │   ├── EvolutionEngine ────→ 10-step self-evolution
  │   ├── TransferLearning ───→ Cross-run knowledge (20 snapshots)
  │   ├── BackgroundTrainer ──→ ProcessPoolExecutor (separate CPU)
  │   └── DecisionTelemetry ──→ Ring buffer (360 ticks)
  │
  └── KEY INSIGHT: LiveEngine has ZERO direct infra/broker imports
      └── All external I/O injected via constructor
```

### Startup Boot Chain

> See [§44 Engine Startup Sequence](#44-engine-startup-sequence) for the full 14-step boot order and middleware stack. Summary: Observability → DB → Outbox → Strategies → Organism/MultiStrategy (mutex) → Scanners → WebSocket → Reconciliation → Sync.

### Middleware Chain

```
REQUEST → CORS → GZip → Deduplication → Rate Limiting → HTTP Metrics → Security Headers → ROUTE
```
> Detail in [§44 Middleware Stack](#44-engine-startup-sequence).

---

# LAYER 9: ML INFRASTRUCTURE (backend/ml/)

> The `backend/ml/` directory contains 17 modules that form the platform-level ML infrastructure. These are **separate from** the organism ML modules (`backend/organism/ml_signal.py`, `ensemble_models.py`, etc.) which are organism-specific. The `backend/ml/` modules provide general-purpose ML capabilities used by multiple consumers.

## 57. ML PIPELINE ARCHITECTURE

**Source**: `backend/ml/pipeline.py`

### Pipeline Stages

```
PipelineStage (8 stages):
  1. DATA_INGESTION        → Raw data collection
  2. FEATURE_ENGINEERING   → Feature extraction
  3. FEATURE_VALIDATION    → Feature QA gates
  4. MODEL_TRAINING        → Model fitting
  5. MODEL_VALIDATION      → Performance evaluation
  6. MODEL_DEPLOYMENT      → Model promotion
  7. INFERENCE             → Live predictions
  8. MONITORING            → Drift + performance tracking

PipelineStatus: pending → running → completed | failed | cancelled

PipelineConfig:
  - feature_cache_ttl_seconds: 3600 (1 hour)
  - validation_split: 0.2, early_stopping_patience: 10
  - max_training_time_seconds: 3600, batch_size: 32
  - inference_timeout_ms: 100.0
  - drift_threshold: 0.1, performance_window_days: 7
  - A/B testing: challenger_traffic_pct: 0.1 (10%), modular arithmetic routing
  - Model versioning + drift monitoring integration
```

### Pipeline Flow

```
                ┌──────────────────────────────────────────────────────┐
                │                 ML PIPELINE                          │
                │                                                      │
  Training ─────┤  data_processing → feature_engineering → training    │
  Path          │  → validation → active_model_pointer (write)         │
                │                                                      │
  Inference ────┤  active_model_pointer (read) → prediction_service    │
  Path          │  → ensemble_framework                                │
                │                                                      │
  Monitoring ───┤  monitoring.py (retrain decision) → lifecycle.py     │
  Path          │  → lifecycle_scheduler.py (execution)                │
                │                                                      │
  Staleness ────┤  staleness_detector (5D) + drift (PSI)               │
  Check         │  → decide_retrain() → retraining trigger             │
                └──────────────────────────────────────────────────────┘
```

---

## 58. FEATURE ENGINEERING & DATA PROCESSING

### Data Processing

**Source**: `backend/ml/data_processing.py`

```
SimpleScaler (no sklearn dependency):
  │
  ├── Standard scaling: (x - mean) / std
  ├── MinMax scaling: (x - min) / (max - min)
  └── Robust scaling: (x - median) / MAD

  epsilon: 1e-8 (prevents division by zero)
  Fit/transform pattern for ML preprocessing
```

### Feature Engineering

**Source**: `backend/ml/feature_engineering.py`

```
FeatureConfig:
  feature_types:
    - technical    (SMA, RSI, MACD, Bollinger, etc.)
    - statistical  (variance, skew, kurtosis)
    - categorical  (sector, market cap bucket)
    - temporal     (hour, day-of-week, month)
    - derived      (cross-feature interactions)

  Prometheus metrics:
    - feature_engineering_transforms_total
    - feature_engineering_duration_seconds
```

### Sentiment

**Source**: `backend/ml/sentiment.py`

Wrapper module re-exporting `SocialSentimentAnalyzer` from `backend/data/social_sentiment.py`. Provides sentiment-based features for the ML pipeline.

---

## 59. MODEL TRAINING & VALIDATION

### Training

**Source**: `backend/ml/training.py`

```
TrainingStatus: pending → running → completed | failed

Supported Algorithms (requires scikit-learn):
  - RandomForestClassifier / Regressor
  - LogisticRegression / LinearRegression
  - SVM (SVC / SVR)
  - GradientBoosting

Cross-Validation Methods:
  - GridSearchCV
  - RandomizedSearchCV
  - TimeSeriesSplit (walk-forward)
  - KFold / StratifiedKFold

Security: secure_load() wrapper for model deserialization
Raises: RuntimeError if sklearn not installed
```

### Validation

**Source**: `backend/ml/validation.py`

```
KFoldSplitter:
  - Real K-Fold cross-validation (numpy-based, no sklearn mocks)

Metrics computed:
  - accuracy, precision, recall, f1_score
  - confusion matrix (multi-class support)
  - Handles zero-division and degenerate cases

_compute_binary_metrics():
  - True numpy implementation
  - Edge case: all-same-class → accuracy=1.0, precision/recall=0.0
```

### Model Selection

**Source**: `backend/ml/model_selection.py`

```
BacktestEvalResult:
  - n_samples, total_return, cagr, sharpe, max_drawdown

Target kinds:
  - "next_close"    → regression
  - "direction_up"  → classification (threshold: 0.5 default)

Methods:
  - time_split_by_fraction()   → train/test split respecting time order
  - positions_from_predictions() → convert signals to position sizing
  - simulate_pnl_long_flat()   → long-flat equity curve simulation
```

---

## 60. MODEL REGISTRY & LIFECYCLE

### Model Management

**Source**: `backend/ml/model_management.py`

```
ModelStatus flow:
  registered → training → trained → deployed → retired
                                  └→ failed

ModelMetadata:
  - name, version, status, timestamps
  - performance metrics, config
  - Serialization: joblib, pickle, JSON
  - Checksum validation (file integrity)
  - File size tracking, tag-based organization
```

### Model Registry

**Source**: `backend/ml/model_manager.py`

```
InMemoryModelRegistry:
  - Keyed by (name, version) tuple → (model, ModelVersion)
  - Feature schema lock for consistency
  - PSI drift detection integration
  - Respects DISABLE_ML env var (set to "0" by default)
  - In-memory for Light Mode / testing
```

### Active Model Pointer

**Source**: `backend/ml/active_model_pointer.py`

```
Disk-based pointer system:
  - Bridges training jobs → live inference
  - JSON pointer files in active_models/ subdirectory
  - ActiveModelInfo dataclass: model path, metadata
  - write_active_model_pointer() — called after training
  - read_active_model_pointer()  — called by inference

Config:
  - ACTIVE_MODEL_POINTER_DIR env var
  - MODEL_STORE_PATH env var
```

### Lifecycle Orchestrator

**Source**: `backend/ml/lifecycle.py`, `backend/ml/lifecycle_scheduler.py`

```
Lifecycle cadence:
  - Daily:   snapshot + monitoring
  - Weekly:  retrain cycle
  - Monthly: promotion review

LifecycleJobResult: { ok: bool, message: str, details: dict }
Events logged to ModelLifecycleEvent table for audit trail

Scheduler:
  - In-process (ENABLE_ML_LIFECYCLE_SCHEDULER=1)
  - Accepts HH:MM config via env vars
  - Respects market hours and weekends
  - WARNING: Multi-worker risk — use external cron in production
```

---

## 61. ENSEMBLE FRAMEWORK & PREDICTION SERVICE

### Ensemble Framework

**Source**: `backend/ml/ensemble_framework.py`

```
VotingStrategy (5 modes):
  - weighted_average      — weighted mean of predictions
  - majority_vote         — democratic decision
  - confidence_weighted   — scale by model confidence
  - stacking              — meta-learner on base predictions
  - dynamic               — adjust weights based on recent performance

ModelPredictionResult:
  - prediction, confidence, signal_strength
  - direction: long / short / neutral
  - latency tracking

EnsemblePredictionResult:
  - Aggregated across all base models
  - Combined confidence + signal strength
```

### Prediction Service

**Source**: `backend/ml/prediction_service.py`

```
PredictionRequest → PredictionResult

PredictionType:
  - classification, regression, forecast, anomaly_detection

PredictionStatus:
  - pending → processing → completed | failed | cached

Execution:
  - ThreadPoolExecutor for async predictions
  - Timeout: 30s default
  - Cache-enabled by default
  - Supports probability return
```

---

## 62. DRIFT DETECTION & MONITORING

### Drift Detection

**Source**: `backend/ml/drift.py`

```
Population Stability Index (PSI):
  - Measures feature distribution shift between training and live data
  - Quantile binning: 10 bins default
  - epsilon handling for edge cases

DriftResult:
  - psi_score: float (overall)
  - feature_psi: dict (per-feature breakdown)
  - affected_features: list[str]

Handles degenerate distributions (zero-size bins → fallback)
```

### Retraining Monitor

**Source**: `backend/ml/monitoring.py`

```
decide_retrain() → RetrainDecision:
  - should_retrain: bool
  - reasons: list[str] (human-readable justifications)

Retrain Triggers:
  │
  ├── PSI >= 0.15 → feature drift detected
  ├── Performance drop >= 2% (min_return_drop)
  └── Negative recent returns → fallback retrain
```

### Staleness Detector

**Source**: `backend/ml/staleness_detector.py`

```
5-Dimension Staleness Analysis:
  │
  ├── 1. Age (days since training)
  ├── 2. Performance decay (accuracy drop %)
  ├── 3. Feature drift (PSI score)
  ├── 4. Prediction drift (distribution shift)
  └── 5. Regime change (new regime since training)

StalenessLevel: fresh → aging → stale → critical

StalenessReasons (enum):
  age, performance_decay, feature_drift,
  prediction_drift, regime_change, low_confidence, manual
```

---

# APPENDICES

## A. CONFIGURATION REFERENCE

### Engine Configuration (.env)

| Variable | Code Default | Docker Default | .env Override | Effect |
|---|---|---|---|---|
| `ORGANISM_TICK_INTERVAL_SECONDS` | 60 | 60 | **10** | Tick frequency |
| `ORGANISM_LIVE_TIMEFRAME` | 1Day | **1Min** | 1Min | Bar timeframe |
| `ORGANISM_MAX_POSITIONS` | **8** | **15** | 15 | Max simultaneous positions |
| `ORGANISM_LONG_ONLY` | true | true | true | Block all short entries |
| `ORGANISM_RETRAIN_INTERVAL` | 60 (200 intraday auto) | **600** | 180 | Ticks between retrains |
| `ORGANISM_ML_DECAY_RATE` | 0.005 | 0.005 | 0.005 | Time-decay on training samples |
| `ORGANISM_MAX_PER_SECTOR` | 4 | 4 | 4 | Sector concentration limit |
| `ORGANISM_DRAWDOWN_KILL_PCT` | **0.05** | **0.03** | **0.08** | Drawdown kill switch |
| `ORGANISM_DRAWDOWN_COOLDOWN_S` | 3600 | **300** | — | Base cooldown after kill |
| `ORGANISM_MAX_CHANGES_PER_DAY` | 100 | **500** | — | Daily evolution budget |
| `ORGANISM_LIVE_LOOKBACK` | 500 | **100** | — | Bars of history to fetch |
| `ORGANISM_LIVE_SYMBOLS` | 22 symbols (+SH,PSQ) | **SPY,QQQ** | 22 symbols | Universe CSV (improve9 B4: +inverse ETFs) |
| `ORGANISM_TRAIN_WINDOW` | 200 | **100** | — | Training window size |
| `ORGANISM_MIN_BARS` | 200 (50 intraday auto) | **50** | — | Minimum bars for a symbol |
| `ORGANISM_NIGHTLY_ENABLED` | 0 | — (not in docker) | — | Nightly training cycle |
| `ORGANISM_NIGHTLY_INTERVAL_S` | 86400 | — | — | Nightly training interval (seconds) |
| `ORGANISM_HALT_TRADING` | 0 | — (not in docker) | — | Manual trading halt |
| `ORGANISM_FREEZE_ADAPTATION` | 0 | **1** | 1 | Freeze all adaptation |
| `SCANNER_ENABLED` | true | — (not in docker) | — | Enable market scanner |
| `ORGANISM_USE_STREAMING` | false | 0 (docker) | — | Use streaming data provider |
| `ORGANISM_PREDICTION_HORIZON` | Timeframe-dependent | — | — | ML prediction horizon (H bars ahead). Defaults: 1Min=15, 5Min=6, 15Min=3, 1Hour=2, 1Day=1 |
| `ORGANISM_EXPLORATION_ENABLED` | false | — | — | Legacy: exploration bucket disabled (improve9 A7) |
| `ORGANISM_EXPLORATION_MAX_NOTIONAL` | 200.0 | — | — | Max $ per exploration position |
| `ORGANISM_EXPLORATION_MAX_POSITIONS` | 3 | — | — | Max concurrent exploration positions |

### Alpaca Configuration

| Variable | Default | Notes |
|---|---|---|
| `ALPACA_API_KEY_ID` | — | Also: `ALPACA_API_KEY`, `APCA_API_KEY_ID` |
| `ALPACA_API_SECRET_KEY` | — | Also: `ALPACA_SECRET_KEY`, `APCA_API_SECRET_KEY` |
| `ALPACA_PAPER` | true | true=paper, false=live |
| `ALPACA_DATA_FEED` | sip (code default) / iex (docker default) | Code defaults to sip; docker-compose overrides to iex |
| `USE_MOCK_BROKER` | false | true=mock broker for testing |

### Infrastructure Configuration

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | — | `postgresql+asyncpg://...` |
| `DATABASE_POOL_SIZE` | 20 | Connection pool |
| `DATABASE_MAX_OVERFLOW` | 10 (30 in Docker) | Pool overflow |
| `REDIS_URL` | — | `redis://:password@host:port/db` |
| `JWT_SECRET_KEY` | — | Required, min 32 chars |
| `OUTBOX_POLL_INTERVAL` | 0.1 | Seconds (100ms) |
| `RECONCILIATION_INTERVAL_MINUTES` | 15 | Position reconciliation |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | http://otel-collector:4317 | Tracing endpoint |
| `APP_ENVIRONMENT` | — | development (docker) |
| `APP_LOG_LEVEL` | — | INFO (docker) |
| `ENABLE_OUTBOX_PATTERN` | — | true (docker) |
| `ENABLE_BACKGROUND_TASKS` | — | true (docker) |
| `ENABLE_WEBSOCKET` | — | true (docker) |
| `ENABLE_ML_LIFECYCLE_SCHEDULER` | 0 | ML lifecycle scheduler opt-in |

---

## B. KEY THRESHOLDS SUMMARY

| Threshold | Value | Location | Purpose |
|---|---|---|---|
| Alpha composite minimum | 0.15 | alpha_scanner | Minimum score to be a candidate |
| Breakout composite minimum | 0.20 | breakout_scanner | Minimum breakout score |
| Pure breakout entry threshold | 0.55 | live_engine | Breakout-only entries need high score |
| Full production promotion gate | strategy-only total_pnl ≥ 0, last_50_mean_pnl ≥ 0, last_50_win_rate ≥ 0.35, sharpe_per_trade ≥ 0 | trading_phase + `/api/v1/health/strategy` | Mature losing brains stay in production_guarded: strict entry gates remain, ML influence and Kelly remain disabled; reconciliation bookkeeping is exposed separately as all-record expectancy |
| Strategy live-order gate | `StrategyGovernor.authorize_signal(..., live_intent=True)` must allow before OrderService entry submission | live_engine + strategy_governor | Blocks unknown, shadow-only, live-disabled, insufficient-evidence strategy IDs before any entry order can reach the broker path |
| Phase 9D portfolio construction gate | ≥2 portfolio-eligible strategies from ≥2 independent families, each with positive after-cost alpha, positive avg R, PF ≥1.20, concentration within limits, correlation ≤0.75, weighted beta ≤0.35 | `evidence/portfolio_construction.py` + `scripts/phase9d_portfolio_construction.py` | Advisory only: no live sizing/order/promotion changes; blocks portfolio scaling when evidence is replay-only or one-family |
| Symbol fitness gate | **0 (learning, no gate)** / 0.45 (production, 10+ trades) | live_engine | improve9 B1: unified canonical system. Learning = soft ranking only. Production = hard reject for established losers |
| Liquidity gate | 10K avg vol/bar | live_engine | Block illiquid symbols (per-bar, not daily) |
| ML confidence reversal | 0.60 (intraday) / 0.65 (daily) | live_engine | ML reversal exit — partial exit 30%/25% of position |
| Min hold before profit exits | dynamic: max(H//3, 3) = **5 bars** (5 min) for H=15 | adaptive_exits | _min_hold_bars(prediction_horizon) — suppresses all profit exits |
| Max loss safety net | 8% (via for_timeframe; base default 15%) | adaptive_exits | Absolute loss limit |
| Edge-over-cost gate | 2× spread_cost (dynamic) | kelly_sizer | Predicted return must clear 2× per-symbol cost [3-50bps] |
| Kelly ML confidence min | 0.5 | kelly_sizer | _ML_CONFIDENCE_MIN — minimum confidence to trigger ML floor |
| Kelly ML floor | 0.04×conf (trained) / 0.02×conf (untrained) | kelly_sizer | Minimum sizing when ML confident + edge clears cost |
| Kelly breakout floor | 0.003×score (requires kelly<0.005, score>=0.55) | kelly_sizer | Minimum sizing on strong breakout + edge clears cost |
| Kelly confidence cap (untrained) | 0.9 | kelly_sizer | Confidence scaling ceiling when ML untrained (was 0.6 — prevented cold-start sizing) |
| Kelly risk-budget floor | **0.10% equity** / atr_stop (learning or production_guarded), 0.25% / (atr × 1.5) × conf_floor_scale (full production) | kelly_sizer | improve9 A1 + Phase 2: fixed ATR-dollar risk while ML/Kelly are not promoted. Full production = pre-Kelly floor with confidence scaling |
| Kelly raw cap | 1.0 (100%) | kelly_sizer | Prevents oversized raw Kelly fractions |
| Kelly min notional | $500 intraday / $2,000 daily | kelly_sizer | Minimum position size (set by live_engine per timeframe) |
| Kelly max per position | 8% intraday / 10% daily | kelly_sizer | Position concentration limit (set by live_engine per timeframe) |
| Kelly max portfolio | 95% | kelly_sizer | Total exposure limit |
| Drawdown risk-off | 25% | kelly_sizer | No new positions at all |
| Drawdown kill switch | code default: 5%, docker default: 3%, .env override: 20% | governance | Halt all entries |
| Intraday size reduction | 40% | live_engine | Last 15 min of session (3:45-4:00 ET) |
| EOD entry block | 15:45 ET | live_engine | Block all new entries (improve7) |
| EOD flatten | 15:58 ET | live_engine | Force close all open positions (improve7) |
| Opening block window | 30 min (9:30-10:00 ET) | live_engine | No entries during open auction (intraday only) |
| Regime sit-out | high_vol/stress + all bearish ML | live_engine | Block entries when all ML signals are short |
| Entry throttle | dynamic: 12/hr (learning) or max(3, 6-open) (production) | live_engine | Learning mode (< 200 trades) gets more entries for data collection. Also gated by bar boundaries (A6) and burst cap (4/15min) |
| Warmup gate | 5 ticks | live_engine | Block entries on cold start |
| Pure breakout cap | 2 per tick | live_engine | _MAX_PURE_BREAKOUT limit |
| BG training timeout | 30 ticks | live_engine | Force-reset stuck background training |
| ML reversal partial exit | 30% (intraday) / 25% (daily) | live_engine | Partial position exit on ML reversal |
| Equity-zero threshold | 3 consecutive | live_engine | Block entries on stale data |
| Walk-forward regression | 0.95 | brain_persistence | Don't persist regressing model |
| Feature QA NaN rate | 20% | feature_store | Reject feature set |
| NaN missingness gate | 25% | live_engine | Block entries when >25% features are NaN/Inf |
| Feature QA missing bars | 10% | feature_store | Flag data quality issue |
| Failure-to-follow delay | chop: max(H×4/5, 5) = **12 bars**; other: max(H//2, 3) = **7** for H=15 | adaptive_exits | Chop gets longer delay (improve7) |
| Failure-to-follow R thresholds | regime-dependent (0.10R–0.25R) | adaptive_exits | trending_up/low_vol/high_vol=disabled; chop=0.15R (**losers-only exit, winners get stop tightened**); stress=0.10R; others=0.25R |
| Confidence entry gate | 0.40 (0.45 in chop/high_vol/trending_down) | live_engine | Below-threshold candidates logged only (improve9 A7: exploration removed) |
| Alpha+breakout bad-regime filter | enabled by default | live_engine | Blocks alpha+breakout entries in chop/trending_down; records blocked candidates with `live_pipeline_candidate=false` for evidence |
| Symbol circuit breaker | (a) 2+ consec losses + 0 wins, (b) PnL ≤ -max($25, 0.10% eq), (c) 2+ SL in 30min | live_engine | Ban symbol for session (improve8 enhanced) |
| Regime evolution freeze | 200+ total trades AND 30+ per regime | kelly_sizer | Evolved regime scales locked until statistically stable (improve7) |
| Full evolution freeze | **300+ total trades** | live_engine | improve9 B5: ALL self-evolution frozen until 300 clean trades. Only ML retraining runs. |
| Horizon timeout | **18 bars** (learning only) | adaptive_exits | improve9 A3: Hard exit at H=15 + 3 grace bars. Aligns exits to thesis horizon |
| Burst entry cap | **4 per rolling 15 min** | live_engine | improve8 C2: Prevents bursty post-hotfix entry cascades |
| Stop-loss re-entry cooldown | **180 ticks** (30 min) | live_engine | improve8: Extended cooldown after stop-loss exit |
| FTF-loss re-entry cooldown | **60 ticks** (10 min) | live_engine | improve8: Moderate cooldown after FTF loss |
| Loser time-stop fallback | **120 bars** (2 hours) | adaptive_exits | Used when max_bars=0 (trending_up, low_vol). Was 200 ticks (~33 min). |
| Time decay rate | **0.3%/bar** | adaptive_exits | Tightens stop after decay_start. Was 1%/tick (6× too fast). |
| Entry slippage cap | 0.1% | live_engine | Marketable limit orders cap slippage at 0.1% above ask / below bid |
| Stale data threshold | 120s | live_engine | Block entries when streaming_provider.last_update_time > 2 min stale (exits still run) |
| Predicted return ML floor | 0.3% | live_engine | Min predicted_return when ML signal present |
| Predicted return no-ML range | 0.5%–2.0% | live_engine | 0.005 + 0.015×breakout_score when no ML |
| Circuit breaker failures | 5 | resilience | Open circuit breaker |
| Circuit breaker recovery | 60s | resilience | Try half-open |
| Alert dedup window | 300s | alerting | Suppress duplicates |
| Alert rate limit | 30/min | alerting | Cap alert volume |
| Stale order pending | 5 min | order_guardrails | Mark as failed |
| Stale order accepted | 24 hr | order_guardrails | Flag for reconciliation |

---

## C. DATA FLOW SUMMARY

| Path | Direction | Protocol | Format | Latency |
|---|---|---|---|---|
| Order Placement | OUT | REST/HTTP | JSON | ~100ms |
| Order Fill Update | IN | WebSocket | JSON | Real-time (<100ms) |
| Historical Bars | OUT | REST/HTTP | JSON | ~500ms |
| Real-time Quote | IN | WebSocket | JSON Array | Real-time |
| Real-time Trade | IN | WebSocket | JSON Array | Real-time |
| Real-time Bar | IN | WebSocket | JSON Array | Real-time |
| Position Check | OUT | REST/HTTP | JSON | ~100ms |
| Account Status | OUT | REST/HTTP | JSON | ~100ms |
| Frontend Updates | OUT | Socket.IO | JSON | Real-time |
| Metrics Scrape | OUT | HTTP | Prometheus text | ~50ms |
| Brain Save | Local | File I/O | JSON/CSV | ~200ms |

---

## D. ERROR HANDLING HIERARCHY

### Recoverable Errors (with retry)

1. **Network**: httpx.TimeoutException, httpx.ConnectError
2. **API**: 429 (rate limit), 500, 502, 503, 504
3. **WebSocket**: Connection lost → reconnect with backoff

### Non-Recoverable Errors (fail fast)

1. **Client**: 400, 401, 403, 404 (except expected 404s), 422 (unless duplicate order)
2. **Auth**: Missing credentials
3. **Config**: Invalid symbols, malformed requests

### Duplicate Order Recovery

- 422 with "client_order_id must be unique" → GET /orders:by_client_order_id → return recovered order

### DLQ Escalation

- Outbox: 5 retries → DLQ + WebSocket "order.rejected" broadcast
- Circuit breaker: 5 failures → OPEN → 60s recovery → HALF_OPEN
- Alert escalation: WARNING → ERROR → CRITICAL (PagerDuty)

---

## E. MODULE INDEX

### organism/ (37 modules)

| Module | Purpose |
|---|---|
| `live_engine.py` | Core tick loop, causal as-of feature boundary, StrategyGovernor entry authorization, telemetry, trade reconstruction |
| `adaptive_exits.py` | ATR-based exits, 15% base safety net (8% via for_timeframe), failure-to-follow (momentum-confirmed, regime R thresholds, delay=H//2, disabled for trending_up/low_vol/high_vol), loser time-stop (fallback=120), wall-clock bar-boundary gating, regime-adaptive |
| `alpha_scanner.py` | 7-factor alpha scoring + Stocks-in-Play overlay + inverse ETF regime flip, top-5 candidates (improve9 B2/B3/B4) |
| `attribution.py` | Per-strategy reward signals from DB fills |
| `background_trainer.py` | ProcessPoolExecutor ML retraining |
| `brain_persistence.py` | Save/load brain state to JSON |
| `breakout_scanner.py` | 6-detector breakout scoring |
| `composite_indicators.py` | 7 proprietary composite indicators |
| `continuous_learner.py` | Online incremental learning |
| `decision_telemetry.py` | Ring buffer (360 ticks) for decisions dashboard |
| `diagnostic_checks.py` | 36 diagnostic checks, 8 categories |
| `diagnostic_scheduler.py` | Report store + pre-open/post-close scheduler |
| `diagnostics.py` | Entry points: preflight, continuous, full suite |
| `evidence/portfolio_construction.py` | Phase 9D evidence-only risk-budget, beta, correlation, family-diversity, and exposure scaling verdicts; no live behavior mutation |
| `ensemble_models.py` | Combined classifier + regressor ensemble |
| `feature_store.py` | Versioned features with QA gates |
| `governance.py` | Kill switch, halt, freeze, change budget |
| `kelly_sizer.py` | Half-Kelly sizing, regime-stratified, state-dependent cost model, timeframe-aware annualization |
| `market_scanner.py` | Broad universe scan (most-actives, gainers, losers) |
| `ml_features.py` | 79 ML features across 11 categories, _nan_missingness column for data quality gating |
| `ml_signal.py` | Dual XGBoost + ensemble, confidence calibration |
| `multi_timeframe.py` | MTF signal alignment (1m/5m/15m/1h/1d) |
| `nightly_scheduler.py` | Nightly training cycle with backoff |
| `promotion.py` | 6-stage model promotion state machine |
| `pyramider.py` | 3-layer momentum pyramid (60/30/10%) |
| `regime.py` | Regime detection (7 labels), drift detection |
| `replay_simulator.py` | Historical tick replay for backtesting |
| `routes.py` | 29 FastAPI endpoints for organism (status, brain, universe, scanner, decisions, diagnostics, evolution, control) |
| `runner.py` | Unified tick coordinator |
| `scheduler.py` | APScheduler tick loop + diagnostics wiring |
| `sector_map.py` | GICS sector mapping, diversification gate |
| `self_evolution.py` | 10-step meta-learning parameter evolution |
| `streaming_data_provider.py` | WebSocket bar stream + ring buffers |
| `training.py` | Training orchestrator (slow brain) |
| `transfer_learning.py` | Cross-run knowledge transfer |
| `universe_selector.py` | Fitness-based symbol rotation |
| `walk_forward.py` | Walk-forward evaluation + acceptance gates |
| NOTE: `staleness_detector.py` lives in `backend/ml/`, not `organism/ml/` — listed under ml/ section below |

### infra/ (24 modules)

| Module | Purpose |
|---|---|
| `alerting.py` | Slack + PagerDuty alerts, dedup, rate limiting |
| `broker.py` | Redis health check |
| `cache.py` | LRU+TTL memory cache, hot data singleton |
| `db.py` | Async PostgreSQL engine, sessions, pool config |
| `guardrails.py` | 8-layer order validation |
| `guardrails_production.py` | Atomic daily caps, circuit breaker |
| `logging.py` | Structured JSON logging, OTel correlation |
| `metrics.py` | Prometheus registry, cardinality enforcement |
| `object_pool.py` | Thread-safe object pool for orders |
| `observability.py` | OTel tracing, auto-instrumentation |
| `observability_contracts.py` | Fixed histogram bucket definitions |
| `order_guardrails.py` | Post-submission timeout + stale cleanup |
| `outbox.py` | Transactional outbox pattern + DLQ |
| `outbox_worker.py` | Background dispatcher (100ms poll) |
| `performance.py` | LRU cache, batch processor, ring buffer |
| `production.py` | Health checks, graceful shutdown, feature flags |
| `resilience.py` | Circuit breaker, retry with backoff |
| `schemas.py` | SQLAlchemy ORM models (25 tables, incl. TickTelemetry) |
| `security.py` | JWT auth, bcrypt, RBAC, token blacklist |
| `security_hardening.py` | Rate limit, security headers, input validation |
| `unified_database.py` | DEPRECATED — migrated to `infra/db.py` |
| `users.py` | User repository, brute force protection (5 attempts → 15 min lockout) |
| `validation.py` | Symbol validation (max 10 chars), price validation (max $100M, 4 dp) |
| `repositories/*.py` | 7 repositories: orders, positions, executions, signals, models, audits, strategies |

### integrations/ (6 modules)

| Module | Purpose |
|---|---|
| `alpaca_broker.py` | REST client for Alpaca order/position/account API |
| `alpaca_data.py` | Alpaca historical bar fetcher with retry, split adjustment, observability |
| `alpaca_outbox.py` | Outbox dispatcher to Alpaca with smart TIF |
| `alpaca_stream.py` | WebSocket client for trade updates (dev/paper) |
| `alpaca_market_data_stream.py` | WebSocket client for real-time market data |
| `alpaca_stream_production.py` | Production stream with gap-fill, dedup, circuit breaker |

### api/ (15+ modules)

| Module | Purpose |
|---|---|
| `lifespan.py` | Startup/shutdown orchestrator (14 steps) |
| `factory.py` | FastAPI app assembly |
| `middleware_setup.py` | CORS, GZip, dedup, rate limit, metrics |
| `routes_setup.py` | Route registration at /api/v1 |
| `socketio_server.py` | Socket.IO for real-time broadcasts |
| `websocket_manager.py` | WS client management with backpressure |
| `routes/health.py` | /health, /livez, /readyz probes |
| `routes/orders.py` | Order CRUD with rate limiting |
| `routes/auth.py` | JWT login, refresh, logout |
| `routes/monitoring.py` | Prometheus /metrics endpoint |
| `routes/observability.py` | Health dashboard, alerts |

### services/ (27 modules)

| Module | Purpose |
|---|---|
| `risk_manager.py` | Risk metrics, limits, violations, emergency stop |
| `order_service.py` | Order creation via outbox + Redis-backed circuit breaker + reduce_only bypass for exits |
| `portfolio_service.py` | Portfolio aggregation |
| `portfolio_sync_service.py` | Alpaca → DB sync on startup |
| `position_reconciliation_service.py` | DB vs broker discrepancy detection |
| `scheduled_reconciliation.py` | 15-min reconciliation scheduler |
| `market_data_service.py` | Alpaca market data wrapper + WS pub/sub bridge |
| `quote_manager.py` | Redis-cached real-time quotes (5s TTL) |
| `trading_execution_mode.py` | execute/shadow/dry_run mode with runtime override |
| `observability_service.py` | Aggregated health checks |
| `multi_strategy_live_runner.py` | 10 independent strategy engine coordinator |
| `multi_strategy_live_scheduler.py` | Background scheduler for multi-strategy path |
| `audit_service.py` | SEC 17a-4 compliance, SHA-256 hash chain, 24 action types |
| `backtest_service.py` | Strategy backtesting engine (equity curve, trade log) |
| `lot_tracker_service.py` | FIFO lot matching, cost basis, tax lot tracking |
| `trade_analytics_service.py` | Institutional analytics (Sharpe, Sortino, Calmar, profit factor) |
| `slippage_model.py` | Almgren-Chriss market impact model, time-of-day adjustments |
| `strategy_service.py` | Strategy CRUD, lifecycle, versioning, rollback |
| `auto_breakout_scanner.py` | Standalone breakout scanner (0-100 score, $5-2K filter) |
| `cache.py` | 3-layer Redis cache (quotes/bars/indicators) with HA support |
| `indicators.py` | 25+ technical indicators (SMA, RSI, MACD, Bollinger, Ichimoku...) |
| `symbol_validator.py` | Alpaca asset validation (tradable + active), fail-open |
| `positions_service.py` | Alpaca position API wrapper, portfolio value |
| `position_import_service.py` | Import pre-existing Alpaca positions with dedup |
| `signal_service.py` | Signal cache/relay layer for multi-strategy runner |
| `trade_service.py` | Trade history, CSV export, realized PnL integration |
| `auto_breakout_scanner_scheduler.py` | Background scheduler for breakout scanner runs |

### ml/ (17 modules)

| Module | Purpose |
|---|---|
| `active_model_pointer.py` | Disk-based pointer bridging training → live inference |
| `data_processing.py` | SimpleScaler (standard/minmax/robust), no sklearn dependency |
| `drift.py` | PSI-based feature drift detection (10 quantile bins) |
| `ensemble_framework.py` | 5 voting strategies (weighted, majority, confidence, stacking, dynamic) |
| `feature_engineering.py` | 5 feature types (technical, statistical, categorical, temporal, derived) |
| `lifecycle.py` | Daily snapshots, weekly retrains, monthly promotion reviews |
| `lifecycle_scheduler.py` | In-process scheduler (ENABLE_ML_LIFECYCLE_SCHEDULER=1) |
| `model_management.py` | Metadata, versioning, serialization (joblib/pickle/JSON) |
| `model_manager.py` | In-memory registry with feature schema lock + PSI drift |
| `model_selection.py` | Backtest evaluation (Sharpe, CAGR, max drawdown) |
| `monitoring.py` | Retrain decision logic (PSI >= 0.15, perf drop >= 2%) |
| `pipeline.py` | 8-stage ML pipeline orchestration with caching |
| `prediction_service.py` | Async predictions (ThreadPool, 30s timeout, caching) |
| `sentiment.py` | Re-exports SocialSentimentAnalyzer from data/ |
| `staleness_detector.py` | 5-dimension staleness (age, decay, drift, prediction, regime) |
| `training.py` | sklearn training (RF, LR, SVM, GB) + cross-validation |
| `validation.py` | K-Fold CV, binary metrics, confusion matrix (numpy-based) |

### models/ (6 modules)

| Module | Purpose |
|---|---|
| `backtest.py` | Backtest request/response validation (capital: 1K-10M, max 5yr) |
| `ml_models.py` | ML model types (6), statuses (5), training config |
| `risk.py` | Risk status/violation/severity enums + request models |
| `order_integrity.py` | Order FSM, audit log, idempotency, 5 Prometheus metrics |
| `ensemble_model.py` | LSTM+XGBoost+RF combination with graceful degradation |
| `user.py` | Minimal user model (test compatibility shim) |

### config/ (5 modules)

| Module | Purpose |
|---|---|
| `base_settings.py` | Pydantic V2 BaseSettings with nested config sections + .env loading |
| `settings.py` | Active settings API (LRU-cached singleton, dual dataclass/pydantic) |
| `config.py` | DEPRECATED — use `settings.get_settings()` |
| `coordinator.py` | DEPRECATED — use `settings.get_settings()` |
| `unified.py` | DEPRECATED — use `settings.get_settings()` |

### data/ (5 modules)

| Module | Purpose |
|---|---|
| `alpaca_client.py` | Alpaca API client with observability (tracing, metrics, latency) |
| `market_data.py` | Resilient OHLCV processing with error handling |
| `models.py` | Pydantic data models for financial data structures |
| `social_sentiment.py` | Social sentiment analysis (Twitter/Reddit + FinBERT), dev fallbacks |
| `strategy_templates.py` | Strategy parameter templates for wizard builder |

### utils/ (9 modules)

| Module | Purpose |
|---|---|
| `helpers.py` | Math functions, financial calculations, UUID generation, hashing |
| `import_tracker.py` | Centralized import error tracking with fallback management |
| `logger.py` | Logger stub class for infrastructure compatibility |
| `logging.py` | Structured logging with PII/secret scrubbing (API keys, tokens, passwords) |
| `port_management.py` | Dynamic port allocation for tests (avoid conflicts) |
| `secure_pickle.py` | HMAC-SHA256 signed pickle serialization (prevents code execution attacks) |
| `market_hours.py` | **Single source of truth**: NYSE open/close, holidays, early closes, extended hours, slippage multipliers (used by 8+ modules). Key times: MARKET_OPEN=9:30, MARKET_CLOSE=16:00, EARLY_CLOSE=13:00, EXTENDED_OPEN=4:00, EXTENDED_CLOSE=20:00, TICK_START=9:28, TICK_STOP=16:01, PRE_OPEN=9:25, POST_CLOSE=16:05. Slippage time multipliers: pre_market=2.0x (4:00-9:30), open_auction=1.5x (9:30-10:00), morning=0.9x (10:00-11:30), midday=1.0x (11:30-14:00), afternoon=0.95x (14:00-15:30), close_auction=1.3x (15:30-16:00), after_hours=2.5x (16:00-20:00). Covers all 10 NYSE holidays + 3 early close days (Jul 3, Black Friday, Dec 24). |
| `utilities.py` | async_retry with exponential backoff/jitter, timezone helpers |
| `validators.py` | Validation stubs: ValidationError, Validator base, field validators |

### risk/ (12 modules)

| Module | Purpose |
|---|---|
| `risk_manager.py` | AsyncRiskManager: VaR, CVaR, Kelly, EWMA vol, position/sector limits, daily loss limits |
| `advanced_risk.py` | Advanced risk calculations |
| `advanced_risk_manager.py` | Extended risk manager with additional controls |
| `black_swan_protection.py` | Tail risk protection mechanisms |
| `correlation_breakdown.py` | Correlation regime change detection |
| `margin_calculator.py` | Margin requirement calculations |
| `math.py` | Risk math utilities (Kelly, EWMA, VaR z-scores) |
| `metrics.py` | Risk-specific Prometheus metrics |
| `position_limits.py` | Per-symbol (15%), per-sector (30%), portfolio (50%) limits |
| `risk_calculator.py` | Risk computation engine |
| `types.py` | OrderSpec, PortfolioState, RiskDecision, RiskLimits, RiskReasonCode, RiskLevel enums |
| `volatility_checker.py` | Volatility-based risk gating |

### monitoring/ (7 modules)

| Module | Purpose |
|---|---|
| `enhanced_slo_manager.py` | Enhanced SLO management with alerting |
| `memory_monitor.py` | Memory usage monitoring and alerting |
| `per_route_sli.py` | Per-route service level indicators |
| `slo_alerts.py` | SLO violation alerting |
| `slo_dashboard.py` | SLO dashboard data aggregation |
| `slo_metrics.py` | SLO metric collection |
| `slo_monitor.py` | SLO monitoring and compliance tracking |

---

---

## F. FULL API ROUTE REFERENCE

### Authentication (`/api/v1/auth/`)

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/login` | Username/password login → JWT |
| POST | `/token` | Token-based auth |
| GET | `/verify` | Verify token validity |
| POST | `/token/validate` | Validate token |
| POST | `/logout` | Blacklist token |
| GET | `/me` | Current user profile |
| POST | `/register` | Create account |
| POST | `/token/refresh` | Refresh JWT |
| POST | `/password-reset/request` | Request password reset |
| POST | `/password-reset/confirm` | Confirm password reset |
| POST | `/password-change` | Change password |

### Orders (`/api/v1/orders/`)

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/` | List orders (includes system orders) |
| POST | `/` | Place single order |
| POST | `/bulk` | Place bulk orders |
| GET | `/{order_id}` | Get order details |
| GET | `/{order_id}/status` | Get order status |
| PATCH | `/{order_id}` | Modify order |
| DELETE | `/{order_id}` | Cancel order |
| POST | `/{order_id}/cancel` | Cancel order (alternative) |
| GET | `/{order_id}/audit` | Order audit trail |
| POST | `/{order_id}/close-position` | Close position via order |

### Risk (`/api/v1/risk/`)

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/dashboard` | Full risk dashboard |
| GET | `/metrics` | Current risk metrics |
| POST | `/metrics/calculate` | Recalculate metrics |
| GET | `/violations` | Risk violations list |
| GET | `/limits` | Risk limit definitions |
| PUT | `/limits/{limit_name}` | Update risk limit |
| DELETE | `/limits/{limit_id}` | Remove risk limit |
| POST | `/emergency-stop` | Trigger emergency stop |
| POST | `/emergency-stop/{id}/resolve` | Resolve emergency stop |
| GET | `/emergency-stop/active` | Active emergency stops |

### Strategies (`/api/v1/strategies/`)

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/templates` | Available strategy templates |
| GET | `/templates/{type}` | Template by type |
| GET | `/status` | All strategy statuses |
| GET | `/` | List strategies |
| GET | `/{id}` | Get strategy |
| POST | `/` | Create strategy |
| PATCH | `/{id}` | Update strategy |
| DELETE | `/{id}` | Delete strategy |
| POST | `/{id}/start` | Start strategy |
| POST | `/{id}/stop` | Stop strategy |
| POST | `/{id}/pause` | Pause strategy |
| GET | `/{id}/performance` | Strategy performance |
| PUT | `/{id}/performance` | Update performance metrics |
| POST | `/features/ingest` | Ingest features |
| POST | `/signals/batch` | Batch signal submission |
| POST | `/signals/submit` | Submit signals |

### ML Models (`/api/v1/models/`)

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/` | List models |
| GET | `/stats` | Model statistics |
| GET | `/{id}` | Get model |
| DELETE | `/{id}` | Delete model |
| POST | `/{id}/activate` | Activate model |
| POST | `/train` | Train new model |
| GET | `/training/{id}` | Training job status |
| POST | `/predict` | Generate prediction |
| GET | `/{id}/features` | Model features |
| POST | `/compare` | Compare models |
| GET | `/{id}/health` | Model health |
| GET | `/{id}/monitor/snapshots` | Monitoring snapshots |
| POST | `/{id}/monitor/run` | Run monitoring |
| POST | `/{id}/retrain-if-needed` | Conditional retrain |
| GET | `/lifecycle/summary` | Lifecycle summary |
| POST | `/lifecycle/run/daily-monitoring` | Daily monitoring |
| POST | `/lifecycle/run/weekly-retrain` | Weekly retrain |
| POST | `/lifecycle/run/monthly-review` | Monthly review |
| GET | `/{name}/versions` | Model versions |
| GET | `/admin/training-jobs` | All training jobs |
| POST | `/admin/cleanup-jobs` | Clean old jobs |

### Scanner (`/api/v1/scanner/`)

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/scan` | Run market scan |
| GET | `/presets` | Built-in presets |
| POST | `/export/csv` | Export scan as CSV |
| POST | `/export/json` | Export scan as JSON |
| GET | `/presets/custom` | Custom presets |
| POST | `/presets/custom` | Create custom preset |
| PUT | `/presets/custom/{id}` | Update preset |
| DELETE | `/presets/custom/{id}` | Delete preset |
| GET | `/symbols` | Scannable symbols |
| WS | `/ws` | Scanner WebSocket stream |

### Watchlists (`/api/v1/watchlists/`)

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/` | List watchlists |
| POST | `/` | Create watchlist |
| GET | `/{id}` | Get watchlist |
| PUT | `/{id}` | Update watchlist |
| DELETE | `/{id}` | Delete watchlist |
| POST | `/{id}/symbols` | Add symbols |
| DELETE | `/{id}/symbols/{sym}` | Remove symbol |
| PUT | `/{id}/symbols/reorder` | Reorder symbols |
| GET | `/{id}/quotes` | Quotes for watchlist symbols |

### Other Routes (summarized)

| Route File | Endpoints | Key Operations |
|---|---|---|
| `observability.py` | 8 | Health (live/ready), metrics, trading, dashboard, alerts, thresholds |
| `system.py` | 8 | System status, metrics, health, SLI, test endpoint |
| `settings.py` | 7 | Organism/trading/ML settings CRUD, engine restart |
| `audit.py` | 6 | Compliance audit trail queries |
| `chart_templates.py` | 6 | Chart template CRUD + apply |
| `drawings.py` | 5 | TradingView-style drawings CRUD |
| `signals.py` | 5 | Signal storage, retrieval, act on signal |
| `backtest.py` | 5 | Create, list, results, delete |
| `positions.py` | 4 | List, import preview, import, close |
| `market_data.py` | 4 | Stats, health, bars, WebSocket |
| `lots.py` | 4 | Open lots, realized trades, cost basis, unrealized PnL |
| `admin_trading.py` | 3 | Execution mode GET/PUT/DELETE |
| `position_import.py` | 3 | Preview, import, clear |
| `trades.py` | 3 | Trade history retrieval |
| `optimizations.py` | 3 | Strategy optimization runs |
| `indicators.py` | 2 | Calculate indicator, list available |
| `auto_breakout_scanner.py` | 2 | Latest scan, manual trigger |
| `monitoring.py` | 2 | SLI metrics, SLO status |
| `multi_strategy_live.py` | 1 | Manual run-once trigger |

---

## G. ORM MODELS & CONFIGURATION

### Order Integrity FSM

**Source**: `backend/models/order_integrity.py`

```
Order State Machine (16 states):
  PENDING_VALIDATION → VALIDATED → PENDING_RISK_ASSESSMENT → RISK_APPROVED
    → PENDING_SUBMISSION → SUBMITTED → PENDING_EXECUTION → PARTIALLY_FILLED → FILLED
  Branch states: RISK_REJECTED, REJECTED, CANCELLED, EXPIRED, FAILED
  Recovery: PENDING_RETRY, UNDER_REVIEW

  (Simplified view: pending → submitted → accepted → filled / rejected / cancelled / expired)

Append-only audit log for traceability
Idempotency at 3 layers: API, service, outbox

Prometheus Metrics (all prefixed with `trading_`):
  - trading_order_state_transitions_total [from_state, to_state, trigger]
  - trading_order_integrity_violations_total [type]
  - trading_audit_log_entries_total [event_type, entity_type]
  - trading_idempotency_cache_hits_total [layer: api|service|outbox]
  - trading_order_processing_duration_seconds [state, operation]
    buckets: [0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
```

### Configuration Architecture

```
Settings Hierarchy:
  │
  ├── backend/config/base_settings.py  ← Pydantic V2 BaseSettings
  │     Nested sections: AppConfig, DatabaseConfig, DataConfig,
  │     MetricsConfig, AlpacaConfig
  │     .env file loading via python-dotenv
  │
  ├── backend/config/settings.py  ← Active API (get_settings())
  │     LRU-cached singleton pattern
  │     Dual dataclass + pydantic implementation
  │     Re-exports all config classes for backward compat
  │
  └── DEPRECATED:
      ├── config/config.py       → use settings.get_settings()
      ├── config/coordinator.py  → use settings.get_settings()
      └── config/unified.py      → use settings.get_settings()

Environment Variables:
  .env file (gitignored) → loaded by base_settings.py
  docker-compose.yml → overrides for container environment
  Organism vars MUST be in docker-compose.yml (not just .env)
```

### ML Model Types

```
ModelType (enum):
  ENSEMBLE | LSTM | XGBOOST | RANDOM_FOREST | REGRESSION | CLASSIFICATION

ModelStatus (enum):
  TRAINING | READY | FAILED | INACTIVE | DEPRECATED

TrainingStatus (enum):
  PENDING | RUNNING | COMPLETED | FAILED | CANCELLED

Default training config:
  features: ["technical", "sentiment"]
  symbols: ["AAPL", "MSFT", "GOOGL"]
  lookback_days: 90 (range: 30-365)
  test_size: 0.2 (range: 0.1-0.4)
```

---

*This document covers 100% of the platform's Python modules across organism/ (37), infra/ (24), integrations/ (6), api/ (15+), services/ (27), ml/ (17), models/ (6), config/ (5), data/ (5), utils/ (9), risk/ (12), and monitoring/ (7). Every threshold, every flow, every decision path, every endpoint, and every inter-module dependency is documented for visual diagramming.*
