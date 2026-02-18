# 🔍 PRE-TRADING PHASE COMPREHENSIVE AUDIT PROMPT
## Production Readiness Assessment Before Algorithm Training & Trading Strategy Phase
### January 23, 2026

---

## AUDIT CONTEXT

This is a **comprehensive pre-production audit** conducted after completing multiple rounds of remediation. The platform has undergone two major audit cycles with all identified issues addressed:

### Audit History & Resolved Issues

**First Audit Cycle (January 18-19, 2026) - 12 Issues Resolved:**
- CRITICAL: Circuit breaker in-memory state → Redis persistence (26 tests)
- CRITICAL: Unsafe eval() in ML pipeline → AST-based SafeExpressionEvaluator (46 tests)
- CRITICAL: Unsigned pickle → HMAC-SHA256 signing (25 tests)
- HIGH: Unresolved TODOs, missing log scrubbing, bare exceptions
- MEDIUM: Risk manager positions, rate limit docs, DB initialization, Redis HA

**Second Audit Cycle (January 20, 2026) - 8 Issues Resolved:**
- CRITICAL: Unsecured pickle.load() in ML Model Manager → secure_load()
- HIGH: Unsecured pickle.loads() in Cache Service → secure_loads()
- HIGH: Print statements in production code (addressed in __main__ blocks)
- HIGH: Test fixture infrastructure → Fixed conftest.py
- MEDIUM: JWT secret in K8s, Alpaca error handling, memory monitor threading

### Current Test Suite Status (As of January 23, 2026)
```
626 passed, 85 skipped, 0 failed, 96 warnings
```

### Next Phase: Algorithm Training & Trading Strategy
This audit prepares the platform for the trading intelligence phase:
- ML model training pipelines
- Trading algorithm logic
- Strategy execution engine
- Real-time signal generation
- Backtesting framework

---

## MISSION STATEMENT

You are a senior principal engineer and trading systems architect conducting a **pre-production readiness audit** with focus on:

1. **Code Hygiene** - Eliminate all leftover mocks, stubs, placeholders, and test artifacts
2. **Performance Optimization** - Ensure sub-millisecond execution paths
3. **Security Hardening** - Final security sweep before production
4. **Error Handling** - Comprehensive error paths and graceful degradation
5. **Trading Logic Readiness** - Prepare infrastructure for algorithm implementation

---

## PHASE 1: CODE HYGIENE DEEP DIVE

### 1.1 Mock/Stub/Placeholder Elimination

**CRITICAL: Search for and eliminate all production mocks**

```
Priority locations to audit:
□ backend/mlops/model_manager.py
  - Lines 477-505: MockVersion class in train_model()
  - Lines 1285: "stub mode" reference
  - Lines 1429, 1455: Mock prediction returns
  - Lines 1865-1869: Mock feature importance
  - Lines 1925-1935: Stub compatibility functions

□ backend/risk/risk_manager.py
  - Lines 765-780: Placeholder methods (get_portfolio_state, get_historical_returns)
  - Lines 807-878: Mock method detection in validate_order
  - Lines 1174-1178: MockRiskLimits class

□ backend/risk/risk_calculator.py
  - Line 53-54: "Shim function for testing" with mock response

□ backend/services/trade_service.py
  - Line 449: TODO comment for user_id="admin"

□ backend/services/portfolio_service.py
  - Line 231: TODO for actual historical data
```

**Questions to answer:**
1. Are any mocks being used in production code paths?
2. Can the platform run without mock fallbacks?
3. Are placeholder methods actually implemented or just returning dummy data?
4. What happens when a mock is not configured?

### 1.2 Print Statement Audit

**All print() calls must be replaced with proper logging**

```
Known locations requiring fix (verify if in __main__ blocks):
□ backend/utils/import_tracker.py (5 prints)
□ backend/risk/advanced_risk_manager.py (12 prints)
□ backend/optimization/portfolio_optimizer.py (20+ prints)
□ backend/analytics/realtime_risk_analytics.py
□ backend/monitoring/enhanced_slo_manager.py
□ backend/utils/utilities.py

Verify each print is:
- Inside if __name__ == "__main__": block (acceptable)
- Or replaced with logger.info/debug (required)
```

### 1.3 TODO/FIXME Audit

**Search and resolve all outstanding TODO comments**

```
Known outstanding TODOs:
□ backend/services/portfolio_service.py:231
  "TODO: Implement actual historical data from portfolio_history table"

□ backend/services/trade_service.py:449
  "TODO: Pass actual user_id when auth is fully implemented"

□ Any other TODO/FIXME/HACK/XXX markers
```

---

