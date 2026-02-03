# Real Integration Tests

## Philosophy

These tests are designed to validate **ACTUAL SYSTEM BEHAVIOR**, not mock implementations. Every test in this directory makes real calls to:

- **Real Database** - PostgreSQL (required, no SQLite fallback)
- **Real Broker** - Alpaca paper trading API
- **Real Market Data** - Live quotes and historical bars
- **Real ML Models** - Actual model inference
- **Real Calculations** - True risk, P&L, and position math

> **"Mockup tests are useless. We test real behaviour and actions and outputs."**

## Database Policy

| Test Type | Database | Rationale |
|-----------|----------|-----------|
| Unit tests (`tests/`) | SQLite (in-memory) | Fast, isolated, no Docker needed |
| **Real tests (`tests/real_tests/`)** | **PostgreSQL (Docker)** | Production-like behavior required |
| Production | PostgreSQL | Required |

**Real integration tests require PostgreSQL.** SQLite is NOT supported because:
- PostgreSQL-specific features (UUID types, JSONB, etc.)
- Production-like transaction behavior
- Actual constraint enforcement

## Test Categories

| File | Purpose | Dependencies |
|------|---------|--------------|
| `test_real_database.py` | Database CRUD, transactions, performance | PostgreSQL (Docker) |
| `test_real_order_flow.py` | Order lifecycle from submission to fill | Alpaca Paper API |
| `test_real_risk_management.py` | Position sizing, drawdown, VaR calculations | Broker + DB |
| `test_real_api_endpoints.py` | HTTP API validation | Running API Server |
| `test_real_market_data.py` | Quote/bar data quality and freshness | Alpaca Market Data |
| `test_real_positions.py` | Position tracking, P&L, reconciliation | Broker + DB |
| `test_real_ml_models.py` | Model loading, predictions, performance | Trained Models |
| `test_real_e2e_workflows.py` | Complete trading system integration | All Systems |

## Prerequisites

### 1. Docker Services (Required)

```powershell
# Start PostgreSQL and Redis
docker-compose up -d db redis

# Verify containers are healthy
docker ps --format "table {{.Names}}\t{{.Status}}"
```

Expected output:
```
NAMES                          STATUS
algotrading_platform-db-1      Up X minutes (healthy)
algotrading_platform-redis-1   Up X minutes (healthy)
```

### 2. Environment Variables

The `.env` file should contain:
```bash
# Database (loaded automatically from .env)
DATABASE_URL=postgresql+asyncpg://trading:trading_password@localhost:5432/algotrading

# Required for broker tests
ALPACA_API_KEY=your-paper-trading-key
ALPACA_SECRET_KEY=your-paper-trading-secret
```

### 3. Python Dependencies

```powershell
# Required for real tests
pip install psycopg2-binary  # Sync PostgreSQL driver
pip install "httpx[http2]"   # HTTP/2 support for Alpaca
```

### 4. Running API Server (for API endpoint tests)

```powershell
python main.py
# OR
python -m uvicorn backend.api.main:app --host 0.0.0.0 --port 8000
```

## Running Tests

### Run All Real Tests

```powershell
# Ensure Docker is running first
docker-compose up -d db redis

# Run all real tests
pytest tests/real_tests/ -v
```

### Run Specific Category

```powershell
# Database tests only
pytest tests/real_tests/test_real_database.py -v

# Order flow tests only (requires market open)
pytest tests/real_tests/test_real_order_flow.py -v

# API endpoint tests (requires running server)
pytest tests/real_tests/test_real_api_endpoints.py -v
```

### Quick Test Run

```powershell
# Quiet mode with summary
pytest tests/real_tests/ -q --tb=short
```

## Test Markers

| Marker | Meaning |
|--------|---------|
| `@pytest.mark.asyncio` | Async test requiring event loop |
| `require_market_open` | Test requires US market to be open (9:30 AM - 4:00 PM ET) |

## Fixtures

### Database Fixtures

```python
@pytest.fixture
def db_session(sync_session_factory):
    """Real database session with auto-rollback."""
    
@pytest.fixture
async def async_db_session(async_engine):
    """Real async database session."""
```

### Broker Fixtures

```python
@pytest.fixture
async def paper_broker(alpaca_paper_config):
    """Real Alpaca paper trading client."""

@pytest.fixture
def require_market_open():
    """Skip if US market is closed."""
```

