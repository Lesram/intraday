# Running Tests

This document provides comprehensive guidance on running the test suite for the intraday trading platform. The test suite includes unit tests, integration tests, end-to-end tests, performance benchmarks, and fuzz testing.

## Quick Start

```bash
# Install development dependencies
make install-dev

# Run quick smoke tests (recommended for development)
make test

# Run all tests with coverage
make coverage

# Run full test suite
make test-full
```

## Test Suite Overview

### Test Categories

| Test Type | Purpose | Duration | Usage |
|-----------|---------|----------|-------|
| **Smoke Tests** | Fast subset of unit tests for development | ~30s | Daily development |
| **Unit Tests** | Individual component testing | ~2-5min | Feature development |
| **Integration Tests** | Component interaction testing | ~10-15min | Integration validation |
| **E2E Tests** | Full system testing with paper trading | ~20-30min | Release validation |
| **Performance Tests** | Latency and throughput benchmarks | ~10-20min | Performance validation |
| **Fuzz Tests** | Chaos engineering and edge cases | ~15-25min | Robustness testing |

### Test Structure

```
tests/
├── unit/                    # Unit tests
│   ├── test_features.py     # Feature engineering tests
│   ├── test_risk_management.py  # Risk management tests
│   ├── test_orders.py       # Order handling tests
│   └── test_utilities.py    # Utility function tests
├── integration/             # Integration tests
│   ├── test_pipeline.py     # Trading pipeline tests
│   └── test_backtesting.py  # Backtesting engine tests
├── e2e/                     # End-to-end tests
│   └── test_system_integration.py  # Full system tests
├── performance/             # Performance tests
│   └── test_benchmarks.py   # Latency and throughput tests
├── fuzz/                    # Fuzz tests
│   └── test_chaos.py        # Chaos engineering tests
└── fixtures/                # Test data and fixtures
    ├── market_data.py       # Market data generators
    └── broker_responses.py  # Mock broker responses
```

## Running Tests

### Using Make (Recommended)

```bash
# Quick development check
make test                    # Smoke tests (~30s)

# Specific test suites
make test-unit              # Unit tests only
make test-integration       # Integration tests only
make test-e2e              # End-to-end tests
make test-performance      # Performance benchmarks
make test-fuzz             # Chaos engineering tests

# Coverage and reporting
make coverage              # Tests with coverage report
make html-report           # Open coverage report in browser

# Quality checks
make lint                  # Code linting
make format               # Code formatting
make typecheck            # Type checking
make security             # Security scans
make quality              # All quality checks

# Full pipeline
make ci                   # CI pipeline (quality + tests)
make pre-release          # Full release validation
```

### Using Python Test Runner

```bash
# Quick tests
python run_tests.py smoke

# Specific test suites
python run_tests.py unit --verbose
python run_tests.py integration --coverage
python run_tests.py e2e --no-coverage
python run_tests.py performance --benchmarks
python run_tests.py fuzz --verbose

# Full test suite
python run_tests.py full --coverage --parallel

# With additional checks
python run_tests.py smoke --quality --security
```

### Using Pytest Directly

```bash
# Basic usage
pytest tests/unit/ -v                    # Unit tests
pytest tests/integration/ -v            # Integration tests
pytest tests/ -m "not slow" -v          # Fast tests only
pytest tests/ -m "performance" -v       # Performance tests only

# With coverage
pytest tests/unit/ --cov=backend --cov-report=html

# Parallel execution
pytest tests/unit/ -n auto               # Use all CPU cores
pytest tests/unit/ -n 4                 # Use 4 processes

# Specific tests
pytest tests/unit/test_features.py::TestFeatureEngineering::test_rsi_calculation -v
pytest tests/ -k "risk" -v              # Tests matching "risk"

# With markers
pytest tests/ -m "unit and not slow" -v
pytest tests/ -m "integration or e2e" -v
```

## Test Configuration

### Pytest Configuration

