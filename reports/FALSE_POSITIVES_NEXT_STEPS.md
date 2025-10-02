# False Positives Audit - NEXT STEPS & VALIDATION PLAN

**Date**: October 2, 2025  
**Status**: 🚧 **READY FOR VALIDATION**  
**Branch**: fix/order-flow-gate  
**Completed**: 20 fixes implemented | **Remaining**: Validation & deployment

---

## 🎯 Executive Summary

All 20 critical false-positive paths have been **implemented**. Now we need to:

1. ✅ **Validate** all fixes work as expected
2. ✅ **Test** that bad paths now FAIL (good failures)
3. ✅ **Update** migration revision IDs
4. ✅ **Document** security waivers
5. ✅ **Deploy** to staging with confidence

**Time Estimate**: 2-3 hours for complete validation

---

## 📋 PHASE 1: Pre-Validation Setup (15 minutes)

### Step 1.1: Update Alembic Migration Revision ID ⚠️ REQUIRED

**Current Issue**: Migration has placeholder `down_revision = None`

**File**: `migrations/versions/add_idempotency_constraints.py:18`

**Action**:
```bash
# Get current head revision
alembic current

# Expected output: 
# abc123def456 (head)

# Update line 18 in add_idempotency_constraints.py:
# down_revision = 'abc123def456'  # Replace with actual head
```

**Manual Edit Required**:
1. Open `migrations/versions/add_idempotency_constraints.py`
2. Line 18: Replace `down_revision = None` with actual revision from `alembic current`
3. Save file

---

### Step 1.2: Check Database Connection

**Action**:
```bash
# Verify DATABASE_URL is set
echo $env:DATABASE_URL

# Should output: postgresql+asyncpg://user:pass@host:port/dbname
```

**If Not Set**:
```bash
# Option A: Use docker-compose PostgreSQL
docker-compose up -d postgres

# Wait 10 seconds for startup
Start-Sleep -Seconds 10

# Set environment variable
$env:DATABASE_URL = "postgresql+asyncpg://trading:password@localhost:5432/trading_db"

# Option B: Use existing PostgreSQL
$env:DATABASE_URL = "postgresql+asyncpg://your_user:your_pass@localhost:5432/your_db"
```

---

### Step 1.3: Apply Idempotency Migration

**Action**:
```bash
# Apply the new migration (after updating revision ID)
alembic upgrade head

# Expected output:
# INFO  [alembic.runtime.migration] Running upgrade abc123 -> add_idempotency_constraints
# ✅ Added UNIQUE constraint: orders(account_id, client_order_id)
# ✅ Added UNIQUE constraint: order_events(broker_order_id, event_type, event_time)
# ✅ Added UNIQUE constraint: outbox_events(aggregate_id, event_type, created_at)
# ✅ Added index: orders(client_order_id)
```

**Verification**:
```bash
# Verify constraints exist
python -c "from sqlalchemy import create_engine, inspect; engine = create_engine(r'$env:DATABASE_URL'.replace('+asyncpg', '')); inspector = inspect(engine); constraints = inspector.get_unique_constraints('orders'); print('✅ Constraints:', [c['name'] for c in constraints])"

# Expected: ['uq_orders_account_client_order_id']
```

---

## 📋 PHASE 2: New Test Files Validation (20 minutes)

### Step 2.1: Test Alembic Head Validation ✅

**Purpose**: Ensure tests fail if migrations not applied

**Action**:
```bash
# Should PASS (migrations are current)
pytest tests/test_alembic_head.py -v

# Expected output:
# tests/test_alembic_head.py::test_database_at_alembic_head PASSED
# tests/test_alembic_head.py::test_no_pending_model_changes PASSED
```

**Negative Test** (should FAIL):
```bash
# Rollback one migration
alembic downgrade -1

# Should FAIL with clear error
pytest tests/test_alembic_head.py::test_database_at_alembic_head -v

# Expected error:
# AssertionError: Database is NOT at alembic head!
# Current: abc123def456
# Head: add_idempotency_constraints
# 
# Fix: Run 'alembic upgrade head' to apply pending migrations

# Restore migration
alembic upgrade head
```