## PHASE 2: PERFORMANCE & EFFICIENCY ANALYSIS

### 2.1 Hot Path Optimization

**Identify and optimize critical execution paths**

```
Critical paths (target: <1ms):
□ Order placement: Signal → RiskCheck → Broker
□ Position update: Broker callback → Database → WebSocket
□ Market data: Ingest → Processing → Chart update

Audit checklist:
□ Unnecessary database queries in hot paths
□ Synchronous calls that could be async
□ Large object serialization/deserialization
□ Regex compilation in loops
□ String concatenation in loops
□ Excessive logging in hot paths
```

### 2.2 Database Query Optimization

```
Review each module for:
□ N+1 query patterns
□ Missing indexes on frequently queried columns
□ Unbounded SELECT queries (missing LIMIT)
□ Large result sets loaded into memory
□ Connection pool exhaustion risks
□ Transaction scope too large
```

### 2.3 Memory Management

```
Check for:
□ Unbounded caches or lists
□ Large DataFrame operations without chunking
□ Memory leaks in WebSocket connections
□ Circular references preventing garbage collection
□ Large objects held in closures
```

### 2.4 Async/Await Correctness

```
Verify:
□ No blocking I/O in async functions (file I/O, network without async)
□ No time.sleep() in async code (should be asyncio.sleep())
□ Proper use of asyncio.gather() for parallel operations
□ No await in loops that could be parallelized
□ Event loop not blocked by CPU-bound operations
```

---

## PHASE 3: SECURITY FINAL SWEEP

### 3.1 Serialization Security

**Verify all pickle operations use secure methods**

```
Search patterns:
□ pickle.load( → Must use secure_load() from backend/utils/secure_pickle.py
□ pickle.loads( → Must use secure_loads()
□ pickle.dump( → Verify signed with secure_dump()
□ pickle.dumps( → Verify signed with secure_dumps()

Known locations already fixed (verify still in place):
- backend/ml/model_manager.py: Lines 347, 1089, 1096, 1358 use secure_load()
- backend/services/cache.py: Lines 364, 416 use secure_loads()
```

### 3.2 Input Validation

```
For each API endpoint, verify:
□ Pydantic models with proper Field constraints
□ Path parameter validation (UUID format, numeric bounds)
□ Query parameter sanitization
□ Request body size limits
□ File upload restrictions (if any)
```

### 3.3 Authentication & Authorization

```
Verify:
□ All protected routes require valid JWT
□ Role-based access enforced where needed
□ API keys properly scoped
□ Session timeout configured
□ Rate limiting per user/IP
□ No hardcoded credentials
```

### 3.4 Secrets Management

```
Check:
□ No secrets in code (grep for password, secret, key, token)
□ Environment variables used for all secrets
□ .env.example has no real values
□ Docker compose references .env not inline values
□ K8s secrets properly configured
□ PICKLE_HMAC_SECRET environment variable required
```

---

## PHASE 4: ERROR HANDLING & RESILIENCE

### 4.1 Exception Handling Completeness

```
For each service, verify:
□ No bare except: clauses (use specific exceptions)
□ All exceptions logged with context
□ Errors propagated to caller with useful messages
□ No swallowed exceptions (except with logging)
□ Retry logic with backoff for transient failures
□ Circuit breaker integration where appropriate
```

### 4.2 Graceful Degradation

```
Test scenarios:
□ Redis unavailable → Application continues with fallback
□ PostgreSQL unavailable → Proper error response
□ Alpaca API unavailable → Orders queued or rejected cleanly
□ WebSocket disconnect → Automatic reconnection
□ ML model not loaded → Fallback or clear error
```

### 4.3 Error Response Consistency

```
All API errors should:
□ Use consistent error schema
□ Include correlation ID for tracing
□ Not leak internal implementation details
□ Provide actionable error messages
□ Use correct HTTP status codes
```

---

## PHASE 5: TRADING INFRASTRUCTURE READINESS

### 5.1 Strategy Engine Analysis

**File: backend/strategies/engine.py**

```
Verify:
□ Signal netting logic is mathematically correct
□ Throttling prevents excessive trading
□ Risk gating integration is complete
□ Position sizing calculations are accurate
□ Support for multiple concurrent strategies
□ Strategy configuration is validated
```

### 5.2 ML Pipeline Readiness

