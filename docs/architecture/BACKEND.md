# Backend Architecture Analysis Report

**Analysis Date:** January 17, 2026  
**Scope:** Complete backend codebase review  
**Analyzed Components:** API, Services, Infrastructure, Risk, ML, Database, Integrations

---

## 1. Architecture Overview

### 1.1 High-Level Structure

The platform follows a **layered architecture** with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────────────┐
│                     API Layer (FastAPI)                          │
│  ├── factory.py (Application factory pattern)                   │
│  ├── routes/ (REST endpoints)                                   │
│  ├── socketio_server.py (Real-time WebSocket)                   │
│  └── dependencies.py (DI via FastAPI Depends)                   │
├─────────────────────────────────────────────────────────────────┤
│                     Service Layer                                │
│  ├── order_service.py, portfolio_service.py                     │
│  ├── strategy_service.py, backtest_service.py                   │
│  └── Business logic, orchestration                              │
├─────────────────────────────────────────────────────────────────┤
│                  Infrastructure Layer (infra/)                   │
│  ├── db.py (Async PostgreSQL with SQLAlchemy 2.0)               │
│  ├── repositories/ (Data access layer)                          │
│  ├── security.py (JWT authentication, RBAC)                     │
│  ├── outbox.py (Transactional outbox pattern)                   │
│  ├── cache.py (In-memory TTL cache)                             │
│  └── observability.py (OpenTelemetry, Prometheus)               │
├─────────────────────────────────────────────────────────────────┤
│                    Domain Modules                                │
│  ├── risk/ (Risk management, VaR, Kelly)                        │
│  ├── ml/ (Model registry, drift detection)                      │
│  ├── strategies/ (Strategy engine, signal processing)           │
│  └── integrations/ (Alpaca broker, market data)                 │
├─────────────────────────────────────────────────────────────────┤
│                    Data Layer                                    │
│  ├── infra/schemas.py (SQLAlchemy 2.0 models)                   │
│  ├── infra/repositories/ (Repository pattern)                   │
│  └── PostgreSQL (async via asyncpg)                             │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 Application Entry Points

1. **[main.py](../main.py)** - Production entry point with database pre-initialization
2. **[backend/api/factory.py](../backend/api/factory.py)** - Application factory with lifespan management
3. **[backend/api/main.py](../backend/api/main.py)** - FastAPI app creation with OpenAPI configuration

### 1.3 Key Design Patterns Identified

| Pattern | Implementation | Location |
|---------|---------------|----------|
| **Factory Pattern** | `create_app()` function | [factory.py](../backend/api/factory.py) |
| **Repository Pattern** | `OrdersRepo`, `PositionsRepo`, etc. | [infra/repositories/](../backend/infra/repositories/) |
| **Service Layer** | Business logic encapsulation | [services/](../backend/services/) |
| **Dependency Injection** | FastAPI `Depends()` | [dependencies.py](../backend/api/dependencies.py) |
| **Outbox Pattern** | Exactly-once side effects | [outbox.py](../backend/infra/outbox.py) |
| **Strategy Pattern** | Risk decision strategies | [risk_manager.py](../backend/risk/risk_manager.py) |

---

## 2. Strengths Identified

### 2.1 Async-First Architecture ✅

**Excellent async/await implementation throughout:**

```python
# Example from infra/db.py - proper session lifecycle
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    session = _sessionmaker()
    try:
        with trace_span("database_session"):
            yield session
            await session.commit()
    except Exception as e:
        await session.rollback()
        raise
    finally:
        await session.close()
```

- All database operations use `AsyncSession`
- HTTP client (`httpx.AsyncClient`) for broker integration
- Proper connection pooling with pre-warming

### 2.2 Comprehensive Observability ✅

**Full OpenTelemetry + Prometheus stack:**

- Distributed tracing with spans
- Prometheus metrics for latency, throughput
- Structured logging with `structlog`
- Database operation telemetry

```python
# From observability.py
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
```

### 2.3 Robust Repository Pattern ✅

**Clean data access abstraction:**