The test suite is configured via `pytest.ini`:

```ini
[tool:pytest]
# Test discovery
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*

# Coverage requirements
addopts = 
    --strict-markers
    --strict-config
    --cov-fail-under=90
    --cov-branch
    --timeout=300

# Test markers
markers =
    unit: Unit tests (fast, isolated)
    integration: Integration tests (moderate speed)
    e2e: End-to-end tests (slow, full system)
    performance: Performance and benchmark tests
    fuzz: Fuzz testing and chaos engineering
    slow: Tests that take > 30 seconds
    # ... (17 total markers)
```

### Environment Variables

```bash
# Test environment
export ENVIRONMENT=testing
export LOG_LEVEL=INFO

# Testing mode flags
export PAPER_TRADING=true
export SKIP_EXTERNAL_APIS=true
export MOCK_MARKET_DATA=true

# Database testing
export TEST_DATABASE_URL=postgresql://test_user:test_pass@localhost/test_db

# API keys for integration tests (optional)
export TEST_ALPACA_API_KEY=your_paper_trading_key
export TEST_ALPACA_SECRET_KEY=your_paper_trading_secret
```

## Coverage Requirements

The test suite maintains strict coverage requirements:

- **Minimum Coverage**: 90% line coverage + branch coverage
- **Unit Tests**: >95% coverage for core business logic
- **Integration Tests**: >80% coverage for integration paths
- **Critical Components**: 100% coverage for risk management and order handling

### Coverage Reports

```bash
# Generate coverage report
make coverage

# View HTML report
open test_reports/unit_coverage_html/index.html

# View terminal report
cat test_reports/unit_coverage.xml | grep 'line-rate'
```

## Performance Testing

### Latency Benchmarks

```bash
# Run latency tests
make test-performance

# Specific latency tests
pytest tests/performance/ -k "latency" -v -s

# Expected performance targets:
# - Feature calculation: P50 < 5ms, P95 < 20ms
# - Risk checks: P50 < 0.5ms, P95 < 2ms
# - Order processing: P50 < 100ms, P95 < 200ms
```

### Throughput Benchmarks

```bash
# Run throughput tests
pytest tests/performance/ -k "throughput" -v -s

# Expected throughput targets:
# - Market data: >1,000 ticks/second
# - Signal generation: >50 signals/second
# - Order processing: >10 orders/second
```

### Memory and Resource Testing

```bash
# Memory usage tests
pytest tests/performance/ -k "memory" -v -s

# Resource utilization tests
pytest tests/performance/ -k "cpu" -v -s
```

## Fuzz Testing and Chaos Engineering

### Malformed Data Testing

```bash
# Test malformed market data handling
pytest tests/fuzz/ -k "malformed" -v

# Test adversarial order inputs
pytest tests/fuzz/ -k "adversarial" -v
```

### Property-Based Testing

```bash
# Hypothesis-based fuzzing
pytest tests/fuzz/ -k "hypothesis" -v

# Generate random test cases
python -c "from hypothesis import strategies as st; print(st.integers().example())"
```

### Chaos Engineering

```bash
# Component failure simulation
pytest tests/fuzz/ -k "chaos" -v

# Network instability testing
pytest tests/fuzz/ -k "network" -v

# Memory pressure testing
pytest tests/fuzz/ -k "memory_pressure" -v
```

## Continuous Integration

### GitHub Actions Integration

```yaml
# .github/workflows/test.yml
- name: Run Test Suite
  run: |
    make install-dev
    make ci
    
- name: Upload Coverage
  uses: codecov/codecov-action@v3
  with:
    files: ./test_reports/unit_coverage.xml
```

### Pre-commit Hooks

```bash
# Install pre-commit hooks
pre-commit install

# Run pre-commit checks
make pre-commit

# Pre-commit configuration in .pre-commit-config.yaml
```

## Troubleshooting

### Common Issues

