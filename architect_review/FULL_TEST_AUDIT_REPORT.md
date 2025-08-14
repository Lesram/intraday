# 🔍 FULL TEST AUDIT REPORT
*Generated: 2025-08-13 11:58:08*

## 📊 Executive Summary

**Overall Status**: ❌ SIGNIFICANT FAILURES  
**Exit Code**: 2  
**Total Tests**: 4  
**Pass Rate**: 0.0%  
**Coverage**: 0.0%  

### Per-Category Results
| Category | Tests | Pass Rate | Duration | Status |
|----------|-------|-----------|----------|--------|
| chaos | 1 | 0.0% | 6.0s | ❌ |
| e2e | 1 | 0.0% | 0.2s | ❌ |
| integration | 1 | 0.0% | 6.2s | ❌ |
| perf | 1 | 0.0% | 5.3s | ❌ |

### Per-Package Coverage
| Package | Coverage | Covered/Total |
|---------|----------|---------------|

## 🚨 Top Failures (Grouped)

### AttributeError (1 occurrences)
**Suspected Subsystem**: services  
**Example**: tests\chaos\test_broker_faults.py:92: in test_broker_502_503_retry_pattern  

### TypeError (1 occurrences)
**Suspected Subsystem**: api  
**Example**: tests\e2e\test_system_integration.py:71: in test_full_system_startup_shutdown  

### ModuleNotFoundError (1 occurrences)
**Suspected Subsystem**: api  
**Example**: tests\integration\test_api_startup_shutdown.py:25: in ephemeral_app  

### ValueError (1 occurrences)
**Suspected Subsystem**: unknown  
**Example**: tests\perf\test_feature_perf.py:61: in test_feature_computation_performance  


## ⏱️ Performance & Flakiness

### Top 20 Slowest Tests
| Test | Duration |
|------|----------|

## 📉 Coverage Gaps

### Top 10 Files by Missed Lines
| File | Missed Lines | Total Lines | Coverage |
|------|--------------|-------------|----------|

## 🏥 System Health Assessment

### API Health
✅ Using factory pattern (create_app)

### WebSocket Health
Coverage: 0.0%
❌ WebSocket manager coverage <30%

### Database Health
✅ No database issues detected

## 📋 Architect Review Checklist

The following artifacts are available for independent review:

✅ **Available Artifacts**
- test_reports/coverage.xml (for IDE integration)
- test_reports/htmlcov/ (interactive coverage browser)  
- test_reports/junit/*.xml (CI/CD integration)
- architect_review/FULL_TEST_AUDIT_REPORT.md (this report)

🔍 **Missing Artifacts** (would help review):
- openapi.json (API schema)

---
*End of Report*