```python
# From infra/repositories/orders.py
class OrdersRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert_by_idempotency(self, *, client_key: str, ...) -> Order:
        # Idempotency protection
        stmt = select(Order).where(Order.client_idempotency_key == client_key)
        existing_order = result.scalar_one_or_none()
        if existing_order:
            return existing_order
        # Create new order...
```

- Idempotency handling at repository level
- Proper error types (`OrderNotFoundError`, `DuplicateOrderError`)
- Transaction-aware operations

### 2.4 Transactional Outbox Pattern ✅

**Exactly-once delivery guarantee for broker submissions:**

```python
# From outbox.py
class OutboxRepo:
    async def enqueue(self, *, topic: str, payload: dict) -> uuid.UUID:
        event = OutboxEvent(topic=topic, payload=payload, status="pending")
        session.add(event)
        await session.flush()
        return event.id

    async def claim_batch(self, *, limit: int = 100) -> list[OutboxEvent]:
        # FOR UPDATE SKIP LOCKED for concurrency safety
        stmt = select(OutboxEvent).where(...).with_for_update(skip_locked=True)
```

### 2.5 Institutional-Grade Risk Management ✅

**Comprehensive risk controls:**

- Kelly Criterion position sizing
- VaR/CVaR calculations with numerical stability
- Symbol concentration limits
- Circuit breaker mechanism
- Admin override capability with audit logging

```python
# From risk_manager.py
class RiskMathUtils:
    @staticmethod
    def kelly_fraction(mean_return: float, variance: float, ...) -> float:
        if variance < EPS or mean_return <= 0:
            return kelly_floor
        kelly = mean_return / variance
        return max(kelly_floor, min(kelly, kelly_ceiling))
```

### 2.6 Modern SQLAlchemy 2.0 Models ✅

**Clean, typed ORM models:**

```python
# From infra/schemas.py
class Order(Base):
    __tablename__ = "orders"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    client_idempotency_key: Mapped[str] = mapped_column(String(255), unique=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    qty: Mapped[Decimal] = mapped_column(DECIMAL(18, 6), nullable=False)
    
    __table_args__ = (
        Index("ix_orders_symbol_status", "symbol", "status"),
    )
```

### 2.7 Centralized Router Architecture ✅

**Clean route organization with authentication:**

```python
# From factory.py
api_router = APIRouter(prefix="/api/v1")
protected = APIRouter(dependencies=[Depends(get_authenticated_user)])

# Public routes
api_router.include_router(auth_router)
# Protected routes
protected.include_router(orders_router)
protected.include_router(portfolio_router)
api_router.include_router(protected)
```

### 2.8 JWT Security Implementation ✅

**Strict JWT verification with proper claims:**

```python
# From security.py
def verify_jwt(token: str, *, secret: str, issuer: str, audience: str) -> dict:
    verified_payload = jwt.decode(
        token, secret, algorithms=[alg],
        options={
            "verify_signature": True,
            "verify_exp": True,
            "verify_iss": True,
            "verify_aud": True,
        },
        issuer=issuer,
        audience=audience
    )
```

---

## 3. Weaknesses and Issues Found

### 3.1 Mock Imports in Production Code ⚠️ HIGH

**Issue:** `unittest.mock` imports exist in production code paths.

