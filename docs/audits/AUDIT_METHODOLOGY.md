# Comprehensive Algotrading Platform Audit Prompt

## Mission Statement
Perform an exhaustive, line-by-line analysis of the entire algotrading platform codebase. This audit must evaluate every aspect of the system from algorithmic trading logic to frontend UI/UX, producing actionable findings with severity ratings and specific remediation recommendations.

---

## 🎯 AUDIT OBJECTIVES

### Primary Goals
1. **Assess Production Readiness** - Is this platform ready for live trading with real capital?
2. **Identify Critical Defects** - Find bugs, security vulnerabilities, and logic errors that could cause financial loss
3. **Evaluate Code Quality** - Rate maintainability, testability, and adherence to best practices
4. **Measure Performance** - Identify bottlenecks, inefficiencies, and scalability concerns
5. **Review User Experience** - Evaluate frontend design, usability, and accessibility

### Deliverables Expected
- Severity-rated findings (Critical/High/Medium/Low/Info)
- Specific file paths and line numbers for each finding
- Remediation recommendations with code examples where applicable
- Executive summary with overall platform grade (A-F)
- Prioritized action items roadmap

---

## 📊 AUDIT SCOPE & METHODOLOGY

### Phase 1: Architecture & Structure Analysis
**Objective:** Understand the overall system design and organization

**Tasks:**
1. Map the complete directory structure and explain the purpose of each folder
2. Identify all entry points (main.py, API routes, WebSocket handlers)
3. Document the data flow: User Request → API → Service → Database → Response
4. Evaluate separation of concerns (MVC/Clean Architecture compliance)
5. Check for circular dependencies and import issues
6. Assess configuration management (environment variables, secrets handling)

**Questions to Answer:**
- Is the architecture appropriate for a trading platform?
- Are there clear boundaries between layers (API, Service, Data, Domain)?
- How well does the structure support testing and maintenance?
- Is there unnecessary complexity or over-engineering?

**Files to Examine:**
- `backend/__init__.py` and all `__init__.py` files
- `backend/api/factory.py` - Application factory
- `backend/api/main.py` - Entry point
- `main.py` - Root entry point
- All route registration files
- Dependency injection patterns

---

### Phase 2: Trading Algorithm Deep Dive
**Objective:** Validate the correctness and effectiveness of trading logic

**Tasks:**
1. **Strategy Analysis** - Review each trading strategy implementation:
   - `backend/strategies/` - All strategy files
   - Validate buy/sell signal logic
   - Check for edge cases (market gaps, holidays, halted stocks)
   - Verify position sizing calculations
   - Assess stop-loss and take-profit logic

2. **Technical Indicators Review** - `backend/services/indicators.py`:
   - Verify mathematical correctness of each indicator (SMA, EMA, RSI, MACD, etc.)
   - Cross-reference formulas against authoritative sources (Investopedia, TradingView)
   - Test edge cases: empty data, single data point, NaN handling
   - Validate rolling window calculations

3. **Backtesting Engine** - `backend/services/backtest_service.py`:
   - Check for look-ahead bias
   - Verify proper handling of slippage and commissions
   - Validate trade execution simulation accuracy
   - Assess metrics calculations (Sharpe, Sortino, max drawdown)

4. **Order Execution Flow**:
   - `backend/services/order_service.py`
   - `backend/data/alpaca_client.py`
   - Verify order lifecycle management
   - Check idempotency and duplicate order prevention
   - Validate error handling for failed orders

**Critical Questions:**
- Could any strategy logic cause unexpected large losses?
- Are there race conditions in order execution?
- Is there proper handling of partial fills?
- How does the system behave during market volatility?

---

### Phase 3: Risk Management Audit
**Objective:** Ensure the platform protects against catastrophic losses

**Tasks:**
1. **Review Risk Controls** - `backend/risk/`:
   - `risk_manager.py` - Core risk logic
   - Position limits enforcement
   - Daily loss limits
   - Drawdown protection
   - Correlation risk assessment

2. **Validate Pre-Trade Checks**:
   - `backend/infra/order_guardrails.py`
   - Maximum order size limits
   - Buying power validation
   - Symbol validation and restrictions

3. **Emergency Stop Mechanisms**:
   - Kill switch functionality
   - Circuit breakers
   - Automatic position liquidation
   - Alerting and notification systems

**Critical Questions:**
- What happens if the database goes down during trading hours?
- How does the system handle network failures to Alpaca?
- Is there a way to immediately halt all trading?
- Are there any bypasses to risk limits?

---

### Phase 4: Backend Code Quality
**Objective:** Evaluate code craftsmanship and maintainability

**Tasks:**
1. **Python Best Practices**:
   - Type hints coverage and correctness
   - Docstring completeness
   - PEP 8 compliance
   - Use of modern Python features (3.10+)

2. **Async/Await Correctness**:
   - Proper use of async throughout FastAPI routes
   - No blocking calls in async functions
   - Correct exception handling in async context
   - Connection pool management

