# System Architecture Overview

## Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| API Server | FastAPI + Uvicorn | Async HTTP/WebSocket server |
| Frontend | React 19 + TypeScript + Vite | Trading UI |
| Database | PostgreSQL (asyncpg) | Persistent storage |
| Cache | Redis | Session store, rate limiting, token blacklist |
| Broker | Alpaca (alpaca-py) | Order execution, market data, streaming |
| ML | XGBoost, scikit-learn, TensorFlow, PyTorch | Signal generation |
| WebSocket | Socket.IO | Real-time UI updates |
| Observability | OpenTelemetry + Prometheus | Metrics, tracing |

## High-Level Architecture

```
┌─────────────┐     ┌─────────────────────────────────────────────┐
│  React UI   │◄───►│  FastAPI Backend (localhost:8000)            │
│  :5173      │ WS  │                                             │
└─────────────┘     │  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
                    │  │ API      │  │ Services │  │ Organism │  │
                    │  │ Routes   │─►│ Layer    │─►│ Engine   │  │
                    │  └──────────┘  └──────────┘  └──────────┘  │
                    │       │             │              │         │
                    │  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
                    │  │ Security │  │ Risk     │  │ ML       │  │
                    │  │ (JWT)    │  │ Manager  │  │ Pipeline │  │
                    │  └──────────┘  └──────────┘  └──────────┘  │
                    │       │             │              │         │
                    │  ┌──────────────────────────────────────┐   │
                    │  │  PostgreSQL + Redis + Alpaca API     │   │
                    │  └──────────────────────────────────────┘   │
                    └─────────────────────────────────────────────┘
```

## Backend Package Structure

| Package | Purpose |
|---------|---------|
| `backend/api/` | FastAPI routes, middleware, schemas, factory |
| `backend/services/` | Business logic (orders, portfolio, risk, backtest) |
| `backend/organism/` | Living Organism — self-evolving trading brain |
| `backend/strategies/` | 12 trading strategies + engine |
| `backend/ml/` | ML pipeline (training, prediction, validation, drift) |
| `backend/risk/` | Risk calculations (VaR, CVaR, position limits) |
| `backend/integrations/` | Alpaca broker, data, streaming |
| `backend/infra/` | Database, security, logging, metrics, guardrails |
| `backend/config/` | Pydantic-based settings |
| `backend/models/` | SQLAlchemy ORM models |

## Canonical Paths

### Configuration
```python
from backend.config.settings import get_settings
settings = get_settings()  # Pydantic BaseSettings, cached
```

### Database
```python
# FastAPI route dependency
from backend.infra.db import get_db_session
async def route(session: AsyncSession = Depends(get_db_session)): ...

# Standalone async context
from backend.infra.db import get_session_context
async with get_session_context() as session: ...
```

### Authentication
```python
from backend.infra.security import get_authenticated_user, require_admin
# JWT Bearer auth on all protected routes
# require_admin for organism control endpoints
```

## Request Flow

1. **HTTP Request** → FastAPI middleware (CORS, rate limit, dedup, metrics)
2. **Auth** → JWT Bearer token validated → user extracted
3. **Route Handler** → calls service layer
4. **Service** → business logic → database queries → broker calls
5. **Response** → Pydantic serialization → JSON response

## Order Pipeline

```
Signal/User → OrderService.create_order()
  → Pre-trade validation (symbol, qty, type)
  → Risk check (position limits, drawdown, exposure)
  → Outbox insert (idempotent, transactional)
  → OutboxWorker picks up → Alpaca broker submit
  → WebSocket stream receives fill → DB update → UI notification
```

## Living Organism Tick Loop

Every 60 seconds (when `ORGANISM_ENABLED=1`):

1. **Data Fetch** — Historical bars from Alpaca for universe
2. **Feature Engineering** — 95 features per symbol
3. **Regime Detection** — Market regime classification
4. **ML Signal** — If promoted model exists, generate signals
5. **Exit Check** — Evaluate existing positions for exit conditions
6. **Order Submission** — Place orders through risk-checked pipeline
7. **Brain Persistence** — Save state atomically
8. **WebSocket Broadcast** — `organism_tick` event to connected clients

## Frontend Structure

| Feature Module | Purpose |
|---------------|---------|
| `features/dashboard/` | Main dashboard with portfolio overview |
| `features/organism/` | Living Organism control panel |
| `features/trading/` | Order entry, pre-trade checks |
| `features/orders/` | Order management, history |
| `features/positions/` | Position tracking |
| `features/portfolio/` | Portfolio analytics |
| `features/strategies/` | Strategy management, builder |
| `features/backtesting/` | Backtest setup, results |
| `features/ml-models/` | ML model comparison |
| `features/risk/` | Risk dashboard, kill switch |
| `features/trades/` | Trade history, analytics |

## Security

- **Authentication:** JWT with bcrypt password hashing (12-char minimum)
- **Authorization:** Role-based (admin, trader, viewer)
- **Token Revocation:** Redis-backed blacklist with in-memory fallback
- **Rate Limiting:** Per-IP rate limiting on sensitive endpoints
- **CORS:** Locked to specific origins
- **Input Validation:** Pydantic models on all endpoints
- **Secure Deserialization:** HMAC-verified pickle for ML models

## Deployment

| Mode | Command |
|------|---------|
| Development | `python main.py` + `cd frontend && npm run dev` |
| Paper Trading | `docker-compose -f docker-compose.paper.yml up` |
| Production | `docker-compose -f docker-compose.production.yml up` |
| Kubernetes | `kubectl apply -f k8s/deployment.yaml` |
