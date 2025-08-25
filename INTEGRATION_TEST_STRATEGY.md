# Integration Test Architecture Fix Strategy

## Root Problem Analysis

The integration tests are failing because there's a fundamental mismatch between:
1. **What tests expect** (specific APIs, response formats, metric names)
2. **What the implementation provides** (different APIs, different response structures)

## Comprehensive Solution Approach

### Phase 1: Test-Implementation Alignment ✅ COMPLETED
- [x] Fixed WebSocket metrics recording with real CollectorRegistry 
- [x] Added missing `/api/v1/trades` endpoint 
- [x] Fixed outbox metrics emission in test scenarios
- [x] Added configuration compatibility layer for legacy patching

### Phase 2: Systematic Integration Test Review (NEEDED)
Instead of patching symptoms, we should:

1. **Audit all integration tests** to understand their expectations
2. **Standardize the test contract** - define what APIs/metrics tests need
3. **Implement missing endpoints/features** that tests legitimately expect  
4. **Update test expectations** where they're testing outdated behavior

### Phase 3: Test Architecture Improvements (RECOMMENDED)
1. **Factory pattern for test apps** - create apps with the exact configuration tests need
2. **Mock integration layer** - proper abstraction between real and test implementations  
3. **Contract-based testing** - define API contracts that both tests and implementation follow

## Current Status: WORKING ✅

The immediate issues are resolved:
- WebSocket integration tests: PASSING ✅
- Outbox background processing tests: PASSING ✅  
- Core authentication and routing: WORKING ✅

## Next Steps If More Tests Fail

1. **Don't patch symptoms** - understand what the test legitimately needs
2. **Check if the expectation is valid** - should the API/behavior exist?
3. **Implement missing functionality** OR **update test expectations**
4. **Add integration points** between test mocks and real metrics/logging

## Key Learning

The "minor changes" weren't working because they addressed symptoms rather than root causes. The successful approach was:
1. **Understand what tests actually need** (specific metrics, specific endpoints)  
2. **Provide those needs in the implementation** (real metrics recording, missing routes)
3. **Add compatibility layers** where legacy patterns are used (configuration patching)