✅ **PASS CRITERIA**: Test fails when migrations not current

---

### Step 2.2: Test Idempotency Constraints ✅

**Purpose**: Validate database prevents duplicate orders

**Action**:
```bash
# Should PASS (constraints enforce idempotency)
pytest tests/test_idempotency.py -v -s

# Expected output:
# tests/test_idempotency.py::test_duplicate_idempotency_key_returns_same_order PASSED
# tests/test_idempotency.py::test_duplicate_client_order_id_rejected PASSED
# tests/test_idempotency.py::test_different_orders_get_different_ids PASSED
```

**What This Tests**:
1. Duplicate `Idempotency-Key` returns cached order (409 or 200)
2. Duplicate `client_order_id` blocked by database constraint
3. Different orders get different IDs (sanity check)

✅ **PASS CRITERIA**: All 3 tests pass

---

## 📋 PHASE 3: Modified Files Validation (30 minutes)

### Step 3.1: Test PostgreSQL Requirement ✅

**Purpose**: Verify tests fail without PostgreSQL

**File**: `backend/database.py:174`, `scripts/testing/test_layers_1_to_4_consolidated.py:493`

**Action**:
```bash
# Test 1: Missing DATABASE_URL (should FAIL)
$old_url = $env:DATABASE_URL
$env:DATABASE_URL = $null

python -c "from backend.database import DatabaseConfig; DatabaseConfig()"

# Expected error:
# DatabaseError: DATABASE_URL environment variable not set
# 
# Setup instructions:
# 1. Start PostgreSQL: docker-compose up -d postgres
# 2. Set: export DATABASE_URL=postgresql+asyncpg://...

# Restore
$env:DATABASE_URL = $old_url
```

```bash
# Test 2: SQLite URL (should FAIL)
$env:DATABASE_URL = "sqlite:///test.db"

python -c "from backend.database import DatabaseConfig; DatabaseConfig()"

# Expected error:
# DatabaseError: DATABASE_URL must use PostgreSQL (postgresql:// or postgresql+asyncpg://)
# Found: sqlite:///test.db
# 
# PostgreSQL is required for:
# - Connection pooling
# - Row-level locking
# - JSONB columns

# Restore
$env:DATABASE_URL = $old_url
```

✅ **PASS CRITERIA**: Both scenarios fail with clear errors

---

### Step 3.2: Test Burn-In Business Flow Enforcement ✅

**Purpose**: Verify burn-in fails with 0 orders/signals

**File**: `scripts/testing/burn_in_framework.py:448,463`

**Action** (simulation test):
```bash
# This requires a mock K6 results file with 0 business flow
# Create test scenario

# Expected behavior on line 448:
# if not route_metrics:
#     raise ValueError("Burn-in session collected 0 per-route metrics...")

# Expected behavior on line 463:
# if orders_processed == 0 and signals_processed == 0 and risk_decisions == 0:
#     raise ValueError("Burn-in session processed ZERO business transactions...")
```

**Manual Verification**:
```bash
# Check the code has strict validation
Select-String -Path scripts/testing/burn_in_framework.py -Pattern "raise ValueError" -Context 0,3

# Should show both ValueError raises (not warnings)
```

✅ **PASS CRITERIA**: Code raises ValueError, not warning

---

### Step 3.3: Test CI Bypass Blocks ✅

**Purpose**: Verify staging/production blocks -SkipTests/-Fast

**File**: `scripts/ci/quality_gates.ps1:126-164`

**Action**:
```bash
# Test 1: Block -SkipTests in ALL CI environments
$env:GITHUB_ACTIONS = "true"
$env:GITHUB_REF = "refs/heads/main"

pwsh scripts/ci/quality_gates.ps1 -SkipTests

# Expected output:
# ❌ GATE VIOLATION: Cannot use -SkipTests in CI environment
# CI Environment: ci-production
# 
# -SkipTests is NEVER allowed in CI (dev/staging/production)
# Exit code: 2
```

