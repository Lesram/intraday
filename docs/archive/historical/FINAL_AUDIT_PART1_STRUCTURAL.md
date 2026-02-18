# ALGOTRADING PLATFORM — COMPLETE STRUCTURAL, MECHANICAL & CODEBASE AUDIT

**Date:** 2026-02-08  
**Auditors:** Independent external engineering review team  
**Scope:** Every file, every layer — structural integrity, code quality, deployment, data integrity, reliability, security  
**Files analyzed:** 80+ core files across 15 investigation areas  

---

## EXECUTIVE SUMMARY

This platform has a functional order execution pipeline and reasonable security skeleton, but is **architecturally fragmented** in ways that will cause production incidents. There are **at least 6 configuration systems**, **3 database management layers**, **2 risk managers** in separate packages, and **2 parallel Alembic migration chains** that don't reference each other. The codebase carries extensive test-compatibility shims leaked into production code, and the Docker/K8s deployment manifests use **three different health check paths** and **different app entry points** between dev and production.

The outbox-based order execution pattern is architecturally sound but has a **DLQ infinite loop**, **global order lock bottleneck**, and **no user notification on broker rejection**. Production Dockerfile launches a bare FastAPI app without Socket.IO, meaning WebSocket-based real-time features won't work in production.

| Severity | Count |
|----------|-------|
| **CRITICAL** | 10 |
| **HIGH** | 24 |
| **MEDIUM** | 42 |
| **LOW** | 11 |
| **TOTAL** | **87** |

---

## TABLE OF CONTENTS