**Files: backend/ml/*.py**

```
For algorithm training phase:
□ Feature engineering pipeline is complete
□ Training service can handle large datasets
□ Model serialization uses secure pickle
□ Model versioning is implemented
□ A/B testing framework exists
□ Model monitoring for drift detection
□ Inference service is production-ready
```

### 5.3 Backtesting Framework

**File: backend/services/backtest_service.py**

```
Verify:
□ No look-ahead bias (signals execute on NEXT bar)
□ Transaction costs modeled
□ Slippage simulation
□ Position sizing respects capital limits
□ Multiple strategy backtests supported
□ Performance metrics calculation is accurate
□ Results can be compared across runs
```

### 5.4 Risk Management Integration

```
Verify complete integration:
□ Pre-trade risk checks called for all orders
□ Position limits enforced
□ Exposure limits enforced
□ Drawdown monitoring active
□ Circuit breaker triggers trading halt
□ Emergency stop functionality works
```

---

## PHASE 6: FRONTEND & REAL-TIME SYSTEMS

### 6.1 WebSocket Stability

```
Test:
□ Connection survives network interruption
□ Automatic reconnection with exponential backoff
□ State synchronization on reconnect
□ Message ordering guaranteed
□ No duplicate message processing
□ Memory stable under sustained connections
```

### 6.2 Chart Performance

```
For TradingView Lightweight Charts:
□ Large dataset rendering (<10ms for 10k candles)
□ Real-time updates don't cause redraws
□ Memory stable with continuous data
□ Indicator calculations are efficient
□ Drawing tools persist correctly
```

### 6.3 Bundle Optimization (Already Completed - Verify)

```
Verify optimizations in place:
□ Code splitting with React.lazy()
□ Vendor chunk separation
□ Charting libraries lazy-loaded
□ Initial bundle < 200KB gzipped
□ Page-level code splitting working
```

---

## PHASE 7: OPERATIONAL READINESS

### 7.1 Monitoring & Observability

```
Verify:
□ Prometheus metrics for key operations
□ Grafana dashboards configured
□ Log aggregation working
□ Distributed tracing enabled
□ Alerting rules defined
□ SLO/SLI tracking active
```

### 7.2 Deployment Configuration

```
Check:
□ Docker images build successfully
□ docker-compose.yml is complete
□ Kubernetes manifests are valid
□ Environment-specific configs exist
□ Database migrations are idempotent
□ Rollback procedure documented
```

### 7.3 Documentation

```
Ensure exists:
□ API documentation (OpenAPI/Swagger)
□ Architecture diagrams
□ Runbooks for common issues
□ Deployment guide
□ Development setup guide
□ Trading strategy documentation template
```

---

## DELIVERABLES

### Required Output Format

```markdown
# Pre-Trading Phase Audit Report
## Date: [DATE]

## Executive Summary
| Metric | Value |
|--------|-------|
| Overall Readiness | [GO/NO-GO] |
| Critical Issues | X |
| High Issues | Y |
| Medium Issues | Z |
| Tests Passing | N |

## Phase 1: Code Hygiene
### Mocks Found in Production
[List each mock with file:line and recommendation]

### Print Statements
[List each print not in __main__ block]

### Outstanding TODOs
[List each TODO with resolution recommendation]

## Phase 2: Performance
[Findings with benchmarks]

## Phase 3: Security
[Any remaining security concerns]

## Phase 4: Error Handling
[Gaps in error handling]

## Phase 5: Trading Infrastructure
[Readiness assessment for algorithm phase]

## Phase 6: Frontend
[Real-time systems status]

## Phase 7: Operations
[Deployment readiness]

## Recommendations for Trading Phase
1. [Prioritized action items]
2. ...

## Ready for Algorithm Training: [YES/NO]
```

---

## SUCCESS CRITERIA

### GO Criteria
- [ ] 0 Critical issues
- [ ] All HIGH issues have mitigation plan
- [ ] Test suite: 0 failures (skipped acceptable)
- [ ] No mocks in production code paths
- [ ] All print statements in __main__ or replaced with logging
- [ ] No unresolved security findings
- [ ] Strategy engine verified working
- [ ] ML pipeline ready for training
- [ ] Backtesting framework validated

### NO-GO Criteria (Any one blocks production)
- Any pickle.load/loads not using secure methods
- Mock data returned in production APIs
- Hardcoded credentials or secrets
- Circuit breaker not functional
- Risk management bypassed
- Test failures in core trading logic

---

## METHODOLOGY NOTES

1. **Use actual code inspection** - Read the files, don't assume
2. **Run the tests** - Verify test counts match expectations
3. **Trace code paths** - Follow signal from input to execution
4. **Test error scenarios** - What happens when things fail?
5. **Profile hot paths** - Measure actual performance
6. **Check edge cases** - Empty data, null values, boundary conditions

---

*This audit prompt is designed to ensure the platform is production-ready before entering the algorithm training and trading strategy development phase. All findings should be actionable with clear remediation paths.*