```bash
# Test 2: Block -Fast in staging
$env:GITHUB_REF = "refs/heads/staging"

pwsh scripts/ci/quality_gates.ps1 -Fast

# Expected output:
# ❌ GATE VIOLATION: Cannot use -Fast in staging/production
# CI Environment: ci-staging
# 
# -Fast is only allowed in:
# - Local development (no GITHUB_ACTIONS)
# - ci-dev branch
# Exit code: 2
```

```bash
# Test 3: Allow -Fast in dev
$env:GITHUB_REF = "refs/heads/dev"

pwsh scripts/ci/quality_gates.ps1 -Fast

# Expected: Should proceed (no error)
```

```bash
# Cleanup
Remove-Item Env:\GITHUB_ACTIONS
Remove-Item Env:\GITHUB_REF
```

✅ **PASS CRITERIA**: Staging/prod block both flags, dev allows -Fast only

---

### Step 3.4: Test Security Waivers Requirement ✅

**Purpose**: Verify HIGH findings require waivers

**File**: `scripts/ci/quality_gates.ps1:439`, `security/waivers.yml`

**Action**:
```bash
# Test 1: Check if waivers.yml exists
Test-Path security/waivers.yml

# Expected: True (file was created)
```

```bash
# Test 2: Run quality gates and check security validation
pwsh scripts/ci/quality_gates.ps1 -Environment staging

# Should check for security/waivers.yml
# If HIGH findings exist, should validate waivers file
```

**Manual Review**:
```bash
# View waivers template
cat security/waivers.yml

# Should contain:
# - bandit: section
# - grype: section
# - issue_id, severity, reason, owner, expiry, ticket fields
```

✅ **PASS CRITERIA**: Waivers file exists with proper structure

---

### Step 3.5: Test Outbox Verification (Real DB Query) ✅

**Purpose**: Verify outbox test queries database

**File**: `tests/test_order_lifecycle.py:135`

**Action**:
```bash
# Run order lifecycle test
pytest tests/test_order_lifecycle.py -v -s

# Expected: Test queries outbox_events table
# Should see database activity (not just "return True")
```

**Manual Code Review**:
```bash
# Check the fix is in place
Select-String -Path tests/test_order_lifecycle.py -Pattern "return True  # Placeholder" 

# Should return NO MATCHES (placeholder removed)

# Check real implementation exists
Select-String -Path tests/test_order_lifecycle.py -Pattern "get_session|OutboxEvent"

# Should find imports and database query
```

✅ **PASS CRITERIA**: No "return True" placeholder, real DB query present

---

### Step 3.6: Test Tracemalloc Memory Monitoring ✅

**Purpose**: Verify tracemalloc captures Python heap allocations

**File**: `backend/monitoring/memory_monitor.py:146`

**Action**:
```bash
# Quick test
python -c "
from backend.monitoring.memory_monitor import MemoryMonitor
import time

monitor = MemoryMonitor(target_pid=None, output_dir='test_results')
monitor.start()
time.sleep(2)
monitor.stop()

print('✅ Memory monitor test complete')
"

# Check output has tracemalloc fields
cat test_results/memory_monitor_*.jsonl | Select-String "tracemalloc"

# Should contain: python_tracemalloc_mb, python_tracemalloc_peak_mb
```

✅ **PASS CRITERIA**: Snapshots include tracemalloc data

---

## 📋 PHASE 4: Integration Tests (45 minutes)

### Step 4.1: Full Test Suite with PostgreSQL ✅

**Purpose**: Validate all tests pass with real PostgreSQL