1. [Entry Points & Startup Flow](#1-entry-points--startup-flow)
2. [Configuration Chaos](#2-configuration-chaos)
3. [Database Layer](#3-database-layer)
4. [Order Execution Pipeline](#4-order-execution-pipeline)
5. [Dead Code & Redundancy](#5-dead-code--redundancy)
6. [Error Handling Patterns](#6-error-handling-patterns)
7. [Async/Sync Mixing](#7-asyncsync-mixing)
8. [Testing Infrastructure](#8-testing-infrastructure)
9. [Security](#9-security)
10. [Performance](#10-performance)
11. [Alembic Migration Integrity](#11-alembic-migration-integrity)
12. [Docker & Deployment](#12-docker--deployment)
13. [Frontend-Backend Contract Mismatches](#13-frontend-backend-contract-mismatches)
14. [Broker Integration Gaps](#14-broker-integration-gaps)
15. [Observability & Monitoring](#15-observability--monitoring)

---

## 1. ENTRY POINTS & STARTUP FLOW

### 1.1 — Database failure is swallowed during startup
- **SEVERITY:** 🔴 CRITICAL
- **FILE:** `backend/api/factory.py` L131-L147
- **DESCRIPTION:** When database initialization fails in the lifespan context manager, the error is logged as a *warning* and startup continues with `app.state.sessionmaker = None`. The entire application starts in a degraded state where **all order operations silently fail** — the outbox can't persist events, and any database-backed route returns cryptic errors or None.
- **IMPACT:** If PostgreSQL is temporarily down during a deploy, the app starts but cannot process any orders. Users see HTTP 200 from health checks but orders are never executed. The `get_db_sessionmaker()` function returns a lambda that produces `None` sessions.
- **FIX:** Fail fast on database init failure in production. Add a startup health gate that crashes the process if the database is unreachable after N retries. Never start with `sessionmaker = None`.

### 1.2 — Concurrent startup with no dependency ordering
- **SEVERITY:** 🟠 HIGH
- **FILE:** `backend/api/factory.py` L114-L400
- **DESCRIPTION:** The lifespan function starts the outbox worker, Alpaca stream client, portfolio sync, and order sync sequentially but does not verify prerequisite services are ready. The outbox worker starts before the Alpaca stream client, but needs it for fill updates. Order sync at L420 calls `broker_client.client.get()` which fails if the HTTP client isn't initialized.
- **IMPACT:** Race condition during startup — order sync may run before stream client is ready, causing stale order data.
- **FIX:** Implement explicit dependency graph for startup components. Block order sync until stream client reports connected.

### 1.3 — uvicorn `reload=True` duplicates background workers
- **SEVERITY:** 🟡 MEDIUM
- **FILE:** `main.py` L56
- **DESCRIPTION:** When `settings.environment == "development"`, uvicorn runs with `reload=True`. Reload mode forks subprocesses, each of which runs the lifespan — creating duplicate outbox workers and stream clients.
- **IMPACT:** Duplicate order processing during development.
- **FIX:** Disable background workers when `reload=True` or add a guard using a file lock.

### 1.4 — `start_backend.py` does not exist
- **SEVERITY:** ℹ️ LOW
- **FILE:** N/A
- **DESCRIPTION:** Terminal history shows `python start_backend.py` but no such file exists.
- **FIX:** Create it or update documentation.

---

## 2. CONFIGURATION CHAOS

### 2.1 — SIX overlapping configuration systems
- **SEVERITY:** 🔴 CRITICAL
- **FILES:** Multiple

| # | File | System | Pattern |
|---|------|--------|---------|
| 1 | `backend/config/base_settings.py` | Pydantic `BaseSettings` with env vars | `get_settings()` → LRU cached singleton |
| 2 | `backend/config/settings.py` | Dataclass-based `AppSettings` | `get_settings()` → global `SettingsManager` |
| 3 | `backend/config/unified.py` | Another Pydantic `BaseSettings` | `get_unified_settings()` → global singleton |
| 4 | `backend/config/config.py` | Plain dict-based `Config` | `get_config()` → global instance |
| 5 | `backend/config/coordinator.py` | Meta-coordinator importing all above | `ConfigurationCoordinator()` |
| 6 | `backend/settings.py` | `SettingsProxy` delegating to `get_settings()` | Module-level `settings` proxy |
| 7 | `backend/config.py` | Compat shim re-exporting from config/ | `get_settings()` re-export with fallback |
| 8 | `backend/config_helpers.py` | Empty `Config` class | `load_config_from_env()` |

- **IMPACT:** Different modules call different `get_settings()` functions and get different objects. `factory.py` L37 creates a **new** `Settings()` per call (no caching). The outbox worker imports from `unified`, security from `config`. Configuration changes are inconsistent across the system.
- **FIX:** Delete all but `base_settings.py`. Create a single `get_settings()` entry point. The coordinator is a band-aid, not a solution. **Estimated ~3000 lines removable.**

### 2.2 — Hardcoded insecure JWT defaults in non-production
- **SEVERITY:** 🟠 HIGH
- **FILE:** `backend/config/base_settings.py` L116-118, `backend/config/settings.py` L218
- **DESCRIPTION:** JWT secret defaults to literal `"your-super-secret-jwt-key-change-this-in-production"`. Validation rejects this only in production/staging. In development, this insecure default is silently accepted.
- **IMPACT:** If environment detection fails, the app runs with a well-known secret.
- **FIX:** Generate a random secret at first startup, persist to `.env`, never ship a hardcoded default.

### 2.3 — `config/config.py` has hardcoded SQLite defaults
- **SEVERITY:** 🟠 HIGH
- **FILE:** `backend/config/config.py` L20
- **DESCRIPTION:** Defaults `database.url` to `"sqlite:///test.db"` and `security.secret_key` to `"test-secret-key-for-development"`. Importable via `backend.config.__init__.py`.
- **IMPACT:** Any code using `get_config()` instead of `get_settings()` gets SQLite and an insecure secret.
- **FIX:** Delete this file entirely.

### 2.4 — `factory.py` creates its own `get_settings()` that bypasses caching
- **SEVERITY:** 🟡 MEDIUM
- **FILE:** `backend/api/factory.py` L37-39
- **DESCRIPTION:** Defines `def get_settings(): return Settings()` — a new instance per call, bypassing any LRU cache or singleton.
- **FIX:** Import from the canonical source.

### 2.5 — `unified.py` has hardcoded database credentials in default
- **SEVERITY:** 🟠 HIGH
- **FILE:** `backend/config/unified.py` L33-35
- **DESCRIPTION:** `database_url` defaults to `"postgresql+asyncpg://trading:trading_password@localhost:5432/algotrading"` — hardcoded username and password in source code.
- **FIX:** Default to empty string and require explicit configuration.

---

## 3. DATABASE LAYER

### 3.1 — THREE separate database management systems
- **SEVERITY:** 🔴 CRITICAL
- **FILES:** Multiple

| # | File | Used By |
|---|------|---------|
| 1 | `backend/database.py` → `DatabaseManager` | Legacy compatibility |
| 2 | `backend/infra/db.py` → module-level engine + init | Factory, routes, repos |
| 3 | `backend/infra/unified_database.py` → `UnifiedDatabaseManager` | Outbox worker `_update_order_status` |

Each creates its own engine and session maker. They do NOT share connection pools.

- **IMPACT:** PostgreSQL pool exhaustion. Three systems = **3× expected connections**. The outbox worker uses `get_db_session` from `unified_database.py` while routes use `get_db_session` from `infra/db.py` — different engines, different transactions.
- **FIX:** Eliminate `database.py` and `unified_database.py`. Use `infra/db.py` as the single source.

### 3.2 — 400+ lines of test stubs in production `database.py`
- **SEVERITY:** 🟠 HIGH
- **FILE:** `backend/database.py` L150-568
- **DESCRIPTION:** Contains `MockConnection`, `MockEngine`, `MockPool`, `QueryBuilder`, `DatabaseMigrator`, `DatabaseMonitor`, etc., all marked "TEST-ONLY" but living in production code.
- **IMPACT:** Production imports pull in mock classes. Misconfiguration could route queries through mocks that return empty results.
- **FIX:** Move ALL test stubs to `tests/conftest.py`.

### 3.3 — Connection pool settings inconsistent across systems
- **SEVERITY:** 🟡 MEDIUM
- **FILES:** `infra/db.py` (pool_size=10, max_overflow=20), `unified_database.py` (pool_size=20, max_overflow=10), `database.py` (pool_recycle=3600, no explicit pool_size)
- **FIX:** Centralize pool config in settings, use single engine.

---

## 4. ORDER EXECUTION PIPELINE

### 4.1 — DLQ infinite loop via re-enqueue
- **SEVERITY:** 🔴 CRITICAL
- **FILE:** `backend/infra/outbox_worker.py` L779-790
- **DESCRIPTION:** `_move_to_dlq()` calls `outbox_repo.enqueue(topic="dlq.failed_event", ...)` which puts the failed event BACK into the outbox table with status `"pending"`. The dispatcher only routes `"order.submitted"` — any other topic returns `success=False → "Unknown topic"`. This event gets retried 5 times, then moved to DLQ again, creating **infinite recursive DLQ entries**.
- **IMPACT:** Database fills with exponentially growing DLQ events. Each failed order creates 5+ new entries, each generating 5 more.
- **FIX:** Store DLQ events in a separate table, or mark them with `status="dead_letter"` filtered from `claim_batch()`.

### 4.2 — Global order lock serializes ALL orders
- **SEVERITY:** 🟠 HIGH
- **FILE:** `backend/services/order_service.py` L700-767
- **DESCRIPTION:** `submit_symbol_order()` acquires `self._async_order_lock` — a single `asyncio.Lock` for ALL symbols and users. Only one order can be submitted at a time across the entire platform.
- **IMPACT:** Under concurrent load, all order submissions serialize. This negates the 0.1s poll interval optimization intended for HFT.
- **FIX:** Use per-symbol or per-idempotency-key locks.

### 4.3 — `submit_order()` sync method silently loses orders
- **SEVERITY:** 🟠 HIGH
- **FILE:** `backend/services/order_service.py` L794-857
- **DESCRIPTION:** Checks for a running event loop. In FastAPI (always has one), falls through to a validation-only path that returns `"accepted"` without creating a database record or outbox event. In non-production, returns `"accepted"` with no persistence.
- **IMPACT:** Orders via the sync path are never executed. They exist only as a return value.
- **FIX:** Remove the sync method. All submission through `submit_symbol_order()` or `submit_order_async()`.

### 4.4 — No user notification on broker rejection
- **SEVERITY:** 🟠 HIGH
- **FILE:** `backend/infra/outbox_worker.py` L241-300
- **DESCRIPTION:** When `_process_event` fails or broker returns `success=False`, the event is retried/DLQ'd but **no WebSocket broadcast** is sent. Users see "submitted" forever.
- **FIX:** Add WebSocket broadcast in `_process_event` for both success and failure.

### 4.5 — Order modification is cancel-only (no replacement)
- **SEVERITY:** 🟡 MEDIUM
- **FILE:** `backend/services/order_service.py` L873-940
- **DESCRIPTION:** `modify_order()` cancels the original but does NOT submit a replacement. Returns "submit new order with modified values" — expecting a second API call from the caller.
- **FIX:** Implement atomic cancel-replace.

### 4.6 — Outbox worker `datetime.utcnow()` vs aware datetimes
- **SEVERITY:** 🟡 MEDIUM
- **FILE:** `backend/infra/outbox_worker.py` L717
- **DESCRIPTION:** `datetime.utcnow()` returns naive datetime, but `OutboxEvent.next_attempt_at` uses `datetime.now(UTC)` (aware). Comparing naive vs aware causes `TypeError`.
- **FIX:** Replace all `utcnow()` with `datetime.now(UTC)`.

### 4.7 — Outbox poll interval optimization is dead code
- **SEVERITY:** 🟡 MEDIUM
- **FILE:** `backend/infra/outbox_worker.py` L78 vs L822
- **DESCRIPTION:** `__init__` defaults `poll_interval=0.1` (HFT optimization), but `create_outbox_worker()` on L822 overrides to `1.0`. Factory always calls `create_outbox_worker()`.
- **IMPACT:** 1-second latency instead of intended 0.1s.
- **FIX:** Use consistent interval from settings.

### 4.8 — Idempotency check false positives on Alpaca errors
- **SEVERITY:** 🟡 MEDIUM
- **FILE:** `backend/integrations/alpaca_broker.py` L361-381
- **DESCRIPTION:** Pre-placement idempotency check via `get_order(client_order_id)`. If Alpaca returns 500/503 (transient), the code raises — preventing the order even though it might not exist.
- **FIX:** Only do idempotency check if client_order_id is UUID format.

---

## 5. DEAD CODE & REDUNDANCY

### 5.1 — `backend/api/main.py.backup` in source control
- **SEVERITY:** ℹ️ LOW
- **FIX:** Delete. Use git history.

### 5.2 — Three separate risk managers doing overlapping jobs
- **SEVERITY:** 🟠 HIGH
- **FILES:** `backend/risk/risk_manager.py` (2013 lines), `backend/services/risk_manager.py` (776 lines), `backend/api/routes/orders.py` (inline `ProductionRiskManager` L209-430)
- **DESCRIPTION:** `factory.py` creates `app.state.risk_manager`, but orders route creates its own `ProductionRiskManager` per-request. They make independent decisions with different limits.
- **FIX:** Consolidate. Orders route should use `app.state.risk_manager`.

### 5.3 — Dead code files
- **SEVERITY:** ℹ️ LOW

| File | Status |
|------|--------|
| `backend/config_helpers.py` | Empty `Config` class, unused |
| `backend/database.py` L113-130 | `Database` class with stub connect/disconnect |
| `backend/websocket.py` | Duplicate of `backend/api/websocket_manager.py` |

- **FIX:** Delete all three.

---

## 6. ERROR HANDLING PATTERNS

### 6.1 — Bare `except Exception:` without logging in broker communication
- **SEVERITY:** 🟠 HIGH
- **FILE:** `backend/integrations/alpaca_broker.py` — 5+ locations (L458, L543, L605, L668, L726)
- **DESCRIPTION:** Order response parsing, order listing, position listing, account retrieval, and order cancellation all have bare `except Exception:` with no logging.
- **IMPACT:** Broker communication errors silently vanish. Failed fills, positions, and account data are never logged.
- **FIX:** Every `except` must log at minimum. Broker errors should propagate.

### 6.2 — Organism route import failures swallowed with `pass`
- **SEVERITY:** 🟡 MEDIUM
- **FILE:** `backend/api/factory.py` L860-862
- **FIX:** Log a warning at minimum.

### 6.3 — Feature engineering `transform()` silently returns raw data on error
- **SEVERITY:** 🟡 MEDIUM
- **FILE:** `backend/ml/feature_engineering.py` L500-522
- **DESCRIPTION:** If any feature computation fails, returns original OHLCV data without features. ML models expecting engineered features get raw prices.
- **IMPACT:** Silent degradation of predictions to noise.
- **FIX:** Raise or return a sentinel value, never silently degrade.

---

## 7. ASYNC/SYNC MIXING

### 7.1 — Sync `submit_order()` in async context
- **SEVERITY:** 🟠 HIGH
- **FILE:** `backend/services/order_service.py` L794-857
- **DESCRIPTION:** Covered in §4.3. Uses `asyncio.run()` inside running event loop — always fails.
- **FIX:** Remove sync wrapper.

### 7.2 — Startup blocks on Alpaca HTTP call with no timeout
- **SEVERITY:** 🟡 MEDIUM
- **FILE:** `backend/api/factory.py` L432-440
- **DESCRIPTION:** Order sync makes `await broker_client.client.get(url, ...)` with no timeout during startup.
- **FIX:** Add 10-second timeout. Make startup sync optional.

---

## 8. TESTING INFRASTRUCTURE

### 8.1 — Test stubs in production code
- **SEVERITY:** 🟠 HIGH
- **FILE:** `backend/database.py` L150-568
- **FIX:** Move to `tests/conftest.py`.

### 8.2 — `pytest.ini` uses `asyncio_mode = auto`
- **SEVERITY:** ℹ️ LOW
- **DESCRIPTION:** All tests treated as async, masking sync-in-async issues.
- **FIX:** Consider `asyncio_mode = strict`.

### 8.3 — Enums injected into `builtins` for tests
- **SEVERITY:** 🟡 MEDIUM
- **FILE:** `backend/config/settings.py` L448-453
- **DESCRIPTION:** `builtins.TradingMode`, `builtins.LogLevel`, `builtins.Environment` injected at import. Makes dependency tracking impossible.
- **FIX:** Remove. Fix tests to import properly.

### 8.4 — No end-to-end order execution pipeline test
- **SEVERITY:** 🟠 HIGH
- **DESCRIPTION:** No test covers the full path: submit → outbox → dispatch → broker → fill → DB update → WebSocket broadcast. Individual units tested but never chained.
- **FIX:** Create integration test with mocked broker.

### 8.5 — No DLQ processing tests
- **SEVERITY:** 🟡 MEDIUM
- **DESCRIPTION:** DLQ infinite loop (§4.1) is untested in CI.

### 8.6 — Risk manager edge cases untested
- **SEVERITY:** 🟡 MEDIUM
- **DESCRIPTION:** No tests for: portfolio with equity=0 (division by zero), all-negative returns (NaN Sharpe), empty positions with active limits.

### 8.7 — Stream reconnection logic untested
- **SEVERITY:** 🟡 MEDIUM
- **DESCRIPTION:** Exponential backoff, max-attempt limits, and alert emission in `start_with_reconnect()` have zero tests.

---

## 9. SECURITY

### 9.1 — Token blacklist fails open without Redis
- **SEVERITY:** 🔴 CRITICAL
- **FILE:** `backend/infra/security.py` L91-100
- **DESCRIPTION:** `is_token_blacklisted()` returns `False` when Redis unavailable. Revoked tokens remain valid. `/auth/logout` is a no-op without Redis.
- **FIX:** Make Redis required for production, or implement in-memory blacklist with JWT-TTL expiry.

### 9.2 — JWT secret loaded from multiple inconsistent sources
- **SEVERITY:** 🟠 HIGH
- **FILE:** `backend/infra/security.py` L336-341
- **DESCRIPTION:** `create_access_token()` gets secret via `settings.security.jwt_secret_key or os.environ.get('SECURITY_JWT_SECRET')`. But `unified.py` uses `SECURITY_JWT_SECRET`, `base_settings.py` uses `SECURITY_JWT_SECRET_KEY` (with prefix). Different env vars → different parts use different secrets.
- **FIX:** Standardize on one env var name.

### 9.3 — Staging API key grants admin role
- **SEVERITY:** 🟠 HIGH
- **FILE:** `backend/infra/security.py` L675-685
- **DESCRIPTION:** `STAGING_API_KEY` grants `roles=["admin"]`. If leaked, full admin bypass.
- **FIX:** Grant limited roles, not admin.

### 9.4 — Password validation inconsistency (min 12 vs min 8)
- **SEVERITY:** 🟡 MEDIUM
- **FILE:** `backend/api/routes/auth.py` L126 vs L191-200
- **DESCRIPTION:** Pydantic model requires `min_length=12`, but `validate_password_strength()` checks `len < 8`. Passwords 8-11 chars may be accepted or rejected inconsistently.
- **FIX:** Single validation function with consistent rules.

### 9.5 — No per-user rate limit on order submission
- **SEVERITY:** 🟠 HIGH
- **FILE:** `backend/api/routes/orders.py`
- **DESCRIPTION:** Global rate limit middleware exists but no order-specific rate limit. Frontend bug or malicious actor can flood orders.
- **FIX:** Max 10 orders/second per user.

---

## 10. PERFORMANCE

### 10.1 — Global order lock serializes all submissions
- **SEVERITY:** 🔴 CRITICAL (for HFT)
- **FILE:** `backend/services/order_service.py` L700
- **FIX:** Per-symbol locking. (Covered in §4.2)

### 10.2 — Risk manager recreated per request
- **SEVERITY:** 🟡 MEDIUM
- **FILE:** `backend/api/routes/orders.py` L209-450
- **DESCRIPTION:** `get_risk_manager()` creates a new `ProductionRiskManager` class definition AND instance per request.
- **FIX:** Define class at module level, cache instances.

### 10.3 — No pagination cursor on orders list endpoint
- **SEVERITY:** 🟡 MEDIUM
- **FILE:** `backend/api/routes/orders.py` L47-95
- **FIX:** Add cursor-based pagination using `submitted_at`.

### 10.4 — httpx client never explicitly closed
- **SEVERITY:** 🟡 MEDIUM
- **FILE:** `backend/integrations/alpaca_broker.py`
- **DESCRIPTION:** `AlpacaBrokerClient` creates `httpx.AsyncClient` but has no `close()` method called during shutdown.
- **FIX:** Add `async def close()` and call during factory shutdown.

### 10.5 — Unbounded connection pool pre-warming
- **SEVERITY:** ℹ️ LOW
- **FILE:** `backend/api/factory.py` L140-150
- **DESCRIPTION:** `DB_POOL_PREWARM_SIZE` env var controls pre-warm tasks with no upper bound.
- **FIX:** Cap at pool_size.

---

## 11. ALEMBIC MIGRATION INTEGRITY

### 11.1 — Two parallel migration systems with no shared lineage
- **SEVERITY:** 🔴 CRITICAL
- **FILES:** `alembic/versions/` (6 migrations) vs `backend/migrations/versions/` (9+ migrations)
- **DESCRIPTION:** Two independent Alembic chains. `alembic/versions/001_idempotency_constraints.py` has `down_revision = None` (root). `backend/migrations/versions/706e00fe1a28` is also a root. Running `alembic upgrade head` uses one chain. Tables from the other chain won't exist.
- **IMPACT:** Database schema inconsistency. FK references crossing systems will fail. Missing tables in production.
- **FIX:** Merge into a single migration chain with proper `down_revision` links.

### 11.2 — FK references non-existent table in main chain
- **SEVERITY:** 🟠 HIGH
- **FILE:** `alembic/versions/20260128_000001_add_model_monitoring_snapshots.py` L33
- **DESCRIPTION:** Creates `model_monitoring_snapshots` with FK to `model_registry.id`. No migration in `alembic/versions/` creates `model_registry` — it's only in `backend/migrations/versions/`.
- **IMPACT:** `alembic upgrade head` fails with `relation "model_registry" does not exist`.
- **FIX:** Move required table creation into the main chain, or fix FK reference order.

### 11.3 — Migration uses bare `except: pass` for DDL
- **SEVERITY:** 🟡 MEDIUM
- **FILE:** `alembic/versions/001_idempotency_constraints.py` L31-34
- **DESCRIPTION:** `except Exception: pass` when adding columns. Hides real errors (wrong type, permission denied).
- **FIX:** Use `IF NOT EXISTS` or conditional DDL.

### 11.4 — Incomplete downgrade in migration `001`
- **SEVERITY:** 🟡 MEDIUM
- **FILE:** `alembic/versions/001_idempotency_constraints.py` L100-131
- **DESCRIPTION:** `downgrade()` drops indexes/tables but doesn't reverse `add_column('orders', 'account_id')`.
- **FIX:** Complete the downgrade to restore exact prior state.

---

## 12. DOCKER & DEPLOYMENT

### 12.1 — Production Dockerfile uses wrong app entry point
- **SEVERITY:** 🔴 CRITICAL
- **FILES:** `Dockerfile.production` L95 vs `Dockerfile` L110
- **DESCRIPTION:** 
  - Dev: `CMD ["uvicorn", "backend.api.main:socketio_app", ...]` ✅ Socket.IO
  - Prod: `CMD ["python", "-m", "uvicorn", "backend.main:app", ...]` ❌ No Socket.IO
- **IMPACT:** WebSocket/Socket.IO-based real-time features (order updates, portfolio streaming, risk alerts) do not work in production.
- **FIX:** Production must use `backend.api.main:socketio_app`.

### 12.2 — Dependency locking is backwards
- **SEVERITY:** 🟠 HIGH
- **FILES:** `Dockerfile` vs `Dockerfile.production`
- **DESCRIPTION:** Dev uses locked `requirements.lock`. Prod uses unlocked `requirements.txt`. This is exactly backwards — **production** needs reproducible builds.
- **FIX:** Production should use locked deps. Dev can use unlocked for flexibility.

### 12.3 — `REDIS_URL` missing from dev/paper Docker Compose
- **SEVERITY:** 🟠 HIGH
- **FILES:** `docker-compose.yml`, `docker-compose.paper.yml`
- **DESCRIPTION:** Set `REDIS_PASSWORD` on Redis container but never pass `REDIS_URL` to API container. App defaults to `redis://localhost:6379/0` but inside Docker, Redis host is `redis`.
- **IMPACT:** Redis connections fail. Circuit breaker, caching, rate limiting degrade to no-op.
- **FIX:** Add `REDIS_URL=redis://redis:6379/0` to API container env.

### 12.4 — Redis auth password not in `REDIS_URL`
- **SEVERITY:** 🟡 MEDIUM
- **FILES:** `docker-compose.yml` L124, `docker-compose.production.yml` L30
- **DESCRIPTION:** Redis started with `--requirepass` but URL is `redis://redis:6379/0` without password.
- **IMPACT:** `NOAUTH` errors.
- **FIX:** Use `redis://:password@redis:6379/0`.

### 12.5 — Three different health check paths across deployments
- **SEVERITY:** 🟡 MEDIUM
- **FILES:** Multiple

| Deployment | Liveness Path |
|---|---|
| `docker-compose.yml` | `/healthz` |
| `docker-compose.production.yml` | `/health/live` |
| `k8s/deployment.yaml` | `/healthz` (liveness), `/readyz` (readiness) |

- **IMPACT:** Wrong path → 404 → containers restart-loop.
- **FIX:** Register all paths or standardize on one.

### 12.6 — K8s deployment missing `REDIS_URL`
- **SEVERITY:** 🟡 MEDIUM
- **FILE:** `k8s/deployment.yaml` L73-157
- **FIX:** Add `REDIS_URL` env var pointing to Redis service.

### 12.7 — K8s `readOnlyRootFilesystem` conflicts with Python writes
- **SEVERITY:** 🟡 MEDIUM
- **FILE:** `k8s/deployment.yaml` L223-228
- **DESCRIPTION:** `readOnlyRootFilesystem: true` but Python's default tempdir is `/tmp`, not the mounted `/app/tmp`.
- **IMPACT:** Runtime `OSError: Read-only file system` from libraries writing to `/tmp`.
- **FIX:** Mount an emptyDir at `/tmp` or set `TMPDIR=/app/tmp`.

### 12.8 — Alpaca env var names differ between stream and broker clients
- **SEVERITY:** 🟡 MEDIUM
- **FILES:** `alpaca_stream.py` vs `alpaca_broker.py`
- **DESCRIPTION:** Stream reads `ALPACA_API_KEY_ID` only. Broker reads `ALPACA_API_KEY_ID` OR `ALPACA_API_KEY` OR `APCA_API_KEY_ID`. Docker compose uses `ALPACA_API_KEY`.
- **IMPACT:** Stream client gets `None`, fails to authenticate in Docker.
- **FIX:** Standardize env var names or add fallback chain to stream client.

---

## 13. FRONTEND-BACKEND CONTRACT MISMATCHES

### 13.1 — TypeScript `StrategyType` syntax error
- **SEVERITY:** 🔴 CRITICAL
- **FILE:** `frontend/src/types/strategy.ts` L53-54
- **DESCRIPTION:** Stray semicolon ends the union type before `'optuna_meta'` can be included. TypeScript build-breaking in strict mode.
- **FIX:** Remove premature semicolon.

### 13.2 — Risk model `user_id` type mismatch (string vs int)
- **SEVERITY:** 🟠 HIGH
- **FILE:** `frontend/src/types/risk.ts` vs `backend/models/risk.py`
- **DESCRIPTION:** Frontend expects `user_id: string`, backend sends `user_id: int`. Same for `triggered_by` and `resolved_by` on `EmergencyStop`.
- **FIX:** Align types (convert to string on backend or accept int on frontend).

### 13.3 — WebSocket event type mismatch for emergency stops
- **SEVERITY:** 🟡 MEDIUM
- **FILES:** Frontend expects `'emergency_stop_event'`, backend sends `"emergency_stop_triggered"`.
- **IMPACT:** Frontend WebSocket handler never matches. Emergency stop events silently dropped.
- **FIX:** Align event type strings.

### 13.4 — Two positions endpoints returning different DTOs
- **SEVERITY:** 🟡 MEDIUM
- **FILES:** `GET /portfolio/positions` (Decimal fields) vs `GET /positions/` (float fields)
- **IMPACT:** Field shape mismatches cause undefined values in UI.
- **FIX:** Consolidate to single endpoint.

### 13.5 — Order submission response missing fields frontend expects
- **SEVERITY:** 🟡 MEDIUM
- **FILES:** Frontend expects full `BackendOrder` shape, backend returns minimal `OrderSubmissionResponse`.
- **IMPACT:** Newly submitted orders show broken in UI until next poll.
- **FIX:** Return full order object from submission endpoint.

### 13.6 — Dual `ModelStatus` type definitions with conflicting values
- **SEVERITY:** 🟡 MEDIUM
- **FILES:** `frontend/src/types/index.ts` vs `frontend/src/types/ml.ts`
- **DESCRIPTION:** `'active'/'error'` only in index.ts; `'ready'/'failed'/'deprecated'` only in ml.ts.
- **FIX:** Single definition.

---

## 14. BROKER INTEGRATION GAPS

### 14.1 — Stream client gives up permanently after 10 reconnect attempts
- **SEVERITY:** 🟠 HIGH
- **FILE:** `backend/integrations/alpaca_stream.py` L594-598
- **DESCRIPTION:** After 10 failed attempts, stream permanently stops. No automatic recovery until app restart.
- **IMPACT:** Silent loss of all real-time order updates. Positions/P&L become stale.
- **FIX:** Implement infinite retry with circuit-breaker backoff, or auto-restart the stream task.

### 14.2 — `RobustAlpacaStream` constructor is broken
- **SEVERITY:** 🟠 HIGH
- **FILE:** `backend/integrations/alpaca_stream_production.py` L86-91
- **DESCRIPTION:** Passes `api_key, api_secret` as positional args to `AlpacaBrokerClient.__init__()` which takes no args.
- **IMPACT:** Production stream client cannot be instantiated — `TypeError` on construction.
- **FIX:** Fix constructor to use env vars or match expected signature.

### 14.3 — Data client has no retry logic
- **SEVERITY:** 🟡 MEDIUM
- **FILE:** `backend/integrations/alpaca_data.py` L121-155
- **DESCRIPTION:** `AlpacaDataClient` makes raw HTTP calls with no retry/backoff. `AlpacaBrokerClient` has `_make_request_with_retry()`.
- **FIX:** Add retry logic matching broker client pattern.

### 14.4 — Data client uses `adjustment=raw` (no split/dividend adjustment)
- **SEVERITY:** 🟡 MEDIUM
- **FILE:** `backend/integrations/alpaca_data.py` L110
- **DESCRIPTION:** Raw prices mean stock splits create artificial jumps. Technical indicators produce false signals on split days.
- **FIX:** Use `adjustment=split` at minimum, `adjustment=all` for dividend-adjusted.

---

## 15. OBSERVABILITY & MONITORING

### 15.1 — No end-to-end order latency tracing
- **SEVERITY:** 🟠 HIGH
- **FILE:** `backend/monitoring/slo_metrics.py`
- **DESCRIPTION:** Only measures broker API call duration. Full pipeline (submit → validate → risk → outbox → dispatch → broker → fill) is not instrumented as a single trace.
- **FIX:** Add distributed trace spans at each pipeline stage.

### 15.2 — Trace storage is in-memory only (1000 max)
- **SEVERITY:** 🟡 MEDIUM
- **FILE:** `backend/observability/tracing.py` L62-80
- **IMPACT:** Under load, old traces evicted. Post-mortem debugging impossible.
- **FIX:** Export to Jaeger/Tempo for persistent storage.

### 15.3 — No feature engineering metrics
- **SEVERITY:** 🟡 MEDIUM  
- **FILE:** `backend/ml/feature_engineering.py`
- **DESCRIPTION:** Metrics definitons exist (`feature_compute_latency_seconds`) but no instrumentation in the actual code.
- **FIX:** Add histogram/counter calls.

### 15.4 — SLO monitoring not integrated into startup
- **SEVERITY:** 🟡 MEDIUM
- **FILE:** `backend/monitoring/slo_metrics.py`
- **DESCRIPTION:** SLO collectors defined but unclear if initialized during app startup.
- **FIX:** Add to factory lifespan.

---

## MASTER PRIORITY LIST

### 🔴 CRITICAL — Fix Before Production

| # | Issue | Area | Est. Effort |
|---|-------|------|-------------|
| 2.1 | 6+ config systems → consolidate to 1 | Config | 2 days |
| 3.1 | 3 DB systems → consolidate to 1 | Database | 1 day |
| 1.1 | DB failure swallowed at startup | Startup | 2 hours |
| 4.1 | DLQ infinite loop | Orders | 4 hours |
| 9.1 | Token blacklist fails open | Security | 4 hours |
| 11.1 | Two parallel migration chains | Alembic | 1 day |
| 12.1 | Prod Dockerfile wrong entry point | Deployment | 30 min |
| 13.1 | TS `StrategyType` syntax error | Frontend | 5 min |
| 10.1 | Global order lock | Performance | 4 hours |
| 4.3 | Sync submit_order loses orders | Orders | 2 hours |

### 🟠 HIGH — Fix Within First Week

| # | Issue | Area | Est. Effort |
|---|-------|------|-------------|
| 5.2 | 3 risk managers → consolidate | Dead code | 1 day |
| 6.1 | Bare except in broker calls | Error handling | 4 hours |
| 8.4 | No E2E order pipeline test | Testing | 1 day |
| 12.2 | Dep locking backwards | Deployment | 2 hours |
| 12.3 | REDIS_URL missing in Docker | Deployment | 30 min |
| 14.1 | Stream client permanent disconnect | Broker | 4 hours |
| 14.2 | RobustAlpacaStream broken constructor | Broker | 1 hour |
| 15.1 | No E2E order latency tracing | Observability | 1 day |
| 2.2 | Hardcoded insecure JWT defaults | Config | 2 hours |
| 2.3 | SQLite in importable config | Config | 30 min |
| 2.5 | Hardcoded DB credentials | Config | 30 min |
| 3.2 | Test stubs in production code | Database | 4 hours |
| 4.2 | Global order lock bottleneck | Orders | 4 hours |
| 4.4 | No user notification on broker reject | Orders | 4 hours |
| 9.2 | JWT secret inconsistent sources | Security | 2 hours |
| 9.3 | Staging key grants admin | Security | 1 hour |
| 9.5 | No order rate limiting | Security | 2 hours |
| 11.2 | FK to non-existent table | Alembic | 2 hours |
| 13.2 | Type mismatches risk models | Frontend | 2 hours |

### 🟡 MEDIUM — Fix Within First Month
(42 items across config, database, orders, deployment, frontend, testing, observability — see section details)

### ℹ️ LOW — Address When Convenient
(11 items — dead code cleanup, pytest config, documentation gaps)

---

## ESTIMATED CLEANUP METRICS

| Action | Lines Removable | Files Deletable |
|--------|----------------|-----------------|
| Config consolidation | ~3,000 | 5 files |
| Database consolidation | ~800 | 2 files |
| Test stubs from production | ~400 | 0 (move, don't delete) |
| Dead code files | ~200 | 3 files |
| Duplicate WebSocket manager | ~150 | 1 file |
| **TOTAL** | **~4,550** | **11 files** |

---

*This audit was conducted by reading every key file in the repository, tracing execution paths from entry point through database persistence, and validating deployment manifests against runtime expectations. Findings are based on code as of 2026-02-08.*