3. **Database Layer** - `backend/database/`, `backend/infra/db.py`:
   - SQLAlchemy model definitions
   - Query efficiency (N+1 problems, missing indexes)
   - Transaction management
   - Migration handling (Alembic)

4. **Error Handling**:
   - Exception hierarchy and custom exceptions
   - Logging quality and consistency
   - Error response formats
   - Graceful degradation patterns

5. **Code Duplication**:
   - Identify repeated patterns that should be abstracted
   - Check for copy-paste code across files
   - Assess DRY principle adherence

**Files to Examine:**
- All files in `backend/services/`
- All files in `backend/api/routes/`
- All files in `backend/models/`
- `backend/utils/` helpers

---

### Phase 5: API Design Review
**Objective:** Evaluate REST API design and consistency

**Tasks:**
1. **Endpoint Analysis**:
   - RESTful conventions compliance
   - HTTP method appropriateness
   - URL structure consistency
   - Query parameter patterns

2. **Request/Response Schemas**:
   - Pydantic model completeness
   - Validation rules adequacy
   - Serialization consistency
   - API versioning strategy

3. **Authentication & Authorization**:
   - `backend/infra/security.py`
   - `backend/api/routes/auth.py`
   - JWT implementation security
   - Role-based access control
   - Token refresh mechanism

4. **API Documentation**:
   - OpenAPI/Swagger completeness
   - Endpoint descriptions
   - Example requests/responses

---

### Phase 6: Frontend Analysis
**Objective:** Evaluate user interface quality and user experience

**Tasks:**
1. **Code Structure** - `frontend/`:
   - Framework usage (React, Vue, etc.)
   - Component organization
   - State management patterns
   - API integration layer

2. **UI/UX Evaluation**:
   - Dashboard layout and information hierarchy
   - Chart visualization quality
   - Form design and validation feedback
   - Error state handling
   - Loading states and skeleton screens
   - Mobile responsiveness

3. **Trading Interface**:
   - Order entry form usability
   - Position display clarity
   - P&L visualization
   - Risk metric presentation

4. **Performance**:
   - Bundle size analysis
   - Lazy loading implementation
   - WebSocket real-time updates
   - Render performance

5. **Accessibility**:
   - WCAG compliance level
   - Keyboard navigation
   - Screen reader compatibility
   - Color contrast ratios

---

### Phase 7: Security Audit
**Objective:** Identify vulnerabilities that could be exploited

**Tasks:**
1. **Authentication Security**:
   - Password hashing algorithm (should be bcrypt/argon2)
   - JWT secret strength and rotation
   - Session management
   - Brute force protection

2. **Input Validation**:
   - SQL injection prevention
   - XSS prevention
   - CSRF protection
   - Command injection vectors

3. **API Security**:
   - Rate limiting implementation
   - CORS configuration
   - Sensitive data exposure
   - Insecure direct object references

4. **Secrets Management**:
   - Hardcoded credentials (CRITICAL)
   - API key exposure
   - Environment variable handling
   - Secrets in version control

5. **Dependency Security**:
   - Vulnerable packages (run `pip-audit` or `safety check`)
   - Outdated dependencies
   - License compliance

**Files to Scrutinize:**
- `.env*` files
- `backend/config.py`
- `backend/settings.py`
- All auth-related files
- Database connection strings

---

### Phase 8: Performance & Scalability
**Objective:** Identify bottlenecks and scalability concerns

**Tasks:**
1. **Database Performance**:
   - Index coverage analysis
   - Query execution plans for critical queries
   - Connection pool sizing
   - Read replica strategy

2. **API Performance**:
   - Response time benchmarks
   - Concurrent request handling
   - Memory usage patterns
   - CPU-bound vs I/O-bound operations

3. **Real-Time Data**:
   - WebSocket implementation efficiency
   - Market data streaming performance
   - Event propagation latency

4. **Caching Strategy**:
   - Cache hit/miss patterns
   - Cache invalidation logic
   - Redis usage (if applicable)

5. **Scalability Assessment**:
   - Stateless vs stateful components
   - Horizontal scaling readiness
   - Microservices extraction potential

---

### Phase 9: Testing & Quality Assurance
**Objective:** Evaluate test coverage and quality

**Tasks:**
1. **Test Coverage Analysis**:
   - Run `pytest --cov` and analyze report
   - Identify untested critical paths
   - Assess test quality (not just quantity)

2. **Test Organization**:
   - Unit vs integration vs e2e split
   - Test isolation and independence
   - Fixture and mock patterns
   - CI/CD pipeline review

3. **Critical Path Coverage**:
   - Order execution flow tested?
   - Risk management tested?
   - Authentication flow tested?
   - Error scenarios tested?

---

### Phase 10: DevOps & Deployment
**Objective:** Evaluate deployment readiness and infrastructure

**Tasks:**
1. **Containerization**:
   - Dockerfile best practices
   - docker-compose configuration
   - Image size optimization
   - Multi-stage builds

2. **Configuration Management**:
   - Environment-specific configs
   - Feature flags
   - Secrets injection

