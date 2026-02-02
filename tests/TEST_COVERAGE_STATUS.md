# Test Coverage Status Report
## Date: 2026-02-01 (Updated 18:12)

## 🎯 BASELINE ESTABLISHED

### Full Test Suite Run: 02/01/2026 18:11:53

| Metric | Value |
|--------|-------|
| **Test Files** | 316 |
| **Files Passed** | 278 (87.97%) |
| **Files Failed** | 38 (12.03%) |
| **Timeouts** | 0 |
| **Duration** | 13.32 minutes |

## Test Structure (Cleaned)

```
tests/
├── conftest.py            # Main pytest config
├── test_*.py              # 118 root level tests
├── unit/
│   ├── __init__.py
│   ├── test_*.py          # 36 unit tests
│   └── generated/         # 165 auto-generated tests
└── Utility files:
    ├── quick_coverage_check.ps1
    ├── run_all_tests_and_report.ps1
    ├── test_one_by_one.ps1
    └── TEST_COVERAGE_STATUS.md
```

**Total: 316 test files + 3 utility scripts + conftest.py**

## ❌ Failed Tests (38 files)

### Root Level Tests (22 failures)
| Test File | Category | Duration |
|-----------|----------|----------|
| test_admin_trading_execution_mode.py | Integration | 3.9s |
| test_alembic_head.py | Database/Migrations | 1.1s |
| test_api_routes_coverage.py | API | 5.3s |
| test_backtest_api_integration.py | Integration | 17.1s |
| test_idempotency.py | API | 1.4s |
| test_ml_lifecycle_api.py | ML/API | 4.6s |
| test_models_api.py | API | 1.6s |
| test_models_api_simple.py | API | 24.8s |
| test_order_integrity_comprehensive.py | Orders | 1.7s |
| test_order_lifecycle.py | Orders | 1.5s |
| test_order_validation.py | Orders | 2.2s |
| test_performance_slo.py | SLO | 5.2s |
| test_position_management.py | Positions | 11.4s |
| test_pretrade_validation.py | Trading | 11.2s |
| test_real_data_integration.py | Integration | 1.7s |
| test_risk_api.py | Risk/API | 3.2s |
| test_risk_management_complete.py | Risk | 5.3s |
| test_route_registry.py | API | 11.6s |
| test_routes_registry.py | API | 5.3s |
| test_strategies_automated_suite.py | Strategies | 2.2s |
| test_trades_api.py | API | 1.5s |
| test_websocket_integration.py | WebSocket | 1.5s |

### Generated Tests (7 failures)
| Test File | Issue |
|-----------|-------|
| test_auto_audit.py | Module import/mock issue |
| test_auto_drawings.py | Module import/mock issue |
| test_auto_env.py | Environment config issue |
| test_auto_main.py | App startup issue |
| test_auto_memory_monitor.py | Mock issue |
| test_auto_order_integrity.py | Order validation issue |
| test_auto_watchlists.py | Mock issue |

### Unit Tests (9 failures)
| Test File | Issue |
|-----------|-------|
| test_api_routes_comprehensive.py | Route registration |
| test_api_routes_phase5.py | Route registration |
| test_auth_security_phase4.py | Auth fixtures |
| test_backend_modules_batch1.py | Import failures |
| test_backend_modules_batch2.py | Import failures |
| test_data_deployment.py | Deployment config |
| test_enums_comprehensive.py | Enum validation |
| test_mega_comprehensive_imports.py | Complex imports |
| test_models_comprehensive.py | Model validation |

## Failure Categories

| Category | Count | Priority |
|----------|-------|----------|
| API Route Tests | 8 | HIGH |
| Order/Trade Tests | 5 | HIGH |
| Integration Tests | 4 | MEDIUM |
| Import/Module Tests | 6 | MEDIUM |
| Risk Tests | 3 | HIGH |
| Other | 12 | LOW |

## 📈 Next Steps: Improving Coverage

### Priority 1: Fix API Route Tests (8 failures)
These tests are failing due to route registration issues:
- `test_api_routes_coverage.py`
- `test_api_routes_comprehensive.py`
- `test_api_routes_phase5.py`
- `test_route_registry.py`
- `test_routes_registry.py`
- `test_models_api.py`
- `test_models_api_simple.py`
- `test_trades_api.py`

### Priority 2: Fix Order/Risk Tests (8 failures)
Critical trading functionality:
- `test_order_integrity_comprehensive.py`
- `test_order_lifecycle.py`
- `test_order_validation.py`
- `test_risk_api.py`
- `test_risk_management_complete.py`
- `test_pretrade_validation.py`
- `test_position_management.py`
- `test_auto_order_integrity.py`

### Priority 3: Fix Integration Tests (4 failures)
- `test_admin_trading_execution_mode.py`
- `test_backtest_api_integration.py`
- `test_real_data_integration.py`
- `test_websocket_integration.py`

### Priority 4: Fix Import/Module Tests (6 failures)
- `test_backend_modules_batch1.py`
- `test_backend_modules_batch2.py`
- `test_mega_comprehensive_imports.py`
- `test_models_comprehensive.py`
- `test_enums_comprehensive.py`
- `test_data_deployment.py`

## Test Runner Commands

```powershell
# Run all tests one-by-one with timeout (recommended)
.\tests\test_one_by_one.ps1

# Quick coverage check
python -m pytest tests/ -q --cov=backend --cov-report=term --tb=no

# Run specific module tests
python -m pytest tests/unit/generated/ --cov=backend --cov-report=term-missing:skip-covered

# Run single failing test with verbose output
python -m pytest tests/test_api_routes_coverage.py -v --tb=long
```

## Session History

### 2026-02-01 18:12
- ✅ Cleaned tests directory (removed conftest_legacy.py, moved validate_indicator_accuracy.py)
- ✅ Ran full baseline: **316 files, 278 passed (87.97%), 38 failed**
- ✅ Zero timeouts - no hanging tests
- ✅ Duration: 13.32 minutes
