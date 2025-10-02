# Legacy Individual Tests Archive

**Archive Date:** October 1, 2025

## Purpose

This directory contains legacy test files that have been superseded by the modern consolidated testing architecture. These files are preserved for historical reference but are no longer actively maintained or executed.

## Archived Files

### PowerShell Test Runners (Archived October 1, 2025)

1. **run_comprehensive_tests.ps1** (6,666 bytes)
   - Last Modified: September 30, 2025
   - Reason: Superseded by `run_complete_five_layer_tests.py` with modern orchestration
   - Legacy approach: Ran individual test files sequentially
   - Modern replacement: Consolidated Layers 1-4 + Layer 5 business workflows

2. **run_enhanced_comprehensive_tests.ps1** (9,459 bytes)
   - Last Modified: September 30, 2025
   - Reason: Superseded by modern testing framework with better reporting
   - Legacy approach: Enhanced version with more detailed output
   - Modern replacement: `automated_promotion_gates.py` and `burn_in_framework.py`

## Testing Architecture Evolution

### Phase 1: Individual Tests (Pre-September 30, 2025)
- Individual test files for each component (environment, core, ML, API, etc.)
- Separate PowerShell runners for orchestration
- Fragmented coverage and reporting

### Phase 2: Consolidation (September 30 - October 1, 2025)
- Layers 1-4 consolidated into `test_layers_1_to_4_consolidated.py`
- Layer 5 business workflows in `test_layer5_business_workflows.py`
- Modern orchestration with `run_complete_five_layer_tests.py`
- Integrated K6 performance testing with `k6_enhanced_comprehensive_test.js`

### Phase 3: Production Validation (October 1, 2025)
- Automated promotion gates with 6-phase validation
- Burn-in framework with multi-session stability testing
- Quick burn-in for rapid developer feedback
- Pre-deployment validation checklists

## Modern Testing Suite

The current production testing suite consists of:

### Core Test Files (Production)
- `test_layers_1_to_4_consolidated.py` - Foundation tests (Layers 1-4)
- `test_layer5_business_workflows.py` - Business workflows and end-to-end tests
- `test_k6_performance.py` - K6 integration and performance validation
- `k6_enhanced_comprehensive_test.js` - Load testing with authentication

### Orchestration & Validation (Production)
- `run_complete_five_layer_tests.py` - Main test orchestrator
- `automated_promotion_gates.py` - 6-phase deployment validation
- `burn_in_framework.py` - 135-minute stability testing
- `quick_burn_in_test.py` - Rapid developer feedback (15 minutes)
- `check_services_availability.py` - Service health diagnostics

### Supporting Infrastructure (Production)
- `k6_cache_manager.py` - K6 caching for improved performance
- `run_all_tests.py` - Legacy compatibility wrapper

### Specialized Tests (Still Active)
- `test_jwt_auth_security.py` - JWT authentication and security testing
- `test_security_performance.py` - Security performance validation
- `test_paper_trading_integration.py` - Paper trading workflow validation
- `ai_enhancement_integration_test.py` - AI integration testing

## K6 Debug Files (Removed October 1, 2025)

The following K6 files were debugging artifacts from authentication troubleshooting and have been **permanently removed**:

1. **k6_simple_test.js** - Basic K6 test for initial setup verification
2. **k6_debug_auth.js** - Authentication debugging script
3. **k6_simple_metrics_test.js** - Simple metrics collection test

These files served their purpose during the authentication implementation phase and are no longer needed. The production K6 test is `k6_enhanced_comprehensive_test.js`.

## When to Use Archived Files

**Recommendation: Do not use these files.** They are kept only for historical reference.

If you need to understand the evolution of the testing architecture, refer to:
- This README
- `COMPREHENSIVE_TESTING_ARCHITECTURE.md` in scripts/testing/
- `TESTING_ARCHITECTURE_ANALYSIS.md` in project root

## Migration Notes

If you were previously using:
- `run_comprehensive_tests.ps1` → Use `.\venv\Scripts\python.exe scripts/testing/run_complete_five_layer_tests.py`
- `run_enhanced_comprehensive_tests.ps1` → Use automated promotion gates or burn-in framework
- Individual test files → Use consolidated Layer 1-4 tests or Layer 5 business workflows

## Questions?

For questions about the modern testing architecture, see:
- `scripts/testing/README.md` - Testing suite overview
- `scripts/testing/COMPREHENSIVE_TESTING_ARCHITECTURE.md` - Detailed architecture documentation
- `TESTING_ARCHITECTURE_ANALYSIS.md` - Analysis and recommendations (October 1, 2025)