### HTTP Client Fixtures

```python
@pytest.fixture
async def http_client(api_base_url):
    """Real HTTP client for API tests."""

@pytest.fixture
async def authenticated_client(http_client):
    """HTTP client with real JWT token."""
```

### Test Data Factories

```python
@pytest.fixture
def order_factory():
    """Generate valid order requests."""

@pytest.fixture
def position_factory():
    """Generate valid position data."""

@pytest.fixture
def strategy_factory():
    """Generate valid strategy configurations."""
```

## Expected Results

### When Market is Open
- Order flow tests will submit/cancel real paper orders
- Quote tests will receive real-time prices
- Position tests will reflect actual paper trading positions

### When Market is Closed
- Order flow tests that require fills will be skipped
- Quote timestamps may be stale (this is expected)
- Database and API tests still run normally

## Test Output Examples

### Successful Run

```
tests/real_tests/test_real_database.py::TestRealOrderDatabase::test_create_order_real_insert PASSED
tests/real_tests/test_real_order_flow.py::TestRealOrderSubmission::test_submit_market_buy_order PASSED
tests/real_tests/test_real_risk_management.py::TestRealPositionSizing::test_position_size_respects_max_risk PASSED
```

### Market Closed Skips

```
tests/real_tests/test_real_order_flow.py::test_submit_market_buy_order SKIPPED (Market is closed)
tests/real_tests/test_real_market_data.py::test_quote_timestamp_is_recent SKIPPED (Market is closed)
```

## Continuous Integration

For CI/CD, these tests should run:
- **Database tests**: Always (requires PostgreSQL service)
- **API tests**: When API server is available
- **Broker tests**: During market hours or skip gracefully
- **ML tests**: When models are deployed

### GitHub Actions Example

```yaml
services:
  postgres:
    image: postgres:16-alpine
    env:
      POSTGRES_USER: trading
      POSTGRES_PASSWORD: trading_password
      POSTGRES_DB: algotrading
    ports:
      - 5432:5432
    options: >-
      --health-cmd pg_isready
      --health-interval 10s
      --health-timeout 5s
      --health-retries 5

steps:
  - name: Run Real Tests
    env:
      DATABASE_URL: postgresql+asyncpg://trading:trading_password@localhost:5432/algotrading
      ALPACA_API_KEY: ${{ secrets.ALPACA_PAPER_KEY }}
      ALPACA_SECRET_KEY: ${{ secrets.ALPACA_PAPER_SECRET }}
    run: |
      pip install psycopg2-binary "httpx[http2]"
      pytest tests/real_tests/ -v --tb=short
```

## Troubleshooting

### "Real integration tests require PostgreSQL"

Start Docker services:
```powershell
docker-compose up -d db redis
```

### "ModuleNotFoundError: No module named 'psycopg2'"

Install the sync PostgreSQL driver:
```powershell
pip install psycopg2-binary
```

### "Using http2=True, but the 'h2' package is not installed"

Install HTTP/2 support:
```powershell
pip install "httpx[http2]"
```

### "Alpaca credentials not configured"

Set the environment variables in `.env`:
```bash
ALPACA_API_KEY=your-key
ALPACA_SECRET_KEY=your-secret
```

### "Could not connect to Alpaca"

1. Check your internet connection
2. Verify credentials are for paper trading (not live)
3. Ensure Alpaca services are not in maintenance

### "Market is closed" skips

This is expected outside US market hours (9:30 AM - 4:00 PM ET, weekdays).

### "Model not found" skips

Train or deploy the required ML models first:
```bash
python scripts/train_models.py
```

## Contributing

When adding new real tests:

1. **NO MOCKING of business logic** - Test actual behavior
2. **Use fixtures** - Database sessions, broker clients, HTTP clients
3. **Handle unavailability gracefully** - Use `pytest.skip()` when dependencies are missing
4. **Document dependencies** - What needs to be running/configured
5. **Consider market hours** - Mark tests that need live market

## Coverage Goals

These real tests should achieve:
- **100% of critical paths** tested with real operations
- **All API endpoints** validated with real HTTP requests
- **All risk calculations** verified with real portfolio data
- **All order types** tested with real broker execution
- **All data pipelines** validated end-to-end
