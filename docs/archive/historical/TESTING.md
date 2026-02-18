# Testing Guide

## Test Structure

```
tests/                           # 111 comprehensive integration tests
├── conftest.py                  # Shared fixtures
├── unit/                        # Unit tests
│   ├── __init__.py
│   ├── deep/                    # 165 deep functional tests
│   │   └── test_deep_*.py       # Tests that call actual code
│   ├── generated/               # 330 auto-generated tests
│   │   └── test_auto_*.py       # Import and instantiation tests
│   └── test_*.py                # 38 focused unit tests
└── test_*.py                    # Comprehensive test suites
```

**Total: 644 test files**

## Quick Commands

### Run All Tests (Fast - ~2 min)
```bash
python run_tests.py
```

### Run with Coverage Report
```bash
python run_tests.py --coverage
```

### Run Specific Test Category
```bash
# Unit tests only
pytest tests/unit/ -q --tb=short

# Deep functional tests
pytest tests/unit/deep/ -q --tb=short

# Comprehensive tests
pytest tests/test_*.py -q --tb=short
```

## Known Stalling Tests (Auto-Skipped)

The following 24 tests have timeout issues and are automatically skipped:
- test_deep_alpaca_stream.py
- test_deep_scanner.py
- test_mega_comprehensive_imports.py
- test_production_unified.py
- test_helpers_comprehensive.py
- test_live_model_smoke.py
- test_ml_lifecycle_api.py
- test_models_api_simple.py
- test_port_management_comprehensive.py
- test_position_management.py
- test_pretrade_validation.py
- test_risk_management_complete.py
- test_route_registry.py
- test_routes_registry.py
- test_security_boundaries.py
- test_small_modules_comprehensive.py
- test_deep_main.py
- test_deep_ensemble_model.py
- test_deep_slo_alerts.py
- test_deep_social_sentiment.py
- test_deep_utilities.py
- test_auto_sentiment.py
- test_auto_social_sentiment.py
- test_auto_ensemble_model.py

## Coverage Targets

| Metric | Current | Target |
|--------|---------|--------|
| Line Coverage | 49% | 80%+ |
| Branch Coverage | ~40% | 70%+ |
| Passing Tests | 4,620 | 5,000+ |
| Failed Tests | 215 | 0 |
| Skipped Tests | 3,305 | <500 |

## Test Categories

### 1. Deep Tests (`tests/unit/deep/`)
- Actually execute code paths
- Test function behavior
- Cover edge cases

### 2. Generated Tests (`tests/unit/generated/`)
- Import validation
- Class instantiation
- Basic smoke tests

### 3. Comprehensive Tests (`tests/`)
- Full feature tests
- Integration scenarios
- API endpoint tests

## CI/CD Integration

```yaml
# GitHub Actions example
- name: Run Tests
  run: python run_tests.py --coverage --fail-under=80
```

## Fixing Skipped Tests

Most skipped tests fail due to:
1. **Missing mocks** - Add proper mocking for external services
2. **Import errors** - Fix circular imports or missing dependencies
3. **Async issues** - Use proper async test fixtures

To fix:
```bash
# Run a specific skipped test to see the error
pytest tests/unit/deep/test_deep_specific.py -v --tb=long
```
