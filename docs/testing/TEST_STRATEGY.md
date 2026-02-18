# Test Strategy

## Test Tiers

### Tier 1 — Smoke Tests (< 30 seconds)
Fast unit tests to verify nothing is fundamentally broken.
```bash
pytest -x -q -m "unit" --maxfail=3 --tb=short --timeout=15
```
Run before every deployment and after every code change.

### Tier 2 — Integration Tests (< 5 minutes)
Unit + API + service tests with coverage reporting.
```bash
pytest -x -q -m "unit or api or services" --cov=backend --cov-branch --tb=short --timeout=30
```
Run before merging any PR.

### Tier 3 — Full Suite (< 30 minutes)
Complete test suite with coverage report.
```bash
pytest -v --cov=backend --cov-branch --cov-report=html:test_results --cov-report=term-missing:skip-covered --timeout=30
```
Nightly or on-demand.

## Test Markers

| Marker | Description |
|--------|-------------|
| `unit` | Fast, isolated unit tests |
| `integration` | Tests requiring running services (DB, Redis) |
| `live` | Tests requiring live Alpaca connection |
| `api` | API endpoint tests |
| `services` | Service layer tests |
| `performance` | Performance/SLO tests |
| `slow` | Tests that take >5 seconds |
| `evolution` | Organism adaptation tests |
| `regression` | Non-regression checks |

## Running Tests

### Prerequisites
- Python 3.11+ with virtualenv activated
- PostgreSQL running (for integration tests)
- Redis running (for integration tests)
- `.env` configured (for live tests)

### Quick Commands
```bash
# Run all unit tests
pytest -m unit

# Run a specific test file
pytest tests/unit/test_order_service_comprehensive.py -v

# Run tests matching a keyword
pytest -k "risk_manager" -v

# Run with coverage
pytest --cov=backend --cov-report=html:test_results
```

### Live Smoke Tests
```bash
# Requires running backend server
python scripts/smoke_test_live.py

# Trading-specific verification
python scripts/trading_verification.py
```

## Test Organization

```
tests/
├── conftest.py                  # Global fixtures
├── test_*.py                    # Root-level integration tests
├── unit/                        # Unit tests
│   ├── generated/               # Auto-generated coverage tests
│   ├── test_*.py                # Hand-written unit tests
│   └── conftest.py              # Unit test fixtures
├── integration/                 # Integration tests (require services)
└── real_tests/                  # Live broker tests (require Alpaca)
```

## Current Status

| Metric | Value |
|--------|-------|
| Total Tests | ~7,522 |
| Passing | 6,803 |
| Skipped | 719 |
| Failed | 0 |
| Last Run | 2026-02-17 |