**Action**:
```bash
# Ensure PostgreSQL running
docker-compose up -d postgres
Start-Sleep -Seconds 10

# Run full test suite
pytest tests/ -v --tb=short --maxfail=5

# Expected: All tests pass
# Monitor for:
# - No SQLite fallbacks
# - PostgreSQL connections used
# - Alembic head validated
# - Idempotency constraints active
```

**Time**: ~10-15 minutes

✅ **PASS CRITERIA**: All tests pass, no SQLite warnings

---

### Step 4.2: Run Pre-Run Consolidated Tests ✅

**Purpose**: Validate 4-layer testing (imports, functional, paper, live)

**Action**:
```bash
# Run consolidated test suite
pytest scripts/testing/test_layers_1_to_4_consolidated.py -v -s

# Expected output:
# Layer 1: Import & Configuration Tests - PASS
# Layer 2: Functional Tests (PostgreSQL) - PASS (requires DATABASE_URL)
# Layer 3: Paper Trading Tests - PASS (requires ALPACA_API_KEY)
# Layer 4: Live Server Tests - PASS (starts server)

# Monitor for:
# - PostgreSQL validation (should FAIL if not set)
# - Alpaca API calls (should take 50-250ms, not 5ms)
# - No SQLite fallback messages
```

**Time**: ~3-5 minutes

✅ **PASS CRITERIA**: All 4 layers pass, Alpaca test shows real API timing

---

### Step 4.3: Test Alpaca Real API Calls ✅

**Purpose**: Verify Alpaca tests use real TradingClient

**Action**:
```bash
# Ensure alpaca-py installed (already verified: v0.42.2)
python -c "import alpaca.trading; print('✅ alpaca-py available')"

# Run Alpaca test with timing
pytest scripts/testing/test_layers_1_to_4_consolidated.py::PreRunTestSuite::test_layer3_paper_trading -v -s --durations=10

# Expected timing:
# - Real API call: 50-500ms
# - Fallback env check: 5-12ms

# Look for output:
# ✅ Alpaca credentials: [PASS] PASS
#    -> Account Status: ACTIVE, Buying Power: $100000.00
#    Duration: 250ms (indicates real API call)
```

**If Fast** (<20ms):
```bash
# Check if SDK failing to import
python -c "
try:
    from alpaca.trading.client import TradingClient
    print('✅ TradingClient available')
except Exception as e:
    print(f'❌ SDK import failed: {e}')
"

# If fails: pip install alpaca-py
```

✅ **PASS CRITERIA**: Alpaca test takes >50ms (real API call)

---

### Step 4.4: Simulate Burn-In Session ✅

**Purpose**: Validate burn-in enforces business flow

**Action**:
```bash
# Start server in background
python main.py &
$server_pid = $LASTEXITCODE

# Wait for startup
Start-Sleep -Seconds 10

# Run short burn-in (5 minutes)
python scripts/testing/burn_in_framework.py --duration 5 --output burn_in_test_results

# Expected:
# - Collects K6 metrics (route_metrics NOT empty)
# - Processes orders/signals (NOT zero)
# - Memory snapshots include tracemalloc
# - Fails if any counter is 0

# Cleanup
Stop-Process -Id $server_pid
```

**Success Indicators**:
- ✅ `route_metrics` has entries
- ✅ `orders_processed > 0` OR `signals_processed > 0` OR `risk_decisions > 0`
- ✅ No "0.0ms p95" metrics

**Failure Indicators** (GOOD):
- ❌ Raises ValueError if all counters are 0
- ❌ Raises ValueError if route_metrics empty

✅ **PASS CRITERIA**: Burn-in completes with business metrics OR fails with clear error

---

## 📋 PHASE 5: Security & Documentation (20 minutes)

### Step 5.1: Document Security Waivers ⚠️ REQUIRED

**Purpose**: Track HIGH/CRITICAL security findings

**Action**:
```bash
# Run bandit security scan
bandit -r backend/ -f json -o security/bandit_results.json

# Review HIGH severity findings
cat security/bandit_results.json | jq '.results[] | select(.issue_severity=="HIGH")'

# For each HIGH finding, add to security/waivers.yml:
```

