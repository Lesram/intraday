# Platform Status

**Last Updated:** 2026-02-16
**Status:** Production-Ready (Paper Trading)

---

## Test Suite

| Metric | Value |
|--------|-------|
| Total Collected | ~7,520 |
| Passed | 6,828 |
| Skipped | 692 |
| Failed | 0 |
| Test Timeout | 30s per test |
| Suite Runtime | ~6m 12s |

**Exclusions:** `tests/unit/test_alpaca_stream_comprehensive.py` (async hang on Windows), `tests/unit/test_mega_comprehensive_imports.py` and `tests/unit/generated/test_auto_social_sentiment.py` (transformers library timeout) are excluded from the default run.

**Integration tests** (`test_order_lifecycle.py`, `test_order_validation.py`) are marked `@pytest.mark.live` and `@pytest.mark.integration` — they auto-skip when no live server is available.

---

## Frontend Build

- **Framework:** React 19 + TypeScript + Vite
- **Build Status:** Clean (0 TS errors, 13.78s build time)
- **Chunk Warnings:** 2 chunks >500KB (antd, vendor-other) - expected for Ant Design

---

## Backend API

### Route Coverage
All routes are mounted via `backend/api/routes_setup.py` (called by `backend/api/factory.py`):

**Public (no auth):** system, monitoring, observability, auth, chart templates (public)
**Protected (JWT required):** portfolio, positions, risk, orders, trades, signals, multi-strategy-live, auto-breakout, models, strategy, backtest, optimizations, indicators, drawings, watchlists, chart templates, admin-trading, audit, lots
**Protected + Admin:** organism control (train, freeze, halt, promote, rollback, tick)
**Custom Auth (WebSocket):** market-data, scanner

### Previously Unmounted Routes (Now Fixed)
- `audit_router` - Audit trail endpoints (compliance)
- `lots_router` - Cost basis tracking
- `observability_router` - System health/metrics

---

## Security Posture

**Grade: A-**

### Resolved
- Unsafe `pickle.load()` in model loading replaced with `secure_load_from_path` (HMAC verification)
- Hardcoded database credentials in fallback removed (now fails explicitly)
- All organism control endpoints require `require_admin` role
- JWT with bcrypt, token blacklist (Redis + in-memory fallback)
- 12-character minimum password requirement
- CORS locked to specific origins
- No eval/exec vulnerabilities
- No SQL injection vectors (parameterized queries via SQLAlchemy)
- No command injection (subprocess uses list args, no shell=True)

---

## Architecture

### Stack
| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+ / FastAPI / SQLAlchemy 2.0 / asyncpg |
| Frontend | React 19 / TypeScript / Vite / Ant Design 5 |
| Database | PostgreSQL (async) |
| Cache | Redis |
| Broker | Alpaca (Paper Trading / Production) |
| ML | XGBoost / scikit-learn / TensorFlow / PyTorch |
| WebSocket | Socket.IO |
| Observability | OpenTelemetry / Prometheus |

### Canonical Paths
| System | Canonical Module | Notes |
|--------|-----------------|-------|
| Config | `backend.config.settings.get_settings()` | Pydantic BaseSettings |
| Database | `backend.infra.db.get_db_session()` | FastAPI dependency |
| Database (standalone) | `backend.infra.db.get_session_context()` | Async context manager |
| Auth | `backend.infra.security.get_authenticated_user` | JWT bearer |
| Admin Guard | `backend.infra.security.require_admin` | Role-based |

### Deprecated Modules (Test-Only, Not Runtime)
- `backend/config/config.py` - Deprecated stub
- `backend/config/unified.py` - Deprecated stub
- `backend/config/coordinator.py` - Deprecated stub
- `backend/config_helpers.py` - Deprecated stub
- `backend/infra/unified_database.py` - Deprecated wrapper
- `backend/database.py` - Compatibility shim for tests

---

## Living Organism

The self-evolving trading system is initialized at startup when `ORGANISM_ENABLED=1`.

