# MASTER PLATFORM TAKEOVER — Claude Code Execution Prompt

> **Date:** February 16, 2026  
> **Platform:** Institutional-Grade Algorithmic Trading Platform with Living Organism AI  
> **Stack:** Python 3.11 (FastAPI/SQLAlchemy/XGBoost) + React 19 (TypeScript/Vite/Ant Design)  
> **Broker:** Alpaca (Paper Trading, production-ready)  
> **Database:** PostgreSQL + Redis  
> **Root:** `c:\Users\Marsel\intra\algotrading_platform`

---

## ⚠️ POST-EXECUTION VERIFICATION — UNFINISHED WORK (February 16, 2026)

> **Verified by:** GitHub Copilot (Claude Opus 4.6) — independent audit of Claude Code's execution  
> **Method:** Phase-by-phase verification of every item in this prompt against actual codebase state  
> **Scope:** Read every file referenced, ran test suites, checked line counts, confirmed file existence

### What Was Completed Successfully

Claude Code executed the first run of this prompt and completed the following correctly:

- **Phase 1 (Docs Consolidation):** `docs/PLATFORM_STATUS.md` created. `docs/archive/` with 3 subdirectories (`audits/`, `historical/`, `superseded/`) containing 36+ archived files. Top-level `docs/` is clean.
- **Phase 2 (Backend — partial):** Config consolidated — 4 deprecated stubs (`coordinator.py`, `unified.py`, `config.py`, `config_helpers.py`) all emit `DeprecationWarning` and redirect to canonical `backend.config.settings.get_settings()`. 8 missing `__init__.py` files added (`risk/`, `data/`, `features/`, `monitoring/`, `optimization/`, `security/`, `deployment/`, `brokers/`). `dev_testing_routes.py` removed from factory. Audit/lots/observability routes newly mounted.
- **Phase 3 (Frontend):** `npx tsc --noEmit` = 0 errors. 5 empty directories deleted.
- **Phase 4 (Security):** `pickle.load` secured (only via `secure_pickle`). No `eval`/`exec` in production code. All 9 organism control endpoints have `Depends(require_admin)`. No hardcoded secrets.
- **Phase 5 (Integration):** WebSocket event `emergency_stop_event` confirmed aligned between `backend/risk/risk_manager.py` and `frontend/src/features/risk/RiskDashboard.tsx`.
- **Test results:** Unit tests: 567 passed, 0 failed. Full suite: 1,414 passed, 196 skipped, 1 flaky failure (passes in isolation).

### What Was NOT Completed — Claude Code Must Finish These 10 Items

**Claude Code: The items below were NOT done during your first execution of this prompt. You must check each one and complete it now. For each item, confirm completion or explain why it was skipped.**

#### Item 1 — `scripts/smoke_test_live.py` NOT created
- **Prompt reference:** Phase 6, Section 6.2
- **Requirement:** Create a Python script that hits health, auth, portfolio, organism status, organism runs, strategies, and WebSocket endpoints, and prints a PASS/FAIL summary.
- **Current state:** File does not exist.

#### Item 2 — `scripts/trading_verification.py` NOT created
- **Prompt reference:** Phase 6, Section 6.3
- **Requirement:** Create a Python script that verifies Alpaca connectivity, portfolio sync, organism tick recency, shadow order pipeline, and risk limit enforcement. Prints PASS/FAIL.
- **Current state:** File does not exist.

#### Item 3 — `docs/testing/TEST_STRATEGY.md` NOT created
- **Prompt reference:** Phase 1, Section 1.2 (target structure) and Phase 6
- **Requirement:** Create `docs/testing/` directory and `TEST_STRATEGY.md` consolidating the test plan and run procedures from prior audit docs.
- **Current state:** Directory `docs/testing/` does not exist.

#### Item 4 — `docs/architecture/SYSTEM_OVERVIEW.md` NOT created
- **Prompt reference:** Phase 1, Section 1.2 (target structure) and Section 1.3, Step 6
- **Requirement:** Create a unified architecture overview merging key findings from BACKEND.md and current architecture understanding.
- **Current state:** File does not exist.

#### Item 5 — `docs/setup/QUICK_START.md` NOT rewritten
- **Prompt reference:** Phase 1, Section 1.2 and Section 1.3, Step 7
- **Requirement:** Rewrite as an actual getting-started guide (prerequisites, clone, install, configure .env, start services, verify).
- **Current state:** File still contains an October 2025 session-specific fix log. It is NOT a getting-started guide.

#### Item 6 — `docs/README.md` NOT updated
- **Prompt reference:** Phase 1, Section 1.2 and Section 1.3, Step 9
- **Requirement:** Update `docs/README.md` to reflect the new docs structure, reference `archive/`, and point to `PLATFORM_STATUS.md` as the living status tracker.
- **Current state:** No mention of `archive/` or `PLATFORM_STATUS.md` in the file.