**Example Entry**:
```yaml
bandit:
  - issue_id: B105
    severity: HIGH
    reason: "False positive - hardcoded password is test fixture"
    owner: "@security-team"
    expiry: "2025-12-01"
    ticket: "SEC-1234"
    approved_by: "vp-engineering@company.com"
```

**Get VP Engineering approval** for all HIGH waivers

✅ **PASS CRITERIA**: All HIGH findings documented with expiry dates

---

### Step 5.2: Update Skip Statement Tickets ⚠️ REQUIRED

**Purpose**: Track skipped tests with expiry dates

**Files**:
- `tests/test_route_registry.py:121`
- `tests/test_performance_slo.py:173,192`

**Action**:
```bash
# Find all skip statements
Select-String -Path tests/ -Pattern "pytest.skip" -Recurse

# For each skip, verify has:
# 1. Ticket ID (TEST-001, TEST-002, etc.)
# 2. Expiry date (Remove by: YYYY-MM-DD)
# 3. Owner (@team-name)
# 4. Reason (business justification)
```

**Example** (already added):
```python
pytest.skip(
    "Authentication not available\n"
    "Ticket: TEST-001\n"
    "Remove by: 2025-11-01\n"
    "Owner: @auth-team\n"
    "Reason: Auth endpoint not configured in test environment"
)
```

**Update ticket IDs** to real JIRA/GitHub issue numbers

✅ **PASS CRITERIA**: All skips have tickets with expiry <30 days

---

### Step 5.3: Update CI/CD Documentation

**Purpose**: Document new gates and requirements

**Action**:
```bash
# Update README.md with new requirements
# Add section: "Quality Gates & False Positive Prevention"
```

**Required Content**:
```markdown
## Quality Gates

### Database Requirements
- PostgreSQL required (no SQLite in tests)
- `DATABASE_URL` must be set
- Alembic migrations must be current

### CI/CD Restrictions
- `-SkipTests` BLOCKED in ALL CI environments
- `-Fast` BLOCKED in staging/production
- Security waivers REQUIRED for HIGH findings

### Burn-In Requirements
- Staging/production require burn-in sessions
- Must process >0 orders/signals/risk decisions
- Must collect per-route K6 metrics
- SLO monitoring required

### Idempotency
- Database constraints enforce deduplication
- Idempotency-Key header required for orders
- client_order_id must be unique per account
```

✅ **PASS CRITERIA**: Documentation updated

---

## 📋 PHASE 6: Staging Deployment (30 minutes)

### Step 6.1: Pre-Deployment Checklist

**Before deploying to staging**:

- [ ] ✅ All tests pass locally
- [ ] ✅ Alembic migration applied and tested
- [ ] ✅ Security waivers documented
- [ ] ✅ Skip statement tickets updated
- [ ] ✅ DATABASE_URL set in staging environment
- [ ] ✅ ALPACA_API_KEY set in staging environment
- [ ] ✅ alpaca-py installed in staging
- [ ] ✅ CI/CD pipeline updated to block bypasses
- [ ] ✅ Burn-in framework tested locally

---

### Step 6.2: Deploy to Staging

**Action**:
```bash
# Merge to staging branch
git checkout staging
git merge fix/order-flow-gate

# Push to trigger staging deployment
git push origin staging

# Monitor CI/CD pipeline
# Expected:
# 1. Quality gates run WITHOUT -SkipTests/-Fast (blocked)
# 2. Alembic head validation runs first
# 3. Full test suite runs with PostgreSQL
# 4. Security scan checks waivers.yml
# 5. Burn-in session runs (enforces business flow)
```

---

### Step 6.3: Monitor Staging Deployment

**Watch for**:

1. **Quality Gates**: Should enforce all new validations
2. **Burn-In Session**: Should collect business metrics
3. **Promotion Report**: Should show real SLI data (not "0%")
4. **Memory Monitoring**: Should include tracemalloc data
5. **Idempotency**: Database constraints active

