# Phase 2C Implementation Plan - Third Wave Coverage Expansion

## Executive Summary

**Phase 2C** targets medium-complexity modules using the proven direct import testing approach from Phases 2A and 2B, focusing on utility and service modules with moderate statement counts.

**Target Modules**: 3 modules with ~150-200 total statements
**Expected Impact**: ~1.5% coverage improvement (from ~14.3% to ~15.8%)
**Timeline**: Immediate implementation using established patterns

## Phase 2C Target Modules - FINALIZED

### 1. backend/risk/risk_calculator.py ⭐ **PRIMARY TARGET**
- **Size**: 61 lines (estimated ~25-30 statements)
- **Purpose**: Risk calculation utilities and metrics
- **Current Coverage**: 0% (no dedicated tests found)
- **Complexity**: MEDIUM - Class-based with calculation methods
- **Test Strategy**: Direct class testing with metric calculations

**Key Functions to Cover:**
- `RiskCalculator.__init__()`
- `RiskCalculator.calculate_metrics()`
- `RiskCalculator.check_position_limits()`
- Risk calculation logic and edge cases

### 2. backend/services/signal_service.py ⭐ **SECONDARY TARGET**
- **Size**: 68 lines (estimated ~30-35 statements)
- **Purpose**: Signal service for generating and managing trading signals
- **Current Coverage**: Partial (mocked in integration tests only)
- **Complexity**: MEDIUM - Async service class with signal generation
- **Test Strategy**: Direct async class testing with signal generation

**Key Functions to Cover:**
- `SignalService.__init__()`
- `SignalService.get_signals()` (async)
- Signal generation logic for different symbols
- Signal data structure validation

### 3. backend/infra/broker.py ⭐ **TERTIARY TARGET**
- **Size**: 71 lines (estimated ~35-40 statements)
- **Purpose**: Broker health check utilities
- **Current Coverage**: 0% (no dedicated tests found)
- **Complexity**: MEDIUM - Async health checking with Redis integration
- **Test Strategy**: Direct async function testing with mocked Redis

**Key Functions to Cover:**
- `broker_health_check()` (async)
- Redis connection handling
- Error handling and fallbacks
- Health check response validation

## Implementation Strategy

### Phase 2C Proven Pattern
Using the successful approach from Phases 2A and 2B:

```python
# Direct module import pattern with importlib
import importlib.util
module_path = os.path.join(self.backend_path, 'module_dir', 'module_file.py')
spec = importlib.util.spec_from_file_location("module_name", module_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
```

### Test File Creation Plan
1. **tests/unit/test_risk_calculator_direct.py** - Risk calculation coverage
2. **tests/unit/test_signal_service_direct.py** - Signal service coverage  
3. **tests/unit/test_broker_health_direct.py** - Broker health check coverage

## Success Metrics

### Phase 2C Completion Criteria
✅ **All target modules achieve 100% statement execution**  
✅ **All tests pass with 100% success rate**  
✅ **Direct import patterns validated on medium-complexity modules**
✅ **Coverage improvement of ~1.5% measured**

### Progress Tracking
- **Module 1 (risk_calculator.py)**: Target ~25-30 statements → Expected 8-10 tests
- **Module 2 (signal_service.py)**: Target ~30-35 statements → Expected 10-12 tests  
- **Module 3 (broker.py)**: Target ~35-40 statements → Expected 12-15 tests

**Total Expected**: ~90-105 statements, ~30-37 tests across 3 modules

## Advanced Technical Challenges

### Phase 2C Specific Complexity
- **Async testing**: Both signal_service.py and broker.py are async
- **External dependencies**: broker.py uses Redis (needs mocking)
- **Business logic**: risk_calculator.py involves financial calculations
- **Service patterns**: Testing service classes vs utility functions

### Solutions Planned
- **pytest-asyncio**: For async method testing
- **Mock external services**: Redis, database connections
- **Decimal precision**: Financial calculation accuracy
- **Service initialization**: Class instantiation and state management

---

**Status: READY FOR PHASE 2C IMPLEMENTATION** 🚀