3. **Observability**:
   - Logging implementation
   - Metrics collection (Prometheus)
   - Distributed tracing
   - Alerting setup

4. **Deployment Strategy**:
   - Blue-green or canary deployment
   - Rollback procedures
   - Health check endpoints
   - Graceful shutdown handling

---

## 📋 AUDIT OUTPUT FORMAT

### For Each Finding, Document:

```markdown
### [SEVERITY] Finding Title

**Location:** `path/to/file.py` lines X-Y

**Description:** 
Clear explanation of the issue

**Impact:**
What could go wrong if not addressed

**Evidence:**
```python
# Code snippet showing the problem
```

**Recommendation:**
```python
# Code snippet showing the fix
```

**Effort:** Low/Medium/High
**Priority:** P1/P2/P3/P4
```

### Severity Definitions:
- **CRITICAL**: Could cause financial loss, security breach, or system failure
- **HIGH**: Significant impact on functionality, performance, or security
- **MEDIUM**: Moderate impact, should be addressed in near term
- **LOW**: Minor issues, code quality improvements
- **INFO**: Observations, best practice suggestions

---

## 🔍 SPECIFIC AREAS TO DEEP DIVE

### Must-Review Files (Read Every Line):
1. `backend/services/order_service.py` - Order execution logic
2. `backend/data/alpaca_client.py` - Broker API integration
3. `backend/risk/risk_manager.py` - Risk controls
4. `backend/strategies/engine.py` - Strategy execution engine
5. `backend/services/indicators.py` - Technical indicators
6. `backend/infra/security.py` - Authentication
7. `backend/api/routes/auth.py` - Auth endpoints
8. `backend/api/routes/orders.py` - Order endpoints
9. `backend/services/backtest_service.py` - Backtesting

### Configuration Files:
1. `backend/config.py`
2. `backend/settings.py`
3. `backend/config/base_settings.py`
4. `.env`, `.env.paper`, `.env.production`
5. `docker-compose*.yml`
6. `alembic.ini`

### Frontend Critical Paths:
1. Main dashboard component
2. Order entry form
3. Position display
4. Chart components
5. WebSocket connection handling

---

## 📊 FINAL DELIVERABLES

1. **Executive Summary** (1 page)
   - Overall platform grade (A-F)
   - Top 5 critical findings
   - Production readiness assessment
   - Recommended go/no-go decision

2. **Detailed Findings Report** (comprehensive)
   - All findings organized by severity
   - Each with location, description, and remediation

3. **Architecture Diagram**
   - Visual representation of system components
   - Data flow illustration
   - Integration points

4. **Prioritized Remediation Roadmap**
   - Sprint-ready task breakdown
   - Effort estimates
   - Dependency mapping

5. **Test Gap Analysis**
   - Missing test scenarios
   - Recommended additional tests

---

## 🚀 EXECUTION INSTRUCTIONS

### For AI Agent Execution:

1. **Start with Structure**: Use `list_dir` to map the complete directory tree
2. **Read Systematically**: Process files in order of criticality (see Must-Review list)
3. **Use grep_search**: Find patterns across codebase (e.g., `TODO`, `FIXME`, hardcoded values)
4. **Cross-Reference**: When reviewing a service, also check its tests, routes, and models
5. **Run Analysis Tools**: Execute `pytest --cov`, `ruff check`, type checking where possible
6. **Document As You Go**: Create findings immediately upon discovery
7. **Synthesize**: After individual analysis, look for systemic patterns

### Time Allocation Guidance:
- Phase 1 (Architecture): 10%
- Phase 2 (Trading Logic): 20% ← Most critical
- Phase 3 (Risk Management): 15% ← Critical for safety
- Phase 4 (Backend Quality): 15%
- Phase 5 (API Design): 5%
- Phase 6 (Frontend): 10%
- Phase 7 (Security): 10% ← Critical for protection
- Phase 8 (Performance): 5%
- Phase 9 (Testing): 5%
- Phase 10 (DevOps): 5%

---

## ⚠️ RED FLAGS TO WATCH FOR

### Immediate Stop-and-Report Items:
1. Hardcoded credentials or API keys
2. SQL injection vulnerabilities
3. Missing authentication on sensitive endpoints
4. Race conditions in order execution
5. No position limits or broken risk controls
6. Look-ahead bias in backtesting
7. Incorrect indicator calculations that affect trading decisions
8. Missing error handling on broker API calls
9. No kill switch or emergency stop mechanism
10. Storing passwords in plaintext

---

## 📝 NOTES FOR AUDITOR

- This is a **paper trading** platform currently, but assess as if it will handle real capital
- The platform uses **Alpaca** as the broker API
- Backend is **FastAPI** with **PostgreSQL** and **SQLAlchemy 2.0 async**
- Frontend framework should be identified during audit
- Recent cleanup removed 166 root-level Python files (check for any remnants)
- Previous audit gave architecture grade of 7.5/10 - validate or update this

---

*This audit prompt version: 1.0*
*Created: January 18, 2026*
*Platform: Algotrading Platform*