**Success Indicators**:
- ✅ No "p95: 0.0ms" false metrics
- ✅ No "availability: 0%" false greens
- ✅ Burn-in shows orders_processed > 0
- ✅ route_metrics not empty
- ✅ CI blocks -SkipTests flag attempts

---

## 📊 VALIDATION SUMMARY CHECKLIST

### ✅ Phase 1: Pre-Validation (15 min)
- [ ] Update alembic migration revision ID
- [ ] Verify DATABASE_URL set to PostgreSQL
- [ ] Apply idempotency migration
- [ ] Verify constraints exist in database

### ✅ Phase 2: New Tests (20 min)
- [ ] test_alembic_head.py passes
- [ ] test_alembic_head.py fails when migrations behind
- [ ] test_idempotency.py passes (all 3 tests)

### ✅ Phase 3: Modified Files (30 min)
- [ ] PostgreSQL requirement enforced
- [ ] SQLite URL rejected
- [ ] Burn-in raises ValueError on 0 business flow
- [ ] CI blocks -SkipTests in ALL environments
- [ ] CI blocks -Fast in staging/production
- [ ] Security waivers.yml exists
- [ ] Outbox verification queries database
- [ ] Tracemalloc monitoring active

### ✅ Phase 4: Integration (45 min)
- [ ] Full test suite passes
- [ ] Pre-run tests validate PostgreSQL
- [ ] Alpaca tests use real API (>50ms)
- [ ] Burn-in completes with business metrics

### ✅ Phase 5: Security (20 min)
- [ ] Security waivers documented
- [ ] VP approval obtained
- [ ] Skip tickets updated
- [ ] Documentation updated

### ✅ Phase 6: Staging (30 min)
- [ ] Deploy to staging
- [ ] Monitor quality gates
- [ ] Verify burn-in enforcement
- [ ] Confirm no false positives

---

## 🎯 SUCCESS CRITERIA

**ALL of the following must be true**:

1. ✅ All 20 fixes validated working
2. ✅ Tests FAIL on bad paths (PostgreSQL required, 0 business flow, etc.)
3. ✅ Tests PASS on good paths (real validation, business metrics collected)
4. ✅ CI blocks test bypasses in staging/production
5. ✅ Database constraints prevent duplicate orders
6. ✅ Security waivers tracked with expiry
7. ✅ Staging deployment succeeds with new gates
8. ✅ No "0.0ms p95" or "0% availability" false metrics

---

## ⏭️ WHAT'S NEXT

After completing all validation phases:

1. **Production Deployment**: Merge staging → main with confidence
2. **Monitor Production**: Watch for real SLI data (no false zeros)
3. **P2 Items**: Address deferred medium-priority items:
   - Market hours override for staging (requires backend API)
   - Replace remaining mocks with real APIs
   - Enhance route metrics validation

4. **Continuous Improvement**:
   - Review security waivers monthly (check expiry)
   - Update skip statement tickets (resolve or extend)
   - Monitor burn-in sessions (ensure business flow coverage)
   - Track false-positive rate (should be near 0%)

---

## 🚨 KNOWN ISSUES / BLOCKERS

**None currently** - All critical path items are implemented and testable.

**If You Encounter Issues**:
1. **DATABASE_URL errors**: Ensure PostgreSQL running and URL correct
2. **Alembic errors**: Update down_revision in migration file
3. **Alpaca fast tests**: Verify alpaca-py installed (v0.42.2)
4. **Burn-in 0 metrics**: Check K6 script tagging and server health
5. **Security gate errors**: Document HIGH findings in waivers.yml

---

**Report Generated**: October 2, 2025  
**Validation Status**: 🚧 **READY TO BEGIN**  
**Estimated Time**: 2-3 hours  
**Expected Outcome**: ✅ **100% VALIDATION COMPLETE**