**Locations:**
- [backend/api/main.py#L71](../backend/api/main.py#L71) - `from unittest.mock import Mock`
- [backend/services/order_service.py#L59](../backend/services/order_service.py#L59) - Mock fallback in init
- [backend/api/portfolio.py#L181](../backend/api/portfolio.py#L181) - Runtime mock imports

**Impact:** 
- Potential runtime instability
- Unclear behavior in production
- Code smell indicating incomplete dependency injection

**Recommendation:** Implement proper null object pattern or factory methods instead of runtime mocking.

### 3.2 Incomplete TODO/FIXME Items ⚠️ MEDIUM

**20+ TODO comments indicate unfinished features:**

| Location | Issue |
|----------|-------|
| [auth.py#L540](../backend/api/routes/auth.py#L540) | "Implement proper refresh token mechanism" |
| [auth.py#L582](../backend/api/routes/auth.py#L582) | Password reset not implemented |
| [positions.py#L69](../backend/api/routes/positions.py#L69) | "Implement actual Alpaca API integration" |
| [portfolio_service.py#L232](../backend/services/portfolio_service.py#L232) | Historical data not implemented |
| [orders.py#L1257](../backend/api/routes/orders.py#L1257) | Order modification not implemented |

### 3.3 Stub Database Models ⚠️ HIGH

**Issue:** [backend/database/models.py](../backend/database/models.py) contains MockModel stubs instead of real models.

```python
# This should NOT be in production code
class MockModel:
    """Mock database model for testing"""
    def __init__(self, *args, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
```

**Impact:** Confusion about which models are canonical (real models are in `infra/schemas.py`).

### 3.4 Duplicate Configuration Systems ⚠️ MEDIUM

**Issue:** Multiple configuration approaches coexist:

- [backend/config/settings.py](../backend/config/settings.py) - Dataclass-based settings
- [backend/config/base_settings.py](../backend/config/base_settings.py) - Pydantic settings
- [backend/config/__init__.py](../backend/config/__init__.py) - Import shims

**Recommendation:** Consolidate to single Pydantic settings implementation.

### 3.5 Compatibility Shims in `__init__.py` ⚠️ LOW

**Issue:** [backend/__init__.py](../backend/__init__.py) contains extensive module-level import shims:

```python
# Creates fake modules for backward compatibility
settings_module = types.ModuleType('backend.config.settings')
sys.modules['backend.config.settings'] = settings_module
```

**Impact:** Hard to maintain, hides actual module structure.

### 3.6 Inconsistent Error Handling ⚠️ MEDIUM

**Issue:** Mixed approaches to error handling:

- Some routes use `APIError` exceptions
- Some use `HTTPException` directly
- Some services swallow exceptions and return dicts

**Good pattern (should be consistent):**
```python
# From errors.py
class RiskError(APIError):
    def __init__(self, message: str, issues: list[str] = None):
        super().__init__(
            code=ErrorCodes.RISK_LIMIT_EXCEEDED,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
```

### 3.7 Long Methods in Factory ⚠️ LOW

**Issue:** [factory.py](../backend/api/factory.py) is 1203 lines with `create_app()` being ~1000 lines.

**Recommendation:** Extract lifespan logic, router registration, and middleware setup into separate functions.

### 3.8 Missing Type Hints in Some Areas ⚠️ LOW

**Generally good coverage, but gaps exist:**

```python
# From some service methods
def submit_order(self, order_data: dict[str, Any]) -> dict[str, Any]:  # ✅ Good
    
# But some return types are vague
async def get_positions_by_symbols(self, symbols):  # ❌ Missing return type
```

---

## 4. Specific Recommendations

### 4.1 Immediate Actions (High Priority)

#### 4.1.1 Remove Mock Imports from Production
```python
# BEFORE (bad)
from unittest.mock import AsyncMock
self.orders_repo = self.orders_repo or AsyncMock()

# AFTER (good)
class NullOrdersRepo:
    """Null object for when repository is not configured"""
    async def upsert_by_idempotency(self, **kwargs):
        raise RuntimeError("OrdersRepo not configured")

self.orders_repo = self.orders_repo or NullOrdersRepo()
```

#### 4.1.2 Consolidate Configuration
```python
# Single settings.py with Pydantic
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    alpaca_api_key: str
    jwt_secret: str
    
    class Config:
        env_file = ".env"

# Use everywhere
settings = Settings()
```

#### 4.1.3 Delete Stub Models
- Delete [backend/database/models.py](../backend/database/models.py)
- Update imports to use [backend/infra/schemas.py](../backend/infra/schemas.py)

### 4.2 Short-Term Improvements (Medium Priority)

#### 4.2.1 Implement Missing Auth Features
Priority order:
1. Token refresh mechanism
2. Password reset flow
3. Account lockout after failed attempts

#### 4.2.2 Standardize Error Handling
Create domain-specific exceptions:
```python
# backend/domain/exceptions.py
class TradingException(Exception):
    """Base exception for trading domain"""
    pass

class InsufficientFundsError(TradingException):
    pass

class SymbolNotFoundError(TradingException):
    pass
```

#### 4.2.3 Refactor Factory Pattern
```python
# backend/api/factory.py
def create_app(settings=None) -> FastAPI:
    app = FastAPI(title="Trading Platform", lifespan=create_lifespan())
    
    configure_middleware(app)
    configure_routes(app)
    configure_error_handlers(app)
    
    return app

# Separate files
# backend/api/lifespan.py
# backend/api/middleware.py
# backend/api/route_config.py
```

### 4.3 Long-Term Improvements (Low Priority)

#### 4.3.1 Add Complete Type Annotations
Use `mypy --strict` to find gaps:
```bash
mypy backend/ --strict --ignore-missing-imports
```

#### 4.3.2 Implement Domain Events
Replace direct WebSocket broadcasts with domain events:
```python
class OrderFilledEvent:
    order_id: UUID
    filled_qty: Decimal
    avg_price: Decimal

# Handlers subscribe to events
@event_handler(OrderFilledEvent)
async def notify_frontend(event: OrderFilledEvent):
    await broadcast_order_update(...)
```

---

## 5. Dead Code and Unused Modules

### 5.1 Potentially Dead Code

| File | Reason |
|------|--------|
| [backend/database/models.py](../backend/database/models.py) | Mock models, real ones in `infra/schemas.py` |
| [backend/api/routes/api_v1.py](../backend/api/routes/api_v1.py) | Empty file |
| [backend/api/routes/models_old.py](../backend/api/routes/models_old.py) | Old version suffix suggests deprecated |
| [backend/ml/model_manager_stub_backup.py](../backend/ml/model_manager_stub_backup.py) | Backup suffix |
| [backend/api/main.py.backup](../backend/api/main.py.backup) | Backup file |

### 5.2 Redundant Repository Files

| File | Issue |
|------|-------|
| [backend/database/repositories/order_repository.py](../backend/database/repositories/order_repository.py) | Stub, real impl in `infra/repositories/orders.py` |
| [backend/database/repositories/execution_repository.py](../backend/database/repositories/execution_repository.py) | Not used, real impl in `infra/repositories/` |

### 5.3 Duplicate Functionality

- [backend/websocket.py](../backend/websocket.py) vs [backend/api/websocket_manager.py](../backend/api/websocket_manager.py) - Similar WebSocket management
- [backend/infra/db.py](../backend/infra/db.py) vs [backend/infra/database.py](../backend/infra/database.py) - Database connection

---

## 6. Code Quality Summary

| Category | Score | Notes |
|----------|-------|-------|
| **Architecture** | 8/10 | Clean layering, good patterns |
| **Async Usage** | 9/10 | Consistent async-first |
| **Type Coverage** | 7/10 | Good but gaps exist |
| **Error Handling** | 6/10 | Inconsistent approaches |
| **Documentation** | 5/10 | Limited inline docs |
| **Test Organization** | 7/10 | Comprehensive but scattered |
| **Dependencies** | 7/10 | Some prod/test mixing |

### Overall Assessment: **7.2/10**

The architecture is solid with institutional-quality patterns (outbox, repository, risk management). Main improvements needed:
1. Remove mock imports from production
2. Consolidate configuration
3. Complete TODO items
4. Delete dead code

---

## 7. Appendix: File Statistics

| Directory | Files | Lines (approx) |
|-----------|-------|----------------|
| backend/api/ | 35 | ~12,000 |
| backend/services/ | 20 | ~5,000 |
| backend/infra/ | 25 | ~8,000 |
| backend/risk/ | 10 | ~4,500 |
| backend/ml/ | 12 | ~5,000 |
| backend/strategies/ | 5 | ~1,500 |
| **Total** | **107** | **~36,000** |

---

*Report generated by architecture analysis on January 17, 2026*