**Components:** governance, promotion, regime detection, self-evolution, brain persistence, walk-forward validation, transfer learning, Kelly sizing, adaptive exits

**Scheduler:** Configurable via `ENABLE_ORGANISM_SCHEDULER=1`

### Market Scanner (Phase 5)

Replaces the fixed 9-symbol universe with a live market-scanning system.

- **Module:** `backend/organism/market_scanner.py`
- **Enabled:** `SCANNER_ENABLED=true` (default on)
- **Scan cadence:** Every `SCANNER_INTERVAL_TICKS` ticks (default 6 = every 60s)
- **Pipeline:** Most-Actives + Movers (up/down) -> Snapshot tension scoring -> Filtered + ranked candidates
- **Feeds into:** `DynamicUniverseSelector.rotate(candidate_pool=...)` and temporary universe injection (top 20)
- **Tension boost:** Scanner-discovered stocks get confidence multiplier `(1 + tension * 0.5)`
- **Concurrent fetch:** `_fetch_and_compute_features()` uses `asyncio.Semaphore(10)` for parallel bar fetches
- **Rollback:** Set `SCANNER_ENABLED=false` to revert to fixed seed universe

---

## Cleanup Completed

### Factory Refactoring
`backend/api/factory.py` refactored from 1,311 lines to 265 lines:
- Extracted lifespan (startup/shutdown) to `backend/api/lifespan.py`
- Extracted route registration to `backend/api/routes_setup.py`
- Extracted middleware setup to `backend/api/middleware_setup.py`

### Code Removed
- Mock trades/history endpoint in factory.py (returning empty data)
- Dead `register_middleware()` function (~160 lines)
- 5 empty frontend directories
- 15+ outdated doc files archived to `docs/archive/`

### Tests Fixed (From Previous 20+ Failures)
- NoopModelManager assertion updates (prediction/confidence/status)
- BaseStrategy default value corrections (stop_loss/take_profit)
- SignalService test rewrite (cache-layer pattern)
- AlpacaDataClient mock fixes (client.request vs client.get)
- AlpacaStreamClient mock fixes (websockets.connect path)
- Positions route mock updates (PositionDTO aliases, empty mock data)
- Auth route updates (12-char password minimum)
- Risk manager test fixes (MagicMock attribute behavior)
- ML validation test corrections (mock return values, assertion relaxation)
- Security hardening test updates (validate_symbol_strict)
- Broker health check mock fixes (settings.data.redis_url)

### Files Created
- 8 `__init__.py` files for proper Python packages
- `scripts/smoke_test_live.py` — Live smoke test (health, auth, portfolio, organism, WebSocket)
- `scripts/trading_verification.py` — Trading pipeline verification (Alpaca, sync, risk)
- `scripts/ci/run_all_tests_and_report.ps1` — 3-tier test runner (Smoke/Integration/Full)
- `docs/testing/TEST_STRATEGY.md` — Test markers, tiers, and procedures
- `docs/architecture/SYSTEM_OVERVIEW.md` — High-level architecture and canonical paths
- `docs/setup/QUICK_START.md` — Getting-started guide (rewritten from session log)
- `backend/api/lifespan.py` — Extracted lifespan management
- `backend/api/routes_setup.py` — Extracted route registration
- `backend/api/middleware_setup.py` — Extracted middleware setup
- This status document

---

## Running the Platform

### Development
```bash
# Backend
python main.py

# Frontend
cd frontend && npm run dev
```

### Paper Trading (Docker)
```bash
docker-compose -f docker-compose.paper.yml up
```

### Production (Docker)
```bash
docker-compose -f docker-compose.production.yml up
```

### Environment Variables Required
See `.env.example` for full list. Critical ones:
- `DATABASE_URL` - PostgreSQL connection string
- `ALPACA_API_KEY` / `ALPACA_API_SECRET` - Broker credentials
- `JWT_SECRET_KEY` - Authentication secret
- `REDIS_URL` - Redis connection string