#### Item 7 — `docs/front_backend/INTEGRATION_AUDIT.md` NOT archived
- **Prompt reference:** Phase 1, general archival directive
- **Requirement:** Move to `docs/archive/historical/` (it's a session-specific audit document, not an active reference).
- **Current state:** Still in `docs/front_backend/`.

#### Item 8 — `backend/api/factory.py` still 1,130 lines (target: <500)
- **Prompt reference:** Phase 7, Section 7.3
- **Requirement:** Extract organism scheduler setup into `backend/organism/scheduler_setup.py`, extract route registration into a dedicated function, extract middleware setup into a dedicated function. Keep `factory.py` under 500 lines.
- **Current state:** 1,130 lines. Was reduced from 1,468 but did not reach the <500 target. The major extractions (scheduler, routes, middleware) were not done.

#### Item 9 — Test runner has 2 tiers, not the specified 3 tiers
- **Prompt reference:** Phase 6, Section 6.1
- **Requirement:** `run_all_tests_and_report.ps1` should support three tiers: Tier 1 Smoke (<30s, `-m unit`), Tier 2 Integration (<5min, `-m "unit or api or services"`), Tier 3 Full (<30min, full suite with coverage).
- **Current state:** Script supports 2 tiers (Fast/Full) via a `-Fast` flag. No Smoke tier, no Integration tier as distinct runnable modes.

#### Item 10 — 1 flaky test: `test_order_lifecycle.py::test_order_via_orders_endpoint`
- **Prompt reference:** Phase 8 — all tests must pass
- **Requirement:** Full test suite should have 0 failures.
- **Current state:** This test fails when run in the full suite but passes in isolation. This is a test isolation issue (likely shared DB state or fixture leakage). Needs investigation and fix.

### Execution Instructions

1. Work through Items 1–10 above in order.
2. After each item, confirm it is done by checking the file exists / line count / test passes.
3. Update `docs/PLATFORM_STATUS.md` with any changes made.
4. When all 10 items are done, re-run the Definition of Done checklist at the bottom of this prompt and confirm every box is checked.

---

## MISSION

You are taking over this entire platform. Your job is to understand EVERYTHING, consolidate the scattered documentation debt, verify every system works end-to-end, fix what's broken, wire what's disconnected, and deliver a unified, seamlessly operating trading platform.

This is NOT an audit that produces another report. This is an EXECUTION mission. You read, you understand, you fix, you verify, you move on. No new audit docs — only a single living status tracker and working code.

---

## PHASE 0 — ORIENTATION (Read-Only, Do NOT Write Code Yet)

### 0.1 Understand the Documentation Landscape

The `docs/` folder has **65+ files** accumulated across 5+ audit/fix sessions since January 2026. Many are redundant, outdated, or superseded. Here is the canonical status:

**AUTHORITATIVE (keep and reference):**
- `docs/blueprints/EVOLVING_ORGANISM_BLUEPRINT.md` — THE master blueprint. Single source of truth for the Living Organism architecture. Supersedes SELF_LEARNING, BREAKOUT_ALPHA, and LIVING_STRATEGY blueprints.
- `docs/blueprints/FULL_LIVING_TRADING_ORGANISM_BLUEPRINT_AND_EXECUTION_PLAN.md` — Strategic roadmap and philosophy
- `docs/COMPREHENSIVE_AUDIT_AND_EXECUTION_PLAN.md` — Master issue tracker (103/105 fixed)
- `docs/architecture/SIGNAL_AGGREGATION.md` — Core design decision (keep)
- `docs/architecture/WEBSOCKET_GUIDE.md` — WebSocket implementation reference
- `docs/operations/PAPER_TRADING_ROLLOUT.md` — Active rollout guide
- `docs/setup/ENVIRONMENT.md` — Env var reference
- `docs/setup/DATABASE.md` — DB setup
- `docs/setup/AUTHENTICATION.md` — Auth system
- `docs/API_RATE_LIMITS.md` — Rate limiting policies
- All `docs/runbooks/*` — Operational runbooks (keep as templates)

**SUPERSEDED/OUTDATED (candidates for archival or deletion):**
- `docs/blueprints/SELF_LEARNING_ORGANISM_BLUEPRINT.md` — superseded by EVOLVING_ORGANISM_BLUEPRINT
- `docs/blueprints/BREAKOUT_ALPHA_BLUEPRINT.md` — superseded (modules built into organism)
- `docs/blueprints/LIVING_STRATEGY_SYSTEM_PLAN.md` — superseded
- `docs/PART2_TRADING_LOGIC_AUDIT.md` — earlier draft, superseded by FINAL_AUDIT_PART2
- `docs/PROJECT_REORGANIZATION_PLAN.md` — completed, superseded by REORGANIZATION_COMPLETE
- `docs/setup/QUICK_START.md` — misnomer, it's an Oct 2025 session-specific fix log, not a getting-started guide
- `docs/architecture/WEBSOCKET_FIX_SUMMARY.md` — historical post-mortem (Oct 2025 bug, fixed)
- `docs/architecture/IMPLEMENTATION_PLAN.md` — partially outdated frontend roadmap from Oct 2025

**AUDIT DOCUMENTS (valuable findings but tracking is scattered):**
- 20 files in `docs/audits/` — multiple overlapping audit reports and prompts
- Key finding trajectory: C-/NO-GO (Jan 18) → B+ (Jan 20) → A-/GO (Jan 23) → Current
- Most critical unfixed items from audits:
  1. Organism control endpoints lack admin-only role scoping (SERVICES_API_DEEP_AUDIT)
  2. Idempotency key collision risk (second-level timestamp, needs UUID)
  3. Config consolidation (6 config systems → should be 1)
  4. Database module consolidation (3 DB layers → should be 1)
  5. Two parallel Alembic migration chains (no shared lineage)

### 0.2 Understand the Codebase Architecture

**Backend (~190 Python files across 25 packages):**

| Package | Files | Purpose | Health |
|---------|-------|---------|--------|
| `backend/organism/` | 27 | Living Trading Organism — brain, governance, training, evolution | ACTIVE — ticking every 60s |
| `backend/services/` | 28 | Business logic — orders, portfolio, risk, positions, signals, trades | Mixed — some wired, some stubs |
| `backend/api/` | 30+ | FastAPI routes, middleware, schemas, auth, factory | ACTIVE — factory.py is 1468 lines |
| `backend/strategies/` | 9 | 12 trading strategies (6 core + 6 advanced), engine, living policy | ACTIVE |
| `backend/ml/` | 18 | ML pipeline, model management, training, prediction, drift detection | ACTIVE |
| `backend/risk/` | 12 | Risk calculation, VaR/CVaR, position limits, Black Swan, margin | Partially wired |
| `backend/integrations/` | 7 | Alpaca broker, data, streaming, outbox | ACTIVE |
| `backend/data/` | 5 | Alpaca client, market data, strategy templates | ACTIVE |
| `backend/infra/` | 25+ | DB, cache, logging, metrics, security, repositories, guardrails | ACTIVE |
| `backend/models/` | 7 | SQLAlchemy ORM models | ACTIVE |
| `backend/features/` | 5 | Feature engineering, technical indicators, alignment | ACTIVE |
| `backend/monitoring/` | 7 | SLO metrics, memory monitor, dashboards | Template-level |
| `backend/config/` | 6 | 6 config systems (KNOWN DEBT — should be consolidated) |  FRAGMENTED |
| `backend/database/` | 8 | 3 DB management systems (KNOWN DEBT — should be consolidated) | FRAGMENTED |
| `backend/mlops/` | 12 | MLOps pipeline, model serving, experiment tracking | Partially wired |
| `backend/security/` | 1 | API hardening | Minimal |
| `backend/utils/` | 9 | Logging, helpers, secure pickle, validators | ACTIVE |
| `backend/analytics/` | 3 | Order flow analytics, real-time risk | Minimal |
| `backend/optimization/` | 1 | Portfolio optimizer | Stub |
| `backend/observability/` | 3 | Metrics, tracing | ACTIVE |
| `backend/brokers/` | 2 | Alpaca production client, broker failover | Reference |
| `backend/deployment/` | 1 | Deployment validator | Minimal |
| `backend/migrations/` | 12 | Alembic migrations (2 parallel chains — KNOWN DEBT) | FRAGMENTED |
| `backend/research/` | 2 | Optuna meta-research engine | Experimental |

**Frontend (~120 TypeScript/TSX files):**

| Area | Key Files | Purpose | Health |
|------|-----------|---------|--------|
| `features/organism/` | OrganismDashboard, organismApi | Living Organism control panel | ACTIVE |
| `features/dashboard/` | Dashboard.tsx | Main dashboard | ACTIVE |
| `features/trading/` | TradingPage, OrderEntry, PreTradeChecks | Order execution | ACTIVE |
| `features/orders/` | OrdersPage, ActiveOrders, OrderHistory | Order management | ACTIVE |
| `features/positions/` | PositionsPage, PositionDetail, PositionStats | Position tracking | ACTIVE |
| `features/portfolio/` | PortfolioPage | Portfolio overview | ACTIVE |
| `features/strategies/` | StrategiesPage, StrategyBuilder, StrategyWizard | Strategy management | ACTIVE |
| `features/backtesting/` | BacktestingPage, BacktestForm, Results | Strategy backtesting | ACTIVE |
| `features/ml-models/` | MLModelsPage, ModelRegistry, TrainingForm | ML model management | ACTIVE |
| `features/risk/` | RiskDashboard, KillSwitchButton, RiskLimits | Risk management UI | ACTIVE |
| `features/trades/` | TradesPage, InstitutionalMetrics, TradeDetail | Trade history/analytics | ACTIVE |
| `features/auth/` | LoginPage, RegisterPage | Authentication | ACTIVE |
| `features/admin/` | (empty) | Admin panel | NOT BUILT |
| `features/market-data/` | (empty) | Market data feature | NOT BUILT |
| `components/market/` | ChartContainer, QuotePanel, Scanner, Watchlist | Market data display | ACTIVE |
| `components/layout/` | AppHeader, AppSidebar, GlobalStatusBar, MainLayout | App shell | ACTIVE |
| `services/` | 14 API service files | Backend communication | ACTIVE |
| `stores/` | 6 Zustand stores | State management | ACTIVE |
| `hooks/` | 14 custom hooks | WebSocket, auth, charts, data | ACTIVE |

**Tests (~114 test files in tests/ root + 533 in subdirectories):**
- Last known state: ~55% coverage, Phases 1-6 of 8-phase coverage plan complete
- Phases 7 (Services) and 8 (Remaining) NOT STARTED

### 0.3 Understand the Current Runtime State

As of February 16, 2026 17:27 UTC:
- **Server**: Running `python main.py` on localhost:8000
- **Frontend**: Running `npm run dev` on localhost:5173
- **Living Organism**: ACTIVE — ticks every 60s
  - Data fetching: ✅ All symbols returning 200 OK from Alpaca
  - Feature engineering: ✅ 461 rows, 95 features per symbol
  - Regime detection: ✅ `trending_up` detected
  - Drawdown governance: ✅ Fixed (was false-triggering at 100% due to missing TradingClient)
  - Signal generation: 0 signals (no promoted ML model yet — training produces candidates but Sharpe < 0.3 threshold)
  - Exit checking: ✅ 2 exits checked (AAPL, SPY positions)
- **Portfolio**: Alpaca paper account — $112,695.98 equity, $109,456.20 cash, 2 positions (AAPL: 10 shares, SPY: 1 share)
- **API**: All organism endpoints returning 200 OK, portfolio returning real Alpaca data
- **WebSocket**: Socket.IO active, emitting `organism_tick` events to connected clients

**Known bugs fixed in the last session (Feb 16):**
1. Async/sync mismatch — `AlpacaDataClient` methods are async but were wrapped in `asyncio.to_thread()` (for sync functions). Fixed with `asyncio.iscoroutinefunction()` dispatch.
2. DataFrame length mismatch — Feature engineering produces 461 rows from 480 raw bars (19 warm-up rows dropped), but merge paths had misaligned indices. Fixed with `reset_index(drop=True)` + min-length merge + tail-aligned OHLCV.
3. Missing `model_lifecycle_events` table — Created via SQL script.
4. Admin account locked — Failed login attempts during testing locked account. Unlocked via script.
5. PositionsService had no TradingClient — Factory created `PositionsService()` with no broker connection, so equity always returned 0, triggering 100% false drawdown. Fixed by creating `TradingClient` with Alpaca credentials.
6. Drawdown cold-start — When equity = 0, drawdown formula `(peak - 0) / peak = 100%` always triggers kill switch. Added guard to skip drawdown check when equity = 0.

---

## PHASE 1 — DOCUMENTATION CONSOLIDATION

**Goal:** Replace 65+ scattered docs with a clean, workable structure that we actually use.

### 1.1 Create Single Living Status Tracker

Create `docs/PLATFORM_STATUS.md` — THE one document that tracks the state of everything:

```
# Platform Status — Living Document
## Last Updated: [date]

### System Health
- [ ] Backend Server: [status]
- [ ] Frontend: [status]  
- [ ] Living Organism: [status]
- [ ] Database: [status]
- [ ] Redis: [status]
- [ ] Alpaca Connection: [status]

### Component Status Matrix
| Component | Status | Coverage | Last Verified | Known Issues |
|-----------|--------|----------|---------------|--------------|
| ... | ... | ... | ... | ... |

### Open Issues (Priority Order)
1. ...

### Recently Completed
1. ...
```

### 1.2 Consolidate Docs Structure

Target structure:
```
docs/
├── PLATFORM_STATUS.md          ← NEW: Single living tracker
├── README.md                   ← UPDATE: Clean index pointing to new structure
├── architecture/
│   ├── SYSTEM_OVERVIEW.md      ← NEW: Unified architecture doc  
│   ├── SIGNAL_AGGREGATION.md   ← KEEP
│   ├── WEBSOCKET_GUIDE.md      ← KEEP
│   └── TRADING_ALGORITHMS.md   ← KEEP (refresh if needed)
├── blueprints/
│   ├── EVOLVING_ORGANISM_BLUEPRINT.md  ← KEEP (authoritative)
│   └── STRATEGIC_ROADMAP.md    ← MERGE: from FULL_LIVING + current state
├── operations/
│   ├── PAPER_TRADING_ROLLOUT.md ← KEEP
│   ├── OPERATIONAL_CADENCE.md   ← KEEP
│   └── POST_LAUNCH_MONITORING.md ← KEEP
├── runbooks/                    ← KEEP ALL (6 files, they're templates)
├── setup/
│   ├── QUICK_START.md           ← REWRITE: Actual getting-started guide
│   ├── ENVIRONMENT.md           ← KEEP
│   ├── DATABASE.md              ← KEEP
│   ├── AUTHENTICATION.md        ← KEEP
│   └── TLS_SETUP_GUIDE.md      ← KEEP
├── testing/
│   └── TEST_STRATEGY.md        ← NEW: Consolidated test plan + run procedures
└── archive/                     ← NEW: Move all outdated/superseded docs here
    ├── audits/                  ← Move all 20 audit docs (findings are tracked in STATUS)
    ├── superseded_blueprints/   ← Move 3 superseded blueprints
    └── historical/              ← Move session logs, resolution plans, etc.
```

### 1.3 Implementation Steps for Docs Consolidation

1. Create `docs/archive/`, `docs/archive/audits/`, `docs/archive/superseded_blueprints/`, `docs/archive/historical/`
2. Move superseded files to archive (see list in 0.1 above)
3. Move ALL `docs/audits/*` files to `docs/archive/audits/` 
4. Move session-specific docs (`SESSION3_AUDIT_AND_FIXES.md`, `AUDIT_SESSION2_EXECUTION_PLAN.md`, etc.) to `docs/archive/historical/`
5. Create `docs/PLATFORM_STATUS.md` with current state from Phase 0 findings
6. Create `docs/architecture/SYSTEM_OVERVIEW.md` merging key findings from BACKEND.md + current architecture understanding
7. Rewrite `docs/setup/QUICK_START.md` as an actual getting-started guide
8. Create `docs/testing/TEST_STRATEGY.md` consolidating from TESTING.md and TEST_COVERAGE_100_PLAN.md
9. Update `docs/README.md` to reflect new structure

**IMPORTANT:** Do not delete any files. Move them to archive. Git history preserves everything.

---

## PHASE 2 — BACKEND SYSTEMS VERIFICATION & FIX

Go through each backend system. For each: read the code, verify it works, fix what's broken, document the status.

### 2.1 Core Infrastructure

**Config System (KNOWN DEBT — 6 systems):**
- `backend/config.py` — root config
- `backend/settings.py` — settings
- `backend/config_helpers.py` — helpers
- `backend/config/base_settings.py` — base settings
- `backend/config/config.py` — config module
- `backend/config/settings.py` — another settings
- `backend/config/unified.py` — unified config
- `backend/config/coordinator.py` — config coordinator
- **ACTION:** Audit which config paths are actually used at runtime. Consolidate into ONE canonical config module. All other files should import from it or be deleted.

**Database System (KNOWN DEBT — 3 layers):**
- `backend/database.py` — root DB
- `backend/database/connection.py` — connection module
- `backend/database/database_config.py` — DB config  
- `backend/database/models.py` — DB models
- `backend/database/models_production.py` — production models
- `backend/database/unified_config.py` — unified DB config
- `backend/database/production.py` — production DB
- `backend/database/optimization.py` — DB optimization
- `backend/infra/db.py` — infra DB layer
- `backend/infra/unified_database.py` — unified database
- **ACTION:** Trace all `create_engine` / `sessionmaker` calls. Identify the ONE true database session used at runtime. Consolidate. Ensure Alembic uses the same engine.

**Alembic Migrations (KNOWN DEBT — 2 parallel chains):**
- `backend/migrations/versions/` has migrations from two different lineage chains
- Some reference tables from the other chain (broken FKs)
- **ACTION:** Audit the migration chain. Merge into single linear history if possible, or at minimum verify all tables exist and FKs resolve.

### 2.2 Trading Engine

**Strategy Engine (`backend/strategies/`):**
- 12 strategies: 6 core (MeanReversion, Momentum, Ensemble, StatArb, Rebalancing, + basic) + 6 advanced (SqueezeBreakout, FailedBreakoutReversal, MultiTimeframeBreakout, AdaptiveRegimeMomentum, OrderFlowImbalance, CrossSectionalMomentum)
- `engine.py` — StrategyManager with signal netting, whipsaw prevention
- `living_policy.py` — Adaptive weights from organism learning
- **ACTION:** Verify all 12 strategies produce valid signals. Run each strategy against recent data and confirm no crashes, no NaN/Inf, and signals are well-formed.

**Order Pipeline (`backend/services/order_service.py` → `backend/infra/outbox.py`):**
- Order flow: OrderService → validation → risk checks → outbox → broker submission
- Shadow mode support (`TRADING_EXECUTION_MODE=shadow`)
- **ACTION:** Trace the full order lifecycle from signal → order creation → risk check → outbox → broker submit → fill tracking. Verify each step works. Test with a shadow order.

**Risk Management:**
- `backend/services/risk_manager.py` — Service-level risk
- `backend/risk/risk_manager.py` — Core risk calculations
- `backend/risk/advanced_risk_manager.py` — VaR/CVaR
- `backend/risk/position_limits.py` — Position sizing limits
- `backend/risk/black_swan_protection.py` — Tail risk
- `backend/organism/governance.py` — Organism governance (drawdown kill, cooldown)
- `backend/organism/kelly_sizer.py` — Kelly criterion sizing
- **ACTION:** Verify the risk chain: who calls what, does the governance controller actually block orders when halted, does Kelly sizing respect position limits, do risk checks use REAL portfolio data (not $100K fallback).

### 2.3 Living Organism

**Core Modules (`backend/organism/`):**
- `live_engine.py` — Main tick loop (fetches data → features → regime → positions → signals → exits → orders)
- `training.py` — Nightly/manual training orchestrator
- `scheduler.py` — APScheduler tick scheduling
- `governance.py` — Drawdown kill, halt controls
- `brain_persistence.py` — Atomic brain state save/load
- `ml_features.py` — Feature computation (95 features)
- `ml_signal.py` — ML signal generation
- `regime.py` — Market regime detection (trending_up/down, mean_reverting, volatile, crisis)
- `promotion.py` — Model promotion pipeline (gates: Sharpe, improvement, OOS)
- `self_evolution.py` — 7 adaptive parameter adjusters
- `continuous_learner.py` — Incremental learning
- `walk_forward.py` — Walk-forward validation
- `feature_store.py` — Feature caching
- `alpha_scanner.py` — Alpha opportunity scanning
- `breakout_scanner.py` — 6 breakout pattern detectors
- `adaptive_exits.py` — Dynamic exit engine
- `pyramider.py` — 3-layer position pyramiding
- `kelly_sizer.py` — Kelly criterion position sizing
- `multi_timeframe.py` — Multi-timeframe feature aggregation
- `universe_selector.py` — Dynamic symbol universe selection
- `transfer_learning.py` — Cross-strategy learning
- `attribution.py` — PnL attribution
- `routes.py` — Organism API endpoints
- **ACTION:** Verify each module is actually wired into the tick loop or training pipeline. Many modules may be DEFINED but never CALLED. Map the actual call graph from `live_tick()` and `run_training()`. Any disconnected modules need to be either wired in or clearly documented as "Phase 3/4 - not yet active".

**Critical Organism Questions to Answer:**
1. Does the training pipeline successfully produce a model? (Current: yes, but rejected — Sharpe 0.020 < 0.3 threshold)
2. What needs to happen for a model to be promoted? (Sharpe ≥ 0.3, improvement ≥ 5% over incumbent, OOS validation pass)
3. Once promoted, will the signal generator actually produce signals? Will orders flow?
4. Is the self-evolution loop actually running? (Contextual bandit, parameter adaptation)
5. Is attribution being computed and fed back to the learner?
6. Is the feature store actually caching and reusing features across ticks?

### 2.4 API Layer

**Factory (`backend/api/factory.py` — 1468 lines):**
- Creates the FastAPI app, mounts middleware, registers routes, manages lifespan
- KNOWN DEBT: Too large, should be split
- **ACTION:** Verify all routes are registered, all middleware is active, lifespan startup/shutdown works cleanly, and the organism scheduler starts properly.

**Routes (`backend/api/routes/` — 27 route files):**
- Verify each route file has working endpoints
- Check for mock data or stubs in production paths
- Verify auth requirements on each endpoint
- **SPECIFIC CHECK:** `dev_testing_routes.py` — should NOT be mounted in production

**Organism Endpoints (from `backend/organism/routes.py`):**
- `GET /organism/status` — Current organism state
- `GET /organism/runs` — Run history
- `GET /organism/brain` — Brain state
- `GET /organism/policy` — Living policy
- `GET /organism/attribution` — PnL attribution
- `POST /organism/freeze`, `/halt`, `/promote`, `/rollback` — Control endpoints
- **CRITICAL:** These control endpoints LACK admin-only role scoping (found in SERVICES_API_DEEP_AUDIT). Any authenticated user can halt the organism. FIX THIS.

### 2.5 Integrations

**Alpaca Integration:**
- `backend/integrations/alpaca_broker.py` — Broker operations
- `backend/integrations/alpaca_data.py` — Market data (AlpacaDataClient — ASYNC)
- `backend/data/alpaca_client.py` — Older client (AlpacaClient — SYNC)
- `backend/integrations/alpaca_stream.py` — WebSocket streaming
- `backend/integrations/alpaca_stream_production.py` — Production stream
- `backend/integrations/alpaca_outbox.py` — Outbox-based order submission
- **WARNING:** Two different Alpaca client types exist. `AlpacaDataClient` is async, `AlpacaClient` is sync. Code must use `asyncio.iscoroutinefunction()` to dispatch correctly. This was a critical bug fixed on Feb 16.
- **ACTION:** Verify all Alpaca integration points handle async/sync correctly. Verify the stream client connects and receives data. Verify outbox submission works.

### 2.6 ML Pipeline

**Training Flow:**
- `backend/organism/training.py` → `backend/ml/training.py` → `backend/ml/feature_engineering.py`
- `backend/ml/model_manager.py` — Model storage and loading
- `backend/ml/prediction_service.py` — Inference
- `backend/ml/validation.py` — Cross-validation, OOS testing
- `backend/ml/drift.py` — Distribution drift detection
- `backend/ml/staleness_detector.py` — Model freshness checking
- **ACTION:** Run a training cycle manually. Check if features are computed correctly, model trains without errors, validation metrics are real (not fake/mock), and the model is saved properly.

---

## PHASE 3 — FRONTEND VERIFICATION & FIX

### 3.1 Build Verification

```bash
cd frontend
npm run build
```
- Must exit 0 with zero TypeScript errors
- If there are errors, fix them

### 3.2 Page-by-Page Verification

For EACH page in the frontend, verify:
1. It renders without console errors
2. It connects to real backend API endpoints (not mock data)
3. It handles loading, empty, and error states properly
4. Data displayed matches what the backend returns

**Pages to verify:**
- Dashboard (`features/dashboard/Dashboard.tsx`)
- Organism Dashboard (`features/organism/OrganismDashboard.tsx`)
- Trading Page (`features/trading/TradingPage.tsx`)
- Orders Page (`features/orders/OrdersPage.tsx`)
- Positions Page (`features/positions/PositionsPage.tsx`)
- Portfolio Page (`features/portfolio/PortfolioPage.tsx`)
- Strategies Page (`features/strategies/StrategiesPage.tsx`)
- Strategy Builder (`features/strategies/StrategyBuilderPage.tsx`)
- Backtesting Page (`features/backtesting/BacktestingPage.tsx`)
- ML Models Page (`features/ml-models/pages/MLModelsPage.tsx`)
- Risk Dashboard (`features/risk/RiskDashboard.tsx`)
- Trades Page (`features/trades/TradesPage.tsx`)
- Scanner Page (`pages/ScannerPage.tsx`)
- Market Data Demo (`pages/MarketDataDemo.tsx`)

### 3.3 Empty Features

- `features/admin/` — EMPTY. Decide: build it or remove the route/nav entry.
- `features/market-data/` — EMPTY. Decide: build it or remove the route/nav entry.
- `components/atomic/`, `components/data-display/`, `components/financial/` — EMPTY directories. Delete them.

### 3.4 WebSocket Verification

- Socket.IO connection established on page load
- `organism_tick` events received and update the Organism Dashboard
- `portfolio` events received and update portfolio displays
- Reconnection works after connection drop
- No console errors related to WebSocket

### 3.5 UX Issues to Fix

- Empty states: When there's no data (e.g., no trades, no signals), show proper "No data yet" messages, not blank spaces or loading spinners
- Error handling: API 401/403/500 errors should show user-friendly messages
- Navigation: Sidebar should clearly indicate the current page. Dead links should be removed.
- Responsive: Basic mobile-responsive layout should work

---

## PHASE 4 — SECURITY HARDENING

### 4.1 Critical Security Items

1. **Organism control endpoints need admin-only access** — `POST /organism/freeze`, `/halt`, `/promote`, `/rollback` — add `@require_role("admin")` or equivalent
2. **dev_testing_routes.py** — Must not be mounted outside development. Check `factory.py` for how it's included.
3. **Environment variable secrets** — Verify `JWT_SECRET_KEY`, `ALPACA_API_KEY_ID`, `ALPACA_API_SECRET_KEY` are loaded from `.env` and never hardcoded
4. **Default credentials** — Search for hardcoded passwords, default admin credentials in source code (not just `.env.example`)
5. **SQL injection** — Verify all database queries use parameterized queries (SQLAlchemy ORM handles this, but check for raw SQL)
6. **Rate limiting** — Verify rate limiting middleware is active on sensitive endpoints (login, order submission)

### 4.2 Verification

Run these checks:
```bash
# Search for hardcoded secrets
grep -r "secret_key\s*=" backend/ --include="*.py" | grep -v ".env" | grep -v "os.getenv" | grep -v "test"
# Search for eval/exec
grep -rn "eval\|exec(" backend/ --include="*.py" | grep -v "#" | grep -v "test"
# Search for pickle.load without secure wrapper
grep -rn "pickle.load" backend/ --include="*.py" | grep -v "secure_pickle"
```

---

## PHASE 5 — INTEGRATION & SYNERGY

### 5.1 End-to-End Flow Verification

Test the complete flow:
1. **Login** → frontend auth → backend JWT → token stored → all subsequent requests authenticated
2. **Dashboard loads** → portfolio data from Alpaca → positions displayed → WebSocket connected → organism status shown
3. **Organism tick** → data fetched → features computed → regime detected → signals generated (when model exists) → orders submitted (when in execute mode) → portfolio updated → UI refreshed via WebSocket
4. **Strategy management** → create strategy → backtest → view results → enable for live trading
5. **Order flow** → order entry → pre-trade validation → risk check → order submitted → fill received → position updated → trade recorded → analytics updated
6. **Risk monitoring** → real-time portfolio metrics → drawdown tracking → kill switch button works → governance halts trading when triggered

### 5.2 API Contract Alignment

Verify frontend TypeScript types match backend Pydantic models for:
- Portfolio data (`/api/v1/portfolio/`)
- Orders (`/api/v1/orders/`)
- Positions (`/api/v1/positions/`)
- Strategies (`/api/v1/strategies/`)
- Organism status (`/api/v1/organism/status`)
- Risk metrics (`/api/v1/risk/`)
- ML models (`/api/v1/models/`)

For each endpoint:
1. Call the endpoint from the backend (curl or httpie)
2. Compare the response shape to the frontend TypeScript type
3. Fix any mismatches

### 5.3 WebSocket Event Alignment

Verify event names match between backend and frontend:
- Backend sends `organism_tick` → Frontend listens for `organism_tick`
- Backend sends `emergency_stop_triggered` → Frontend listens for... what? (Known mismatch: frontend may listen for `emergency_stop_event`)
- Backend sends portfolio updates → Frontend handles them
- Check ALL socket event names in both codebases and align them

---

## PHASE 6 — TESTING PROTOCOL

### 6.1 Create a One-Click Test Suite

Create/update `run_all_tests_and_report.ps1` to run three tiers:

**Tier 1 — Smoke Tests (< 30 seconds):**
```
pytest -x -q -m "unit" --maxfail=3 --tb=short
```
Must pass before any deployment.

**Tier 2 — Integration Tests (< 5 minutes):**
```
pytest -x -q -m "unit or api or services" --cov=backend --cov-branch --tb=short
```
Run before merging any PR.

**Tier 3 — Full Suite (< 30 minutes):**
```
pytest -v --cov=backend --cov-branch --cov-report=html:test_results --cov-report=term-missing:skip-covered
```
Nightly or on-demand.

### 6.2 Live Smoke Tests

Create `scripts/smoke_test_live.py` that:
1. Hits the health endpoint → 200 OK
2. Authenticates with admin credentials → JWT token
3. Calls `/portfolio/` → returns real Alpaca data
4. Calls `/organism/status` → returns current organism state
5. Calls `/organism/runs?limit=5` → returns recent tick history
6. Calls `/strategies/` → returns strategy list
7. Verifies WebSocket connects and receives a tick within 90 seconds
8. Prints PASS/FAIL summary

This is the "button you click" to verify the platform is working.

### 6.3 Trading-Specific Tests

Create `scripts/trading_verification.py` that:
1. Verifies Alpaca API connectivity (account data readable)
2. Verifies portfolio sync (equity > 0, positions match Alpaca)
3. Verifies organism is ticking (last tick < 120 seconds ago)
4. Verifies order pipeline (submit a shadow order → verify it's recorded)
5. Verifies risk limits are active (try to exceed position limit → blocked)
6. Prints PASS/FAIL with details

### 6.4 Frontend Build Test

The Vite build (`npm run build`) should be run and must produce zero errors:
```bash
cd frontend && npm run build 2>&1
```

---

## PHASE 7 — CLEANUP & POLISH

### 7.1 Dead Code Removal

Based on `docs/CLEANUP_PLAN.md` (which was never executed):
1. Delete empty directories: `features/admin/`, `features/market-data/`, `components/atomic/`, `components/data-display/`, `components/financial/`
2. Review `backend/` for unused files identified in previous audits
3. Check for `__init__.py` files missing in packages that need them (`backend/risk/`, `backend/data/`, `backend/features/`, `backend/monitoring/`, `backend/optimization/`, `backend/security/`, `backend/deployment/`)
4. Review `.gitignore` — ensure `organism_brain/`, `logs/`, `models/active_models/`, `reports/`, `test_results/` are properly ignored

### 7.2 Missing `__init__.py` Files

These packages have NO `__init__.py` — add them:
- `backend/risk/`
- `backend/data/`
- `backend/features/`
- `backend/monitoring/`
- `backend/optimization/`
- `backend/security/`
- `backend/deployment/`
- `backend/brokers/`

### 7.3 Factory.py Refactor

`backend/api/factory.py` is 1468 lines. At minimum:
1. Extract organism scheduler setup into `backend/organism/scheduler_setup.py`
2. Extract route registration into a dedicated function
3. Extract middleware setup into a dedicated function
4. Keep `factory.py` under 500 lines

---

## PHASE 8 — FINAL VERIFICATION

### 8.1 Full System Test

1. Stop all running processes
2. Start PostgreSQL and Redis (`docker-compose up -d db redis`)
3. Start backend (`python main.py`)
4. Start frontend (`cd frontend && npm run dev`)
5. Run `scripts/smoke_test_live.py` → ALL PASS
6. Run `scripts/trading_verification.py` → ALL PASS
7. Open browser at `localhost:5173` → login → verify all pages load with real data
8. Wait for one organism tick → verify it completes without errors
9. Run `pytest -x -q -m "unit" --maxfail=3` → ALL PASS
10. Run `cd frontend && npm run build` → EXIT 0

### 8.2 Update Status Document

Update `docs/PLATFORM_STATUS.md` with final state of every component.

---

## EXECUTION RULES

1. **Do not create new audit documents.** Update `docs/PLATFORM_STATUS.md` only.
2. **Fix issues as you find them.** Don't catalog them for later.
3. **Test after each fix.** Run relevant tests to verify.
4. **Commit after each phase.** Don't accumulate too many changes.
5. **If a fix would take > 30 minutes**, document it in PLATFORM_STATUS.md as "Known Issue" with severity and move on.
6. **Prioritize by impact:** Security > Data Integrity > Functionality > UX > Code Quality.
7. **The organism must keep ticking.** Don't break the live tick loop while fixing things.

---

## ENVIRONMENT SETUP

Before starting, verify:
```bash
# Backend
cd c:\Users\Marsel\intra\algotrading_platform
python -c "import backend; print('Backend imports OK')"
python -m pytest --co -q 2>&1 | tail -5  # Collect test count

# Frontend
cd frontend
npm run build 2>&1 | tail -5

# Services
docker-compose ps  # PostgreSQL and Redis should be running
```

**Key env vars (in `.env`):**
- `ALPACA_API_KEY_ID` / `ALPACA_API_SECRET_KEY` — Alpaca paper trading credentials
- `ALPACA_PAPER=true` — Paper trading mode
- `DATABASE_URL=postgresql+asyncpg://trading:trading_password@localhost:5432/algotrading`
- `JWT_SECRET_KEY` — Random secret for JWT signing
- `ORGANISM_ENABLED=1` — Living Organism enabled
- `ENABLE_ORGANISM_SCHEDULER=1` — Auto-tick scheduling enabled

---

## DEFINITION OF DONE

The platform is "done" when:

- [ ] `docs/` has < 25 active files (rest archived), with one living `PLATFORM_STATUS.md`
- [ ] Backend server starts cleanly with no warnings/errors in first 10 seconds
- [ ] Frontend builds with zero TypeScript errors
- [ ] All 14 frontend pages render with real data (no mock data, no console errors)
- [ ] Organism ticks every 60s without errors
- [ ] `smoke_test_live.py` passes all checks  
- [ ] `trading_verification.py` passes all checks
- [ ] Unit tests pass (`pytest -m unit` — 0 failures)
- [ ] Organism control endpoints require admin role
- [ ] No hardcoded secrets in source code
- [ ] WebSocket events are aligned between frontend and backend
- [ ] API response shapes match frontend TypeScript types
- [ ] Config is consolidated (< 3 config files in active use)
- [ ] Every backend package has `__init__.py`
- [ ] `factory.py` is < 500 lines  
- [ ] Empty frontend directories are removed
- [ ] `.gitignore` properly excludes generated files

---

## APPENDIX — FILE INVENTORY

### Backend Packages (25)
```
backend/analytics/     backend/api/          backend/brokers/
backend/config/        backend/data/         backend/database/
backend/deployment/    backend/features/     backend/infra/
backend/integrations/  backend/migrations/   backend/ml/
backend/mlops/         backend/models/       backend/monitoring/
backend/observability/ backend/optimization/ backend/organism/
backend/research/      backend/risk/         backend/security/
backend/services/      backend/strategies/   backend/utils/
```

### Frontend Feature Modules (14)
```
features/admin/        features/auth/         features/backtesting/
features/dashboard/    features/market-data/  features/ml-models/
features/orders/       features/organism/     features/portfolio/
features/positions/    features/risk/         features/strategies/
features/trades/       features/trading/
```

### Key Entry Points
```
main.py                          → Backend server entry point
backend/api/factory.py           → FastAPI app factory
backend/organism/live_engine.py  → Organism tick loop
backend/organism/scheduler.py    → Tick scheduler
backend/organism/training.py     → Training orchestrator
frontend/src/main.tsx            → Frontend entry point
frontend/src/App.tsx             → React app root
frontend/src/routes/index.tsx    → Route definitions
```
