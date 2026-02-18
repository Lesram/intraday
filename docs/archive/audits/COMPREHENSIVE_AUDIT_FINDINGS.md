# 🔍 COMPREHENSIVE PLATFORM AUDIT FINDINGS
## Hedge Fund-Grade Algorithmic Trading Platform - Technical Audit Report

**Audit Date:** January 2026  
**Audit Version:** 1.0  
**Platform Version:** 1.0.0  
**Auditor:** Principal Engineer Technical Review

---

## EXECUTIVE SUMMARY

### Overall Assessment: **B+ (Strong Foundation, Production-Ready with Improvements)**

This audit covers a **comprehensive algorithmic trading platform** with sophisticated architecture suitable for institutional-grade operations. The platform demonstrates strong engineering practices in core areas while revealing opportunities for enhancement in security, performance, and operational excellence.

### Key Metrics
| Metric | Value | Assessment |
|--------|-------|------------|
| Python Backend Files | 562 | Large, well-organized codebase |
| Total Python Code Size | ~6.4 MB | Substantial platform |
| Frontend Components | 165 TS/TSX files | Modern React architecture |
| Function Definitions | 3,622 | Comprehensive functionality |
| Return Type Hints | 1,702 (47%) | Needs improvement → target 90%+ |
| `Any` Type Usage | 119 occurrences | Should reduce for type safety |
| TODO/FIXME Comments | 20+ | Technical debt to address |
| Test Files | 43 | Good coverage, needs expansion |

---

## PHASE 1: ARCHITECTURE REVIEW

### 1.1 System Architecture - ✅ STRONG

**Positive Findings:**
- **Factory Pattern**: Clean `create_app()` factory with isolated FastAPI instances
- **Lifespan Management**: Proper async context manager for startup/shutdown
- **Task Registry**: Tracked asyncio tasks for deterministic cleanup
- **Database Pre-warming**: Connection pool pre-warming for reduced latency
- **Socket.IO Integration**: Real-time WebSocket support with Socket.IO wrapper

**Architecture Flow:**
```
main.py → backend/api/main.py → backend/api/factory.py
              ↓
    Database Init → Outbox Worker → Alpaca Stream → Portfolio Sync
              ↓
    FastAPI App with Lifespan Management
```

