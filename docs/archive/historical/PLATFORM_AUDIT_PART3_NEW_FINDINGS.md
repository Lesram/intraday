# Platform Audit — Part 3: New Findings

**Date:** 2026-02-08  
**Scope:** Frontend-backend contracts, Alembic integrity, Docker/K8s deployment, feature engineering, broker integrations, missing tests, observability gaps.  
**Exclusions:** All issues already documented in Part 1 (config systems, DB layers, DLQ loops, token blacklist, global order lock, error handling, async/sync) and Part 2 ($100 fallback, signal stub, stop-loss metadata, synthetic risk returns, $250K fallback, ML mock validation, regime tilts, no slippage, no confidence gate, strategy reinstantiation, no data freshness).

---

## 1. Frontend-Backend Contract Mismatches

### F-01 — TypeScript `StrategyType` union has syntax error (CRITICAL)
**File:** [frontend/src/types/strategy.ts](frontend/src/types/strategy.ts#L53-L54)  
**Severity:** 🔴 Critical (build-breaking)

```typescript
  | 'hybrid'
  | 'hybrid_strategy';
 | 'optuna_meta';   // ← stray semicolon on prior line makes this a dangling expression
```

Line 53 ends the union with a semicolon, then line 54 starts ` | 'optuna_meta';` which is a bare union not attached to anything. This is a **TypeScript syntax error** and will fail strict compilation. `optuna_meta` is never actually part of `StrategyType`.

**Impact:** Frontend build may break depending on tsconfig strictness. Any strategy with type `optuna_meta` will fail type checks.

---

### F-02 — Risk model schema divergence: frontend expects `user_id: string`, backend sends `user_id: int`
**File:** [frontend/src/types/risk.ts](frontend/src/types/risk.ts#L46-L47) vs [backend/models/risk.py](backend/models/risk.py#L92-L93)  
**Severity:** 🟠 High

Frontend `RiskMetric` interface declares:
```typescript
user_id: string;
```

Backend Pydantic model `RiskMetric` declares:
```python
user_id: int  # Changed from UUID to int
```

The backend sends an integer, but the frontend types expect a string. Same mismatch exists for `RiskViolation`, `RiskLimit`, `EmergencyStop` (all use `int` on backend, `string` on frontend).

**Impact:** Type assertions fail at runtime. Any code doing strict equality checks on `user_id` will silently fail.

---

### F-03 — Risk `UpdateRiskLimitRequest` missing `limit_name` field on frontend
**File:** [frontend/src/types/risk.ts](frontend/src/types/risk.ts#L98-L103) vs [backend/models/risk.py](backend/models/risk.py#L56-L58)  
**Severity:** 🟡 Medium

Frontend defines `UpdateRiskLimitRequest` WITH a `limit_name` field:
```typescript
limit_name: string;
limit_value: number;
```

But the backend `UpdateRiskLimitRequest` Pydantic model does NOT include `limit_name` — it's a path parameter (`PUT /limits/{limit_name}`), not a body field. The frontend `riskApi.ts` destructures `limit_name` from the request body and puts it in the URL path, which works — but only because of the manual destructuring in the service layer. A direct POST with the full body would send an extra field that Pydantic silently ignores.

**Impact:** Low risk due to workaround in service layer, but the type contract is misleading.

---

### F-04 — Frontend `EmergencyStop` expects fields backend doesn't send
**File:** [frontend/src/types/risk.ts](frontend/src/types/risk.ts#L82-L92) vs [backend/models/risk.py](backend/models/risk.py#L138-L152)  
**Severity:** 🟠 High

Frontend expects:
```typescript
triggered_by: string;   // Frontend expects human-readable name
```

Backend sends:
```python
triggered_by: int  # Changed from UUID to int — sends a raw user ID integer
```

Additionally, `resolved_by` has the same mismatch (`string` vs `int | None`).

**Impact:** Emergency stop UI will display raw user IDs (integers) instead of usernames.

---

### F-05 — Frontend `RiskDashboardData.summary` field mismatch
**File:** [frontend/src/types/risk.ts](frontend/src/types/risk.ts#L115-L124) vs [backend/models/risk.py](backend/models/risk.py#L161-L175)  
**Severity:** 🟡 Medium

Frontend expects `summary` as an inline object type. The backend sends `RiskDashboardSummary` which includes a `last_updated` field in `RiskDashboardData` but NOT in the summary sub-object:

```python
class RiskDashboardData(BaseModel):
    summary: RiskDashboardSummary
    last_updated: datetime  # ← This field exists in backend but NOT in frontend type
```

Frontend `RiskDashboardData` does not include `last_updated`.

**Impact:** Frontend silently drops the `last_updated` field, losing data freshness information.

---

### F-06 — Frontend `EmergencyStopEvent.type` value mismatch
**File:** [frontend/src/types/risk.ts](frontend/src/types/risk.ts#L138-L140) vs [backend/models/risk.py](backend/models/risk.py#L194-L196)  
**Severity:** 🟡 Medium

Frontend expects WebSocket event type:
```typescript
type: 'emergency_stop_event';
```

Backend sends:
```python
type: str = "emergency_stop_triggered"
```

These strings do not match. Any frontend WebSocket handler filtering on `type === 'emergency_stop_event'` will never match.

**Impact:** Emergency stop WebSocket events silently dropped by frontend.

---

### F-07 — Portfolio position endpoint URL mismatch
**File:** [frontend/src/services/portfolioService.ts](frontend/src/services/portfolioService.ts#L22) vs [backend/api/portfolio.py](backend/api/portfolio.py#L170)  
**Severity:** 🟡 Medium

Frontend calls:
```typescript
apiClient.get<Position[]>('/portfolio/positions');
```

Backend has TWO positions endpoints:
1. `GET /api/v1/portfolio/positions` — in `backend/api/portfolio.py`
2. `GET /api/v1/positions/` — in `backend/api/routes/positions.py`

These return **different DTOs**. The `portfolio.py` returns positions with `Decimal`-serialized fields. The `positions.py` route returns `PositionDTO` with float fields. Frontend imports `Position` from `portfolioStore` which uses yet another shape with fields like `unrealized_pl`, `cost_basis`, `side`, `opened_at` that the backend `PortfolioSummary` positions array does not guarantee.

**Impact:** Field mismatches cause undefined values in the position display.

---

### F-08 — Frontend order submission expects `BackendOrder` response, backend returns `OrderSubmissionResponse`
**File:** [frontend/src/services/ordersService.ts](frontend/src/services/ordersService.ts#L108) vs [backend/api/routes/orders.py](backend/api/routes/orders.py#L144-L154)  
**Severity:** 🟡 Medium

Frontend `submitOrder` calls `POST /orders` and expects a full `BackendOrder` shape including fields like `qty`, `filled_qty`, `limit_price`, `stop_price`, `avg_fill_price`. But the backend `OrderSubmissionResponse` only returns: `order_id`, `client_order_id`, `status`, `symbol`, `side`, `qty`, `submitted_at`.

The frontend `transformBackendOrder` will produce `undefined` for: `filled_qty`, `order_type`, `limit_price`, `stop_price`, `avg_fill_price`, `time_in_force`, `exchange`, `strategy_id`, `updated_at`.

**Impact:** Newly submitted orders show as broken in the UI until the next poll.

---

### F-09 — Dual `ModelStatus` type definitions with conflicting values
**File:** [frontend/src/types/index.ts](frontend/src/types/index.ts#L196) vs [frontend/src/types/ml.ts](frontend/src/types/ml.ts#L20-L27)  
**Severity:** 🟡 Medium

`index.ts` defines:
```typescript
export type ModelStatus = 'active' | 'training' | 'inactive' | 'error';
```

`ml.ts` defines:
```typescript
export const ModelStatus = { TRAINING: 'training', READY: 'ready', FAILED: 'failed', INACTIVE: 'inactive', DEPRECATED: 'deprecated' };
```

Values `'active'`/`'error'` only exist in `index.ts`; `'ready'`/`'failed'`/`'deprecated'` only in `ml.ts`. Which models use which depends on the import path.

**Impact:** UI components importing from different paths will handle model status inconsistently.

---

## 2. Alembic Migration Integrity

### A-01 — Two parallel migration systems with no shared lineage
**Files:** [alembic/versions/](alembic/versions/) vs [backend/migrations/versions/](backend/migrations/versions/)  
**Severity:** 🔴 Critical

There are **two independent Alembic migration directories**:
1. `alembic/versions/` — 6 migrations (chain: `001 → 002 → 003 → 20260128 → 20260129 → 20260202`)
2. `backend/migrations/versions/` — 9+ migrations (separate chain including `706e00fe1a28` initial, `20251007`, `20251015`, etc.)

These two chains **do not reference each other**. The `alembic/versions/001_idempotency_constraints.py` has `down_revision = None`, meaning it's a root. The `backend/migrations/versions/706e00fe1a28` is also a root.

Running `alembic upgrade head` will use one chain. Running with the other `alembic.ini` script location will use the other. Tables created by one chain won't exist for the other.

**Impact:** Database schema inconsistency. Missing tables, constraint conflicts, or data corruption depending on which migration path was run.

---

### A-02 — `model_registry` table referenced by FK but has no alembic migration
**File:** [alembic/versions/20260128_000001_add_model_monitoring_snapshots.py](alembic/versions/20260128_000001_add_model_monitoring_snapshots.py#L33)  
**Severity:** 🟠 High

Migration `20260128_000001` creates `model_monitoring_snapshots` with a foreign key to `model_registry.id`. But no migration in `alembic/versions/` creates the `model_registry` table. It's only created in `backend/migrations/versions/706e00fe1a28`, which is the *other* migration chain, or manually in test fixtures (`tests/conftest.py` line 178).

**Impact:** `alembic upgrade head` will fail with `relation "model_registry" does not exist` when creating `model_monitoring_snapshots`.

---

### A-03 — Migration `001_idempotency_constraints` swallows errors with bare `except: pass`
**File:** [alembic/versions/001_idempotency_constraints.py](alembic/versions/001_idempotency_constraints.py#L31-L34)  
**Severity:** 🟡 Medium

```python
try:
    op.add_column('orders', sa.Column('account_id', ...))
except Exception:
    pass  # Column might already exist, ignore error
```

And again at line 75:
```python
try:
    op.create_unique_constraint('uq_orders_account_client_order', ...)
except Exception:
    pass
```

These bare `except` blocks make the migration non-idempotent in a way that hides real errors (e.g., wrong column type, permission denied). A proper approach is conditional DDL (`IF NOT EXISTS`) or Alembic's `batch_alter_table`.

**Impact:** Silent migration failures that aren't detected until production queries fail.

---

### A-04 — Missing `downgrade()` in migration `001`
**File:** [alembic/versions/001_idempotency_constraints.py](alembic/versions/001_idempotency_constraints.py#L100-L131)  
**Severity:** 🟡 Medium

The `downgrade()` function drops indexes and tables but does NOT reverse the `add_column('orders', 'account_id')` or the unique constraint with the bare `except`. This means a downgrade leaves orphan columns.

**Impact:** Rollback doesn't fully restore the previous schema state.

---

## 3. Docker / Deployment Issues

### D-01 — Dockerfile references `requirements.lock` but `Dockerfile.production` uses `requirements.txt`
**File:** [Dockerfile](Dockerfile#L34-L39) vs [Dockerfile.production](Dockerfile.production#L35-L38)  
**Severity:** 🟠 High

`Dockerfile` (development/staging):
```dockerfile
COPY requirements.txt requirements.lock ./
RUN pip install -r requirements.lock
```

`Dockerfile.production`:
```dockerfile
COPY requirements.txt requirements-dev.txt* ./
RUN pip install -r requirements.txt
```

Production uses non-locked `requirements.txt` while development uses locked versions. This is exactly backwards — **production** should use locked dependencies for reproducibility.

**Impact:** Production builds may install different dependency versions than tested.

---

### D-02 — Dockerfile.production references `backend.main:app`, Dockerfile references `backend.api.main:socketio_app`
**File:** [Dockerfile.production](Dockerfile.production#L95) vs [Dockerfile](Dockerfile#L110)  
**Severity:** 🟠 High

```dockerfile
# Dockerfile (dev/staging)
CMD ["uvicorn", "backend.api.main:socketio_app", ...]

# Dockerfile.production (prod)
CMD ["python", "-m", "uvicorn", "backend.main:app", ...]
```

These reference **different application entry points**. The dev Dockerfile uses the Socket.IO-wrapped app (`socketio_app`), while production uses the bare FastAPI app (`backend.main:app`). This means **WebSocket/Socket.IO support is missing in production**.

**Impact:** Real-time order updates, portfolio updates, and risk alerts via WebSocket will not work in production deployment.

---

### D-03 — `REDIS_URL` env var missing from `docker-compose.yml` and `docker-compose.paper.yml`
**File:** [docker-compose.yml](docker-compose.yml#L24-L60) and [docker-compose.paper.yml](docker-compose.paper.yml#L15-L64)  
**Severity:** 🟠 High

The `docker-compose.yml` and `docker-compose.paper.yml` set `REDIS_PASSWORD` on the Redis container but **never pass `REDIS_URL` to the API container**. The app defaults to `redis://localhost:6379/0` (from `backend/config/settings.py` line 312), but inside Docker the Redis host is `redis`, not `localhost`.

Only `docker-compose.production.yml` correctly sets `REDIS_URL=redis://redis:6379/0`.

**Impact:** Redis connections fail in Docker dev/paper environments. Circuit breaker, caching, and rate limiting silently degrade to no-op.

---

### D-04 — Redis auth password not included in `REDIS_URL` for production compose
**File:** [docker-compose.yml](docker-compose.yml#L124) vs [docker-compose.production.yml](docker-compose.production.yml#L30)  
**Severity:** 🟡 Medium

`docker-compose.yml` starts Redis with `--requirepass ${REDIS_PASSWORD:-changeme_redis}`, but the `REDIS_URL` (when set) is `redis://redis:6379/0` — no password in the URL. The app will get `NOAUTH Authentication required` errors.

The production compose similarly sets `REDIS_URL=redis://redis:6379/0` without auth credentials, while the dev compose Redis requires a password.

**Impact:** Redis connection failures when password is enabled.

---

### D-05 — Health check path inconsistency across deployments
**Files:** Multiple  
**Severity:** 🟡 Medium

| Deployment | Liveness Path | Readiness Path |
|---|---|---|
| `docker-compose.yml` | `/healthz` | (none specified) |
| `docker-compose.prod.yml` | `/healthz` | (none specified) |
| `docker-compose.production.yml` | `/health/live` | (none specified) |
| `Dockerfile.production` | `/health/live` | (none) |
| `k8s/deployment.yaml` | `/healthz` | `/readyz` |

Three different health check paths are used across environments. If the backend only registers one path, the others return 404 and containers restart in a loop.

**Impact:** Container crash loops in environments using the wrong health check path.

---

### D-06 — K8s deployment missing `REDIS_URL` environment variable
**File:** [k8s/deployment.yaml](k8s/deployment.yaml#L73-L157)  
**Severity:** 🟡 Medium

The Kubernetes deployment spec includes env vars for database, Alpaca, JWT, and OTEL — but **no `REDIS_URL`**. The app defaults to `redis://localhost:6379/0`, which won't work in Kubernetes where Redis is in a separate pod.

**Impact:** Redis-dependent features (circuit breaker, caching, rate limiting) fail silently in K8s.

---

### D-07 — K8s `readOnlyRootFilesystem: true` conflicts with Python cache writes
**File:** [k8s/deployment.yaml](k8s/deployment.yaml#L223-L228)  
**Severity:** 🟡 Medium

```yaml
securityContext:
  readOnlyRootFilesystem: true
```

While `PYTHONDONTWRITEBYTECODE=1` prevents `.pyc` files, some Python libraries write to the filesystem at runtime (e.g., `tempfile`, `httpx` cache). The `tmp` volume is mounted at `/app/tmp`, but Python's default `tempfile.tempdir` points to `/tmp`, not `/app/tmp`.

**Impact:** Runtime crashes from `OSError: [Errno 30] Read-only file system` when libraries try to write to `/tmp`.

---

## 4. Feature Engineering Quality

### FE-01 — `create_leads()` introduces look-ahead bias
**File:** [backend/ml/feature_engineering.py](backend/ml/feature_engineering.py#L307-L313)  
**Severity:** 🔴 Critical

```python
@staticmethod
def create_leads(data: pd.Series, leads: list[int]) -> pd.DataFrame:
    """Create lead features (future values)."""
    for lead in leads:
        if lead > 0:
            features[f'{data.name}_lead_{lead}'] = data.shift(-lead)
```

This method creates features using **future data** (`shift(-lead)`). If used during training without proper train/test split enforcement, the model learns from future prices. The method is publicly available and the docstring says "Create lead features (future values)" without any warning about look-ahead bias.

Although it's not directly called in `FeatureEngineer.transform()`, it's available for use by any caller and is exported in `__all__`.

**Impact:** ML models trained with lead features will show artificially inflated accuracy during backtesting but fail catastrophically in live trading.

---

### FE-02 — `normalized_price` feature uses rolling window that leaks future data at edges
**File:** [backend/ml/feature_engineering.py](backend/ml/feature_engineering.py#L178)  
**Severity:** 🟡 Medium

```python
'normalized_price': (data - data.rolling(window=20).mean()) / data.rolling(window=20).std()
```

This is computed with `rolling(window=20)` which defaults to `min_periods=None` (equals `window`), so the first 19 values are NaN. But the real issue is that this normalization is computed on the full dataset at once. If the data includes both train and test sets, the rolling mean/std are computed with awareness of test-set ordering.

**Impact:** Minor information leakage at train/test boundary, but only when not properly splitting before feature engineering.

---

### FE-03 — `bb_position` division by zero unprotected
**File:** [backend/ml/feature_engineering.py](backend/ml/feature_engineering.py#L91)  
**Severity:** 🟡 Medium

```python
'bb_position': (data - sma) / (std * std_dev)
```

When `std` is zero (e.g., consecutive identical prices), this produces `inf` or `NaN`. Unlike the RSI calculation which adds `1e-10` to avoid division by zero, Bollinger Band position has no such protection.

**Impact:** `inf` values in features cause ML model training to fail or produce garbage predictions.

---

### FE-04 — `transform()` silently returns original data on any error
**File:** [backend/ml/feature_engineering.py](backend/ml/feature_engineering.py#L500-L522)  
**Severity:** 🟡 Medium

```python
def transform(self, data, ...):
    try:
        # ... all feature engineering ...
    except Exception as e:
        logger.error(f"Error in feature transformation: {e}")
        return data  # Return original data if transformation fails
```

If any feature computation fails, the method silently returns the raw data without features. Downstream code expecting engineered features will get raw OHLCV data, producing meaningless predictions.

**Impact:** Silent degradation of ML predictions to random noise.

---

## 5. Broker Integration Gaps

### B-01 — `AlpacaBrokerClient` never closes its `httpx.AsyncClient`
**File:** [backend/integrations/alpaca_broker.py](backend/integrations/alpaca_broker.py#L116-L120)  
**Severity:** 🟡 Medium

The client creates `self.client = httpx.AsyncClient(...)` in `__init__` but the global singleton `get_alpaca_broker_client()` pattern (line 837) means the client is created once and the `close()` method is only called during explicit cleanup. If the app shuts down without calling `cleanup_alpaca_broker_client()`, connections leak.

**Impact:** Connection pool exhaustion during long-running processes or repeated restarts.

---

### B-02 — `AlpacaDataClient` has no retry logic
**File:** [backend/integrations/alpaca_data.py](backend/integrations/alpaca_data.py#L121-L155)  
**Severity:** 🟡 Medium

`AlpacaBrokerClient` has comprehensive retry logic via `_make_request_with_retry()`. But the `AlpacaDataClient` for market data makes raw `self.client.get()` calls with no retry, no rate-limit handling, and no backoff.

**Impact:** Transient Alpaca data API failures cause immediate feature engineering failures for ML models.

---

### B-03 — `AlpacaDataClient` uses `adjustment=raw` — no split/dividend adjustment
**File:** [backend/integrations/alpaca_data.py](backend/integrations/alpaca_data.py#L110)  
**Severity:** 🟡 Medium

```python
params = {
    "adjustment": "raw",  # Use raw prices (no adjustments)
}
```

Using raw (unadjusted) data means stock splits and dividends create artificial price jumps. Technical indicators (RSI, MACD, Bollinger Bands) computed on raw data will produce false signals on split/dividend dates.

**Impact:** False trading signals on days with corporate actions.

---

### B-04 — `AlpacaStreamClient` reconnect gives up permanently after 10 attempts
**File:** [backend/integrations/alpaca_stream.py](backend/integrations/alpaca_stream.py#L594-L598)  
**Severity:** 🟠 High

```python
if self.reconnect_attempts >= self.max_reconnect_attempts:
    logger.error("Max reconnection attempts reached, stopping")
    await self._emit_max_reconnect_alert()
    break  # Permanently stops the stream
```

After 10 failed reconnection attempts, the stream client **permanently stops** and never tries again until the entire application is restarted. There's an alert emitted, but no automatic recovery mechanism. For a trading platform, losing order update streams means fills, cancellations, and partial fills are never reflected in the local database.

**Impact:** Silent loss of all real-time order updates until manual restart. Positions/P&L become stale.

---

### B-05 — `AlpacaStreamClient` uses different env var names than `AlpacaBrokerClient`
**File:** [backend/integrations/alpaca_stream.py](backend/integrations/alpaca_stream.py#L44-L46) vs [backend/integrations/alpaca_broker.py](backend/integrations/alpaca_broker.py#L91-L96)  
**Severity:** 🟡 Medium

Stream client reads:
```python
self.api_key = os.getenv("ALPACA_API_KEY_ID")
self.api_secret = os.getenv("ALPACA_API_SECRET_KEY")
```

Broker client reads (with fallbacks):
```python
self.api_key = (os.getenv("ALPACA_API_KEY_ID") or os.getenv("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID"))
self.api_secret = (os.getenv("ALPACA_API_SECRET_KEY") or os.getenv("ALPACA_SECRET_KEY") or os.getenv("APCA_API_SECRET_KEY"))
```

Docker compose files use `ALPACA_API_KEY` and `ALPACA_SECRET_KEY`. The stream client only checks `ALPACA_API_KEY_ID` — it will get `None` and fail to authenticate.

**Impact:** WebSocket order update stream fails to connect in Docker deployments while REST API works fine.

---

### B-06 — `RobustAlpacaStream` constructor takes `api_key`/`api_secret` positional args but `AlpacaBrokerClient` takes none
**File:** [backend/integrations/alpaca_stream_production.py](backend/integrations/alpaca_stream_production.py#L86-L91)  
**Severity:** 🟡 Medium

```python
class RobustAlpacaStream:
    def __init__(self, api_key, api_secret, base_url=..., paper=True):
        self.alpaca_client = AlpacaBrokerClient(api_key, api_secret, paper=paper)
```

But `AlpacaBrokerClient.__init__` takes **no arguments** — it reads from env vars. Passing `api_key, api_secret, paper` as positional args will raise `TypeError: __init__() takes 1 positional argument but 4 were given`.

**Impact:** Production stream client is broken — cannot be instantiated.

---

## 6. Missing Tests for Critical Paths

### T-01 — No end-to-end order execution pipeline test
**Severity:** 🟠 High

Searched all test files for end-to-end order flow (submit → outbox → dispatch → broker → fill → DB update → WebSocket broadcast). No test covers this full path. Individual unit tests exist for `OrderService`, `AlpacaBrokerClient`, and `AlpacaStreamClient`, but no integration test chains them together.

**Impact:** Regression risk for the most critical business flow.

---

### T-02 — No DLQ processing tests
**Severity:** 🟡 Medium

No test files cover Dead Letter Queue processing behavior (events that fail dispatch, retry exhaustion, DLQ consumption, and re-processing). The DLQ infinite loop issue (Part 1) is documented but untested.

**Impact:** DLQ bugs will not be caught by CI.

---

### T-03 — Risk manager not tested with zero-portfolio or negative-returns edge cases
**Severity:** 🟡 Medium

Tests in `test_risk_manager_comprehensive.py` test normal flows but don't cover:
- Portfolio with `equity=0` (division by zero in concentration calculations)
- All-negative returns (Sharpe ratio `NaN`)
- Empty position list with active risk limits

**Impact:** Runtime crashes in risk calculation edge cases.

---

### T-04 — `AlpacaStreamClient` reconnection logic untested
**Severity:** 🟡 Medium

The `start_with_reconnect()` method has complex exponential backoff, max-attempt limits, and alert emission — none of which are tested. The `_emit_max_reconnect_alert()` method catches and silently swallows all exceptions.

**Impact:** Reconnection bugs go undetected.

---

## 7. Logging / Observability Gaps

### O-01 — No end-to-end order latency tracing from submission to fill
**Severity:** 🟠 High

The `slo_metrics.py` records `order_latency` but it's only called from `backend/brokers/alpaca_production.py` (line 355) — measuring just the broker API call duration. The latency from user clicking "Submit" through validation, risk check, outbox write, outbox dispatch, broker API call, and fill update is **not measured as a single trace span**.

The OpenTelemetry tracing in `backend/observability/tracing.py` has trace analysis capabilities but no specific instrumentation for the order pipeline.

**Impact:** Cannot identify which stage of order processing is the bottleneck. SLO monitoring is incomplete.

---

### O-02 — `TraceStorage` is in-memory only — traces lost on restart
**File:** [backend/observability/tracing.py](backend/observability/tracing.py#L62-L80)  
**Severity:** 🟡 Medium

```python
class TraceStorage:
    """In-memory storage for trace data."""
    def __init__(self, max_traces: int = 1000):
        self.traces: dict[str, list[SpanMetrics]] = {}
```

Traces are stored in a dict with a max of 1000. Under load, this fills up fast and old traces are evicted. There's a warning for production but no automatic switch to persistent storage.

**Impact:** Post-mortem debugging impossible for issues that occurred more than ~1000 requests ago.

---

### O-03 — `backend/observability/metrics.py` is just a forwarding stub
**File:** [backend/observability/metrics.py](backend/observability/metrics.py#L1-L17)  
**Severity:** 🟡 Low (informational)

The entire file is a `__getattr__` proxy to `backend.infra.metrics`. The `track_model_prediction` function is a no-op. Any code importing from `backend.observability.metrics` works, but this creates confusion about where metrics are actually defined.

**Impact:** Developer confusion; two import paths for the same metrics.

---

### O-04 — No metrics for feature engineering pipeline latency or failure rate  
**Severity:** 🟡 Medium

The `LABEL_ALLOWLIST` in `backend/infra/metrics.py` defines `feature_compute_latency_seconds` and `feature_schema_validations_total`, but `backend/ml/feature_engineering.py` has **zero Prometheus instrumentation**. No histograms, no counters, no error rates.

**Impact:** Cannot monitor feature engineering health or detect silent degradation.

---

### O-05 — SLO monitoring not integrated into the startup lifecycle
**Severity:** 🟡 Medium

`backend/monitoring/slo_metrics.py` defines SLO collectors and alert rules, but there's no evidence they're initialized during app startup. The `slo_collector.record_order_latency()` is called from `backend/brokers/alpaca_production.py`, but it's unclear if `slo_monitor` and `slo_alerts` are actually running.

**Impact:** SLO violations may go undetected.

---

## Summary

| Area | Critical | High | Medium | Low |
|------|----------|------|--------|-----|
| Frontend-Backend Contracts | 1 (F-01) | 2 (F-02, F-04) | 5 (F-03, F-05, F-06, F-07, F-08) | 1 (F-09) |
| Alembic Migration Integrity | 1 (A-01) | 1 (A-02) | 2 (A-03, A-04) | 0 |
| Docker/Deployment | 0 | 3 (D-01, D-02, D-03) | 4 (D-04, D-05, D-06, D-07) | 0 |
| Feature Engineering | 1 (FE-01) | 0 | 3 (FE-02, FE-03, FE-04) | 0 |
| Broker Integrations | 0 | 2 (B-04, B-06) | 4 (B-01, B-02, B-03, B-05) | 0 |
| Missing Tests | 0 | 1 (T-01) | 3 (T-02, T-03, T-04) | 0 |
| Observability | 0 | 1 (O-01) | 3 (O-02, O-04, O-05) | 1 (O-03) |
| **Total** | **3** | **10** | **24** | **2** |

### Top 5 Fix Priorities
1. **A-01** — Merge or reconcile the two parallel migration systems before any schema changes
2. **D-02** — Production Dockerfile uses wrong app entry point (no WebSocket support)
3. **B-06** — `RobustAlpacaStream` cannot be instantiated (passes args to no-arg constructor)
4. **FE-01** — `create_leads()` look-ahead bias available for training use
5. **F-01** — TypeScript syntax error in `StrategyType` (build-breaking)