1. **Import Errors**
   ```bash
   # Add project root to Python path
   export PYTHONPATH="${PYTHONPATH}:$(pwd)"
   ```

2. **Database Connection Issues**
   ```bash
   # Use test database
   export DATABASE_URL=sqlite:///test.db
   ```

3. **Slow Tests**
   ```bash
   # Run only fast tests
   pytest tests/ -m "not slow" -v
   ```

4. **Memory Issues**
   ```bash
   # Run tests with reduced parallelism
   pytest tests/ -n 2  # Instead of -n auto
   ```

### Debug Mode

```bash
# Run with debugging
pytest tests/unit/test_features.py -v -s --pdb

# Add breakpoints in code
import pdb; pdb.set_trace()

# Use ipdb for enhanced debugging
import ipdb; ipdb.set_trace()
```

### Test Data Issues

```bash
# Refresh test fixtures
make test-data-refresh

# Generate new market data
python -c "from tests.fixtures.market_data import generate_test_data; generate_test_data()"
```

## Test Reports

Test execution generates comprehensive reports:

```
test_reports/
├── unit_coverage_html/          # HTML coverage report
├── unit_coverage.xml            # XML coverage report  
├── unit_junit.xml               # JUnit test results
├── performance_benchmarks.json  # Performance metrics
├── security_bandit.json         # Security scan results
└── test_summary_TIMESTAMP.json  # Execution summary
```

### Viewing Reports

```bash
# Coverage report
open test_reports/unit_coverage_html/index.html

# Test results summary
python -c "
import json
with open('test_reports/test_summary_latest.json') as f:
    summary = json.load(f)
    print(f'Tests: {summary.get(\"tests_run\", 0)}')
    print(f'Coverage: {summary.get(\"coverage_percent\", 0):.1f}%')
"
```

## Best Practices

### Development Workflow

1. **Before coding**: `make test-smoke` (30s)
2. **After changes**: `make test-unit` (2-5min)
3. **Before commits**: `make pre-commit` (1-2min)
4. **Before PRs**: `make ci` (5-10min)
5. **Before releases**: `make pre-release` (30-60min)

### Writing Tests

```python
# Good test structure
def test_feature_calculation_with_edge_cases(self, sample_data):
    """Test feature calculation handles edge cases properly."""
    # Arrange
    calculator = FeatureCalculator()
    edge_case_data = sample_data.copy()
    edge_case_data['close'] = [100.0] * len(edge_case_data)  # No movement
    
    # Act  
    features = calculator.calculate_features(edge_case_data)
    
    # Assert
    assert features['rsi'] is not None
    assert 0 <= features['rsi'] <= 100
    assert features['volatility'] >= 0
```

### Performance Test Guidelines

```python
# Performance test with clear assertions
def test_feature_latency_requirement(self):
    """Feature calculation must complete within latency requirements."""
    profiler = PerformanceProfiler().start()
    
    # ... test code ...
    
    stats = profiler.stop()
    
    # Clear performance requirements
    assert stats['p50_latency_ms'] < 5.0, "P50 latency too high"
    assert stats['p95_latency_ms'] < 20.0, "P95 latency too high"
```

## Integration with IDEs

### VS Code

```json
// .vscode/settings.json
{
    "python.testing.pytestEnabled": true,
    "python.testing.pytestArgs": ["tests/"],
    "python.testing.cwd": "${workspaceFolder}"
}
```

### PyCharm

1. Go to **Settings** → **Tools** → **Python Integrated Tools**
2. Set **Default test runner** to **pytest**
3. Set **Working directory** to project root

## Monitoring and Alerting

### Test Metrics

Track these key metrics:

- **Test Execution Time**: Should remain stable
- **Coverage Percentage**: Should maintain >90%
- **Flaky Test Rate**: Should be <1%
- **Performance Regression**: Latency should not increase >10%

### Alerts

Set up alerts for:

- Test failure rate >5%
- Coverage drop >2%
- Performance regression >20%
- Security vulnerabilities detected