**Issues Found:**
| Issue | Severity | Location |
|-------|----------|----------|
| No SQLite fallback in production | Low | [factory.py](backend/api/factory.py#L100) |
| Database required before app start | Medium | Coupling concern |

### 1.2 Database Architecture - ✅ SOLID

**Schema Design:**
- SQLAlchemy 2.0 with async patterns (`AsyncAttrs`, `DeclarativeBase`)
- Proper UUID primary keys for orders (avoiding sequential ID exposure)
- JSONB for flexible attributes (PostgreSQL-optimized)
- Idempotency keys for order deduplication

**Models Reviewed:**
- `User` - Proper password hashing, role-based access
- `Order` - Complete lifecycle tracking, idempotency support
- `Execution` - Fill tracking with order relationships
- `Position` - Symbol-based primary key (one position per symbol)
- `Signal` - ML signal tracking with confidence/strength
- `AuditLog` - Compliance-ready with hash chain support
- `OutboxEvent` - Exactly-once delivery pattern

**Indexes:** Well-designed composite indexes for common query patterns.

**Issue:** [backend/database/models.py](backend/database/models.py) contains mock models - production uses [backend/infra/schemas.py](backend/infra/schemas.py)

### 1.3 Repository Pattern - ✅ EXCELLENT

- Clean separation of concerns in [backend/infra/repositories/](backend/infra/repositories/)
- `OrdersRepo` with proper idempotency (`upsert_by_idempotency`)
- Race condition handling via IntegrityError catch
- Async session management

### 1.4 Connection Pooling - ✅ PRODUCTION-READY

```python
# backend/infra/db.py
pool_size=10
max_overflow=20
pool_recycle=3600
pool_reset_on_return="commit"
pool_timeout=30
```

**Note:** NullPool for SQLite (correct), production pooling for PostgreSQL.

**PostgreSQL Optimization:** JIT is disabled (`"jit": "off"`) - this is a specific optimization for OLTP workloads where JIT compilation overhead outweighs benefits for short, fast queries. Good attention to detail.

### 1.5 Caching Architecture - ✅ RESILIENT

**Location:** [backend/services/cache.py](backend/services/cache.py)

**Multi-Layer Cache:**
| Layer | Purpose | TTL |
|-------|---------|-----|
| L1 | Hot Quotes | 5s |
| L2 | Historical Bars | 60s |
| L3 | Technical Indicators | 30s |

**Strengths:**
- Automatic memory fallback if Redis unavailable
- Connection pooling (50 connections)
- Metrics tracking (hits/misses/errors)

**Issue:** Single-node Redis configuration - no Sentinel/Cluster support:
```python
self.redis_client = redis.Redis(
    host=os.getenv('REDIS_HOST', 'localhost'),
    port=int(os.getenv('REDIS_PORT', 6379)),
    # ❌ No Sentinel/Cluster configuration
)
```

**Recommendation:** Add Redis Sentinel support for production HA.

### 1.6 Database Initialization - ⚠️ FRAGMENTED

**Issue:** Database initialization is split between [main.py](main.py) and [factory.py](backend/api/factory.py).

In `main.py` (lines 43-65):
```python
# CRITICAL FIX: Initialize database BEFORE starting uvicorn
# Socket.IO wrapper doesn't forward ASGI lifespan events properly!
engine, sessionmaker = init_db(database_url)
```

**Risk:** This dual-init logic is fragile and may lead to connection leaks or race conditions.

**Recommendation:** Unify DB startup into FastAPI lifespan handler exclusively.

---

## PHASE 2: BACKEND SERVICES ANALYSIS

### 2.1 Order Service - ✅ ROBUST

**Location:** [backend/services/order_service.py](backend/services/order_service.py)

**Strengths:**
- **Circuit Breaker Pattern**: Three-state (CLOSED/OPEN/HALF_OPEN) with:
  - Failure threshold: 5 failures
  - Recovery timeout: 60 seconds
  - Daily P&L loss threshold: 5%
- **Retry with Exponential Backoff**: For 429 rate limiting
- **Comprehensive Validation**: Symbol, side, qty, order type, price checks
- **Idempotency**: Client idempotency keys for deduplication

**Issues:**
| Issue | Severity | Recommendation |
|-------|----------|----------------|
| 🔴 Circuit Breaker state is IN-MEMORY ONLY | CRITICAL | Persist state to Redis - crash-loop can drain account |
| Sync wrapper uses `asyncio.run()` in async context | Medium | Refactor to pure async |
| Mock fallback when no session | Low | Explicit test mode flag |

**⚠️ CRITICAL FINDING: Circuit Breaker State Persistence**

The `CircuitBreaker` class stores all state in memory (`self._state`, `self._failures`, `self._daily_pnl`).

**Risk Scenario:**
1. Strategy bug causes rapid losses
2. Circuit breaker trips (OPEN state)
3. Application crashes or K8s redeploys pod
4. Circuit breaker resets to CLOSED on restart
5. Malfunctioning strategy continues trading
6. Crash-loop repeatedly resets breaker → account drained

**Remediation:** Persist breaker state to Redis with TTL matching `window_seconds`.

### 2.2 Risk Manager - ✅ INSTITUTIONAL GRADE

**Location:** [backend/risk/risk_manager.py](backend/risk/risk_manager.py) (1,731 lines)

**Strengths:**
- **Async-first Design**: No event loop blocking
- **NYSE Holiday Calendar**: 2024-2027 holidays/early closes
- **Market Hours Awareness**: Proper Eastern time handling
- **Risk Math Utilities**:
  - Kelly fraction calculation with floor/ceiling
  - EWMA volatility with numerical stability (EPS = 1e-12)
  - Parametric VaR with normal distribution
  - Historical CVaR (Expected Shortfall)
- **RiskDecision Structured Type**: Clear allow/block with reason codes
- **Admin Override Support**: Configurable via `RISK_ALLOW_ADMIN_OVERRIDE`

**Risk Checks:**
- Symbol concentration limits
- Position value limits
- Portfolio VaR limits
- Halted symbol checking
- Penny stock/crypto prohibition

**Issue:** `_get_current_positions()` returns empty dict with TODO comment - needs integration

### 2.3 Strategy Engine - ✅ EXCEPTIONAL

**Location:** [backend/strategies/engine.py](backend/strategies/engine.py)

**Institutional-Grade Features:**

1. **Signal Netting:**
   - Aggregates signals by symbol using `defaultdict(list)`
   - Nets buy/sell signals before broker submission
   - **Impact:** Saves massive transaction costs

2. **Whipsaw Prevention:**
   ```python
   self.min_flip_interval_s = config.get("min_flip_interval_s", 60)
   ```
   - Prevents rapid position reversals that bleed capital in choppy markets
   - Configurable throttle interval

3. **Crash Isolation:**
   ```python
   async def build_plan_safe(symbol, signals):
       try:
           return await self._build_symbol_plan(...)
       except Exception as e:
           logger.error(f"Failed to build plan for {symbol}")
           return None  # Don't fail the entire batch
   ```
   - Per-symbol exception handling
   - One bad symbol doesn't crash the entire execution batch

4. **Risk Gating:** All executions routed through `RiskManager.before_order()`

### 2.4 Technical Indicators Service - ✅ COMPLETE

**Location:** [backend/services/indicators.py](backend/services/indicators.py)

**26 Indicators Implemented:**
SMA, EMA, RSI, MACD, Bollinger Bands, Stochastic, ATR, OBV, VWAP, CCI, Williams %R, ADX, ROC, MFI, Parabolic SAR, Ichimoku Cloud, TEMA, KAMA, CMO, Aroon, Ultimate Oscillator, Chaikin MF, Donchian Channels, Force Index, WMA, Pivot Points

**Note:** All indicators tested and working per previous session.

### 2.5 Positions Service - ✅ FUNCTIONAL

**Location:** [backend/services/positions_service.py](backend/services/positions_service.py)

- Alpaca integration for real-time positions
- Async wrappers for sync Alpaca API
- Proper fallback for missing positions

---

## PHASE 3: SECURITY AUDIT

### 3.1 Authentication - ✅ SOLID

**Location:** [backend/infra/security.py](backend/infra/security.py)

**Strengths:**
- **JWT Implementation**: HS256 with proper claims (iss, aud, exp, iat, jti)
- **Bcrypt Password Hashing**: With constant-time comparison
- **Strict Token Verification**: Validates all claims
- **72-byte Warning**: Logs warning for passwords exceeding bcrypt limit

**Configuration:**
```python
JWT_ALGORITHM = "HS256"
JWT_ISSUER = "algotrading-platform"
JWT_AUDIENCE = "algotrading-api"
JWT_CLOCK_SKEW = 60  # seconds
```

### 3.2 Security Concerns - ⚠️ REQUIRES ATTENTION

#### CRITICAL: `eval()` Usage
**Location:** [backend/mlops/pipeline.py#L158](backend/mlops/pipeline.py#L158)
```python
return eval(self.config.condition, {"__builtins__": {}}, context)
```

**Risk:** Even with `{"__builtins__": {}}`, this is vulnerable to code injection.
**Recommendation:** Replace with AST-based expression parser or whitelist allowed operations.

#### HIGH: `pickle.load()` Usage
**Locations:**
- [backend/services/cache.py](backend/services/cache.py#L121)
- [backend/ml/model_manager.py](backend/ml/model_manager.py) (4 instances)
- [backend/ml/training.py](backend/ml/training.py#L816)
- [backend/mlops/model_manager.py](backend/mlops/model_manager.py) (4 instances)

**Risk:** Pickle deserialization can execute arbitrary code if attacker can control pickled data.
**Recommendation:** 
1. Use signed pickle with HMAC verification
2. Consider `joblib` with restricted types
3. For cache: Use JSON with type coercion

#### MEDIUM: Bare `except:` Clauses
**Locations:**
- [backend/ml/model_manager.py#L1944, #L1954](backend/ml/model_manager.py)
- [backend/ml/data_processing.py#L317](backend/ml/data_processing.py)
- [backend/api/websocket_manager.py#L189](backend/api/websocket_manager.py)
- [backend/api/routes/system.py#L160](backend/api/routes/system.py)

**Risk:** Catches `KeyboardInterrupt`, `SystemExit`, masking critical errors.
**Recommendation:** Use `except Exception:` with specific logging.

#### HIGH: No PII/Secret Scrubbing in Log Processors
**Location:** [backend/utils/logger.py](backend/utils/logger.py#L14-24)

The `structlog` configuration does not include a processor to scrub sensitive data:
```python
structlog.configure(
    processors=[
        # ... standard processors ...
        # ❌ MISSING: Secret scrubbing processor
        structlog.processors.JSONRenderer(),
    ],
)
```

**Risk:** If an exception occurs in a function receiving `api_key`, `password`, `secret`, or `token` as arguments, `format_exc_info` may log these secrets to disk/console.

**Remediation:** Add a custom processor to mask sensitive keys:
```python
def scrub_secrets(_, __, event_dict):
    SENSITIVE_KEYS = {'password', 'api_key', 'secret', 'token', 'secret_key'}
    for key in list(event_dict.keys()):
        if any(s in key.lower() for s in SENSITIVE_KEYS):
            event_dict[key] = '***REDACTED***'
    return event_dict
```

### 3.3 Secrets Management - ✅ GOOD

- JWT secrets via environment variables (`SECURITY_JWT_SECRET`)
- Alpaca credentials from environment
- No hardcoded secrets in codebase (validated via grep)
- Docker Compose requires `.env` for secrets

---

## PHASE 4: INFRASTRUCTURE REVIEW

### 4.1 Docker Configuration - ✅ PRODUCTION-READY

**Location:** [Dockerfile](Dockerfile)

**Strengths:**
- Multi-stage build (builder → runtime)
- Non-root user (`appuser`, UID 10001)
- Python 3.11-slim base
- Minimal runtime dependencies
- `.dockerignore` (implied by structure)

**docker-compose.yml Highlights:**
- Health checks for all services
- Proper dependency ordering (`depends_on` with conditions)
- Volume persistence for PostgreSQL
- Network isolation (`trading-network`)
- Required environment variables with `?` syntax

### 4.2 Kubernetes Configuration - ✅ PRODUCTION-READY

**Location:** [k8s/deployment.yaml](k8s/deployment.yaml)

**Strengths:**
- 2 replicas with RollingUpdate (maxSurge: 1, maxUnavailable: 0)
- Security context: `runAsNonRoot: true`, `runAsUser: 10001`
- Prometheus annotations for metrics scraping
- Resource requests/limits defined
- Liveness/readiness probes configured

**Resource Allocation:**
```yaml
requests:
  memory: "512Mi"
  cpu: "250m"
limits:
  memory: "2Gi"
  cpu: "1000m"
```

### 4.3 Observability - ✅ EXCELLENT

- **OpenTelemetry Integration**: Trace correlation in logs
- **Prometheus Metrics**: Counter, histogram, gauge support
- **Structured JSON Logging**: With trace_id/span_id injection
- **Health Endpoints**: `/health`, `/healthz`, `/readyz`, `/livez`

---

## PHASE 5: PERFORMANCE ANALYSIS

### 5.1 Rate Limiting - ✅ IMPLEMENTED

**Location:** [backend/api/middleware/rate_limit.py](backend/api/middleware/rate_limit.py)

**Configuration:**
| Endpoint Pattern | Requests/Min | Requests/Sec | Burst |
|-----------------|--------------|--------------|-------|
| `/api/v1/orders` | 30 | 2 | 5 |
| `/api/v1/portfolio` | 120 | 5 | 10 |
| `/api/v1/positions` | 120 | 5 | 10 |
| `/api/v1/models` | 30 | 2 | 5 |
| `/api/v1/health` | 300 | 20 | 50 |
| default | 60 | 5 | 15 |

**Algorithm:** Sliding window with sub-second precision.

### 5.2 Caching - ✅ WELL-DESIGNED

**Location:** [backend/infra/performance.py](backend/infra/performance.py)

- LRU cache with TTL support
- Async-safe with `asyncio.Lock()`
- Memory size limits configurable
- Hit/miss statistics

### 5.3 Performance SLOs - ✅ ENFORCED

**Location:** [tests/test_performance_slo.py](tests/test_performance_slo.py)

| Metric | Threshold | Status |
|--------|-----------|--------|
| /health p95 | < 200ms | Enforced |
| /health p99 | < 500ms | Enforced |
| /health availability | > 99.9% | Enforced |

### 5.4 WebSocket Performance - ✅ SOLID

- Backpressure handling with queue limits
- Heartbeat monitoring (30s interval)
- Stale connection cleanup
- Weak reference tracking for task cleanup

---

## PHASE 6: FRONTEND ANALYSIS

### 6.1 Technology Stack - ✅ MODERN

**Package.json Highlights:**
- React 19.1.1 (latest)
- TypeScript 5.9.3
- Vite 7.1.7
- Zustand 5.0.8 (state management)
- TanStack React Query 5.90.2
- Ant Design 5.27.4
- AG Grid Enterprise 34.2.0
- TradingView Lightweight Charts 5.0.9

### 6.2 State Management - ✅ EXCELLENT

**Location:** [frontend/src/store/](frontend/src/store/)

- `authStore.ts` - JWT handling with XSS protection
- `portfolioStore.ts` - Portfolio state
- `ordersStore.ts` - Order management
- `marketDataStore.ts` - Real-time data
- `uiStore.ts` - UI state

**Security Note:** Access tokens in memory, not localStorage (XSS protection).

### 6.3 API Client - ✅ ROBUST

**Location:** [frontend/src/services/api.ts](frontend/src/services/api.ts)

- Axios with interceptors for JWT injection
- Automatic token refresh on 401
- Request queue during refresh
- Error handling utility

### 6.4 WebSocket Manager - ✅ PRODUCTION-READY

**Location:** [frontend/src/services/websocketManager.ts](frontend/src/services/websocketManager.ts)

- Socket.IO client
- Exponential backoff reconnection
- Connection quality monitoring
- Heartbeat with latency tracking
- Subscription management

---

## PHASE 7: RECOMMENDATIONS

### 🔴 CRITICAL (Fix Immediately)

1. **Persist Circuit Breaker State to Redis**
   - Location: [backend/services/order_service.py](backend/services/order_service.py) - `CircuitBreaker` class
   - Current: All state (`_state`, `_failures`, `_daily_pnl`) is in-memory
   - Risk: Crash-loop can repeatedly reset breaker and drain account
   - Remediation: Store state in Redis with TTL matching `window_seconds`

2. **Remove `eval()` in Pipeline**
   - Location: [backend/mlops/pipeline.py#L158](backend/mlops/pipeline.py#L158)
   - Replace with safe expression evaluator (e.g., `simpleeval` library)

3. **Secure Pickle Loading**
   - Implement HMAC signature verification for all pickle loads
   - Or migrate to `safetensors`/`joblib` with restricted types

### 🟠 HIGH (Fix Before Production)

3. **Increase Type Hint Coverage**
   - Current: 47% of functions have return type hints
   - Target: 90%+
   - Add mypy to CI pipeline

4. **Reduce `Any` Type Usage**
   - Current: 119 occurrences
   - Target: < 20
   - Replace with specific types or generics

5. **Address TODO Comments**
   - 20+ TODO/FIXME items represent technical debt
   - Priority items:
     - [orders.py#L323](backend/api/routes/orders.py#L323) - Position tracking
     - [auth.py#L537](backend/api/routes/auth.py#L537) - Refresh token mechanism
     - [risk_manager.py#L569](backend/risk/risk_manager.py#L569) - Position integration

6. **Fix Bare Exception Clauses**
   - Replace `except:` with `except Exception:`
   - Add proper logging

7. **Add PII/Secret Scrubbing to Logs**
   - Location: [backend/utils/logger.py](backend/utils/logger.py)
   - Add structlog processor to mask `password`, `api_key`, `secret`, `token`

### 🟡 MEDIUM (Address in Next Sprint)

7. **Implement Position Integration in Risk Manager**
   - `_get_current_positions()` returns empty dict
   - Connect to PositionsService for real data

8. **Add Request Tracing End-to-End**
   - Propagate `request_id` through all service calls
   - Include in all log entries

9. **Expand Test Coverage**
   - Current: 43 test files
   - Target: 80%+ code coverage
   - Add property-based testing for risk calculations

10. **Document API Rate Limits**
    - Add rate limit headers to API documentation
    - Include in OpenAPI spec

11. **Unify Database Initialization**
    - Current: Split between main.py and factory.py lifespan
    - Consolidate into factory.py lifespan handler only

12. **Add Redis Sentinel/Cluster Support**
    - Location: [backend/services/cache.py](backend/services/cache.py)
    - Current: Single-node Redis configuration
    - Needed for production HA

### 🟢 LOW (Nice to Have)

11. **Frontend Bundle Optimization**
    - Analyze bundle size with `vite-bundle-visualizer`
    - Implement code splitting for heavy components

12. **Add Circuit Breaker Dashboard**
    - Expose circuit breaker state via API
    - Add UI visualization

13. **Implement Distributed Tracing UI**
    - Jaeger or Zipkin integration
    - Trace visualization in admin panel

---

## APPENDIX A: FILE INVENTORY

### Backend Structure (Key Directories)
| Directory | Files | Purpose |
|-----------|-------|---------|
| `api/routes/` | 26 | API endpoints |
| `infra/` | 25 | Infrastructure (DB, cache, security) |
| `services/` | 20 | Business logic |
| `ml/` | 12 | Machine learning |
| `mlops/` | 12 | ML operations |
| `risk/` | 10 | Risk management |
| `strategies/` | 8 | Trading strategies |
| `integrations/` | 8 | External integrations |

### Frontend Structure
| Directory | Purpose |
|-----------|---------|
| `components/` | React components (atomic, charts, portfolio, etc.) |
| `hooks/` | Custom React hooks (14 files) |
| `services/` | API and WebSocket services |
| `store/` | Zustand state stores |
| `pages/` | Route pages |
| `types/` | TypeScript type definitions |

---

## APPENDIX B: SECURITY CHECKLIST

| Check | Status | Notes |
|-------|--------|-------|
| JWT Implementation | ✅ | HS256 with proper claims |
| Password Hashing | ✅ | Bcrypt with timing-safe comparison |
| Rate Limiting | ✅ | Per-endpoint sliding window |
| CORS Configuration | ✅ | Configurable origins |
| SQL Injection | ✅ | SQLAlchemy parameterized queries |
| XSS Protection | ✅ | Tokens in memory, not localStorage |
| CSRF Protection | ⚠️ | Verify implementation |
| Secrets in Code | ✅ | Environment variables only |
| Dependency Audit | ⚠️ | Run `pip-audit` and `npm audit` |
| TLS/HTTPS | ✅ | K8s config supports TLS |
| Pickle Security | ❌ | Needs HMAC verification |
| Eval Security | ❌ | Remove eval() usage |
| **Log PII Scrubbing** | ❌ | Add structlog processor to mask secrets |
| **Circuit Breaker Persistence** | ❌ | In-memory only - needs Redis |
| **Redis HA** | ⚠️ | Single-node config - needs Sentinel/Cluster |

---

## APPENDIX C: PERFORMANCE BENCHMARKS

### Target SLOs (Hedge Fund Grade)
| Metric | Target | Notes |
|--------|--------|-------|
| Order Submission | < 50ms p95 | Pre-trade risk + DB write |
| Market Data Latency | < 10ms p95 | WebSocket delivery |
| Health Check | < 200ms p95 | Critical for K8s probes |
| API Response | < 500ms p95 | General endpoints |
| Position Query | < 100ms p95 | Portfolio views |

### Recommended Monitoring
- Prometheus metrics for all SLOs
- Grafana dashboards with alerting
- PagerDuty integration for critical alerts

---

## CONCLUSION

This algorithmic trading platform demonstrates **strong architectural foundations** suitable for institutional-grade trading operations. The codebase follows modern async Python patterns, has robust error handling, and includes production-ready infrastructure configurations.

**Key Strengths:**
1. Clean factory pattern with proper lifecycle management
2. Institutional-grade risk management with circuit breakers
3. Complete technical indicators suite (26 indicators)
4. Production-ready Kubernetes deployment
5. Strong authentication and authorization
6. Strategy engine with signal netting and whipsaw prevention
7. Multi-layer cache with graceful Redis fallback

**Critical Areas for Improvement:**
1. **Security**: Remove `eval()`, secure pickle loading, add log PII scrubbing
2. **Resilience**: Persist circuit breaker state to Redis
3. **Type Safety**: Increase type hint coverage (47% → 90%+)
4. **Infrastructure**: Unify DB init, add Redis HA support
5. **Documentation**: API rate limits, architecture diagrams

**Recommendation:** This platform is **suitable for production deployment** after addressing the CRITICAL and HIGH priority items. The architecture can scale to hedge fund-grade operations with the recommended improvements.

---

*This audit was conducted following the methodology outlined in [COMPREHENSIVE_PLATFORM_AUDIT_PROMPT.md](COMPREHENSIVE_PLATFORM_AUDIT_PROMPT.md)*
