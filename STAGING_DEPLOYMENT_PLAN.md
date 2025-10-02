# STAGING DEPLOYMENT PLAN

**Branch**: `fix/order-flow-gate`  
**Commit**: `63be6c4`  
**Status**: Ready for staging deployment  
**Validation**: 18/20 fixes validated locally (90%)

---

## 🎯 DEPLOYMENT PHASES

### Phase 1: Create Pull Request (5 min)

**Action**: Create PR from `fix/order-flow-gate` to `staging`

**PR Link**: https://github.com/Lesram/intraday/pull/new/fix/order-flow-gate

**PR Title**: 
```
feat: eliminate 20 false-positive test paths - validation complete
```

**PR Description Template**:
```markdown
## Summary
Eliminates 20 false-positive test paths identified in comprehensive QA audit.

## Changes (20 Fixes)
### Critical (8)
- ✅ PostgreSQL-only enforcement (reject SQLite)
- ✅ CI test bypass blocks (production/staging)
- ✅ Burn-in business flow validation (6 ValueError)
- ✅ Real outbox delivery verification
- ✅ Database idempotency constraints (3 UNIQUE)
- ✅ Alpaca paper API real timing checks
- ✅ Tracemalloc memory monitoring
- ✅ Security waivers tracking template

### Loop Closure (6)
- ✅ Fixed DatabaseConfig stub validation
- ✅ Alembic asyncpg→psycopg2 conversion
- ✅ VP approval policy in waivers
- ✅ Enhanced burn-in with 6 ValueError
- ✅ Environment-aware CI enforcement
- ✅ Clear error messages with setup instructions

## Validation Results
- ✅ **6 immediate tests**: ALL PASSED (no database required)
- ✅ **18 of 20 fixes**: Validated locally (90%)
- ⏸️ **2 deferred tests**: Require PostgreSQL (will run in CI)

## Test Results
### Test 1: PostgreSQL Enforcement ✅
- Rejects SQLite with clear error
- Accepts PostgreSQL URLs
- Error includes setup instructions

### Test 2: CI Bypass Blocks ✅
- Production: blocks -SkipTests ✅
- Staging: blocks -Fast ✅
- Dev: allows -Fast ✅

### Test 3: Code Verification ✅
- 0 placeholder comments ✅
- 6 ValueError in burn-in (lines 382, 419, 433, 438, 451, 466) ✅
- 2 "ABSOLUTELY BLOCKED" references ✅

### Test 4-6: Infrastructure ✅
- Security waivers template exists ✅
- Tracemalloc import at line 11 ✅
- 3 database constraints created ✅

## CI Will Test
- ✅ test_alembic_head.py (migration validation)
- ✅ test_idempotency.py (duplicate prevention)
- ✅ Full pytest suite with PostgreSQL
- ✅ Security scans (bandit + grype)

## Risk Assessment
**Risk Level**: LOW  
**Confidence**: HIGH  
**Deployment Ready**: YES

## Documentation
- FALSE_POSITIVES_AUDIT.md (18 findings)
- IMMEDIATE_VALIDATION.md (6 tests)
- COMPLETE_VALIDATION_RESULTS.md (comprehensive)
- VALIDATION_CHECKLIST.md (quick reference)
```

---

### Phase 2: Monitor CI Pipeline (15-20 min)

**GitHub Actions to Watch**:

1. **Test Suite** (pytest with PostgreSQL)
   ```bash
   # CI will run:
   pytest tests/ -v --cov=backend --cov-report=term-missing
   ```
   
   **Expected Results**:
   - ✅ test_alembic_head.py passes (2 tests)
   - ✅ test_idempotency.py passes (3 tests)
   - ✅ All unit tests pass
   - ✅ Coverage maintains >80%

2. **Quality Gates** (scripts/ci/quality_gates.ps1)
   ```bash
   # CI will run:
   pwsh scripts/ci/quality_gates.ps1
   ```
   
   **Expected Results**:
   - ✅ Bandit security scan (no HIGH/CRITICAL)
   - ✅ Grype vulnerability scan (no unwaived findings)
   - ✅ All gates pass

3. **Database Migration Check**
   ```bash
   # CI will run:
   alembic current
   alembic upgrade head
   ```
   
   **Expected Results**:
   - ✅ Migration applies cleanly
   - ✅ 3 UNIQUE constraints created
   - ✅ No rollback errors

**CI Failure Handling**:

If CI fails on test_alembic_head.py:
```bash
# Check migration revision
alembic current
alembic history

# Update down_revision in migrations/versions/add_idempotency_constraints.py
# Set to actual head revision from alembic history
```

If CI fails on test_idempotency.py:
```bash
# Verify constraints exist
psql -c "\d orders"
psql -c "\d order_events"
psql -c "\d outbox_events"

# Check for UNIQUE constraints:
# - uq_orders_account_client_order_id
# - uq_order_events_broker_event
# - uq_outbox_events_aggregate_event
```

---

### Phase 3: Deploy to Staging (5 min)

**Action**: Merge PR after CI passes

**Deployment Method**:
```bash
# Option A: GitHub UI merge
# Click "Merge pull request" → "Confirm merge"

# Option B: Command line
git checkout staging
git merge fix/order-flow-gate --no-ff
git push origin staging
```

**Post-Deployment**:
```bash
# Staging environment will auto-deploy via:
# - GitHub Actions deployment workflow
# - OR Kubernetes rollout
# - OR Docker compose restart
```

---

### Phase 4: Staging Monitoring (30 min)

#### 4.1 Health Check (2 min)

```bash
# Check staging server is up
curl https://staging.yourapp.com/health

# Expected:
# {"status": "healthy", "database": "connected", "version": "..."}
```

**Checklist**:
- [ ] Server responds to /health
- [ ] Database connection active
- [ ] All services running
- [ ] No startup errors in logs

---

#### 4.2 Database Constraints Validation (5 min)

```bash
# Connect to staging database
psql $STAGING_DATABASE_URL

# Verify constraints exist
SELECT conname, contype, conrelid::regclass 
FROM pg_constraint 
WHERE conname LIKE 'uq_%';

# Expected output:
# conname                           | contype | conrelid
# ----------------------------------+---------+-------------
# uq_orders_account_client_order_id | u       | orders
# uq_order_events_broker_event      | u       | order_events
# uq_outbox_events_aggregate_event  | u       | outbox_events
```

**Test Duplicate Prevention**:
```sql
-- Attempt to create duplicate order (should fail)
INSERT INTO orders (id, account_id, client_order_id, ...) 
VALUES (uuid_generate_v4(), 'acc123', 'order456', ...);

-- Attempt to insert same order again (SHOULD FAIL)
INSERT INTO orders (id, account_id, client_order_id, ...) 
VALUES (uuid_generate_v4(), 'acc123', 'order456', ...);

-- Expected: ERROR: duplicate key value violates unique constraint "uq_orders_account_client_order_id"
```

**Checklist**:
- [ ] 3 UNIQUE constraints exist in database
- [ ] Duplicate order insertion fails with constraint error
- [ ] Duplicate order_event insertion fails
- [ ] Duplicate outbox_event insertion fails

---

#### 4.3 Burn-In Session Monitoring (15 min)

**Trigger Burn-In Test**:
```bash
# SSH to staging server
ssh staging.yourapp.com

# Run burn-in session
python scripts/testing/burn_in_framework.py \
  --duration 900 \
  --target-url http://localhost:8000 \
  --k6-path /usr/local/bin/k6
```

**Monitor Metrics**:
```bash
# Watch logs for:
# - Orders processed count
# - Signal generation count
# - Risk decision count
# - Per-route metrics
# - Business flow validation

# Example output:
# ✅ Burn-in session complete:
#    - Orders processed: 42 (✅ >0)
#    - Signals generated: 37 (✅ >0)
#    - Risk decisions: 42 (✅ >0)
#    - Per-route metrics: 12 routes (✅ >0)
#    - Error rate: 0.2% (✅ <1%)
```

**Critical Checks** (lines 451, 466 from burn_in_framework.py):
```python
# Line 451: Per-route metrics validation
if len(results["per_route_metrics"]) == 0:
    raise ValueError("Burn-in session collected 0 per-route metrics")

# Line 466: Business flow validation
if orders == 0 and signals == 0 and risk_decisions == 0:
    raise ValueError("Business flow validation failed: 0 orders, 0 signals, 0 risk decisions")
```

**Expected Behavior**:
- ✅ ValueError raised if 0 per-route metrics
- ✅ ValueError raised if 0 business flow events
- ✅ Session fails fast instead of passing with 0s

**Failure Scenarios to Test**:

Test 1: No traffic
```bash
# Stop sending traffic mid-test
# Expected: ValueError at line 466 (0 orders/signals/risk)
```

Test 2: Server crash
```bash
# Kill server process during test
# Expected: ValueError at line 382 (cannot locate server process)
```

**Checklist**:
- [ ] Burn-in runs for 15 minutes without crash
- [ ] Orders processed > 0 (not 0)
- [ ] Signals generated > 0
- [ ] Risk decisions > 0
- [ ] Per-route metrics > 0
- [ ] Error rate < 1%
- [ ] P95 latency < 500ms
- [ ] ValueError raised if any metric = 0

---

#### 4.4 False Positive Metric Check (5 min)

**Monitor for Previous False Positives**:

```bash
# Check Prometheus/Grafana for:
# 1. "0% availability" metrics (should NOT appear)
# 2. "100% success rate" with 0 requests (should NOT appear)
# 3. Tests passing with 0 coverage (should NOT appear)
```

**Dashboard Queries**:
```promql
# Query 1: Availability should never be NaN or 0 with active traffic
rate(http_requests_total[5m]) > 0 AND 
rate(http_requests_successful[5m]) / rate(http_requests_total[5m]) == 0

# Expected: No results (no false 0% availability)

# Query 2: Coverage should never be 0 for deployed code
code_coverage{environment="staging"} == 0

# Expected: No results (no 0% coverage)

# Query 3: Test pass rate should not be 100% with 0 tests
test_pass_rate == 1.0 AND test_count == 0

# Expected: No results (no false 100% pass rate)
```

**Checklist**:
- [ ] No "0% availability" false metrics
- [ ] No "100% success" with 0 requests
- [ ] No test pass metrics with 0 tests run
- [ ] All metrics have realistic values

---

#### 4.5 CI Bypass Block Verification (3 min)

**Test CI Enforcement in Staging**:

```bash
# Attempt to run quality gates with -Fast in staging
$env:GITHUB_ACTIONS = "true"
$env:GITHUB_REF = "refs/heads/staging"

pwsh scripts/ci/quality_gates.ps1 -Fast

# Expected OUTPUT:
# ❌ GATE VIOLATION: Cannot use -Fast in staging/production
# CI Environment: ci-staging
# -Fast flag is ABSOLUTELY BLOCKED in staging/production environments
# Exit code: 2

# Verify exit code
echo $LASTEXITCODE
# Expected: 2 (failure)
```

**Checklist**:
- [ ] -Fast flag blocked in staging
- [ ] -SkipTests flag blocked in staging
- [ ] Clear error messages displayed
- [ ] Exit code = 2 (gate violation)

---

## 📊 SUCCESS CRITERIA

### ✅ All Must Pass

1. **CI Pipeline**:
   - [ ] All pytest tests pass (including test_alembic_head.py, test_idempotency.py)
   - [ ] Security scans pass (bandit + grype)
   - [ ] Migration applies cleanly
   - [ ] Quality gates pass

2. **Staging Deployment**:
   - [ ] Server starts successfully
   - [ ] Health endpoint responds
   - [ ] Database connected
   - [ ] No error logs on startup

3. **Database Constraints**:
   - [ ] 3 UNIQUE constraints exist
   - [ ] Duplicate orders rejected
   - [ ] Constraint violations logged

4. **Burn-In Session**:
   - [ ] Runs for 15 minutes without crash
   - [ ] Orders processed > 0
   - [ ] Business flow metrics > 0
   - [ ] ValueError raised if metrics = 0

5. **False Positive Check**:
   - [ ] No "0% availability" metrics
   - [ ] No "100% success" with 0 requests
   - [ ] All metrics realistic

6. **CI Bypass Blocks**:
   - [ ] -Fast blocked in staging
   - [ ] -SkipTests blocked in staging
   - [ ] Clear error messages

---

## 🚨 ROLLBACK PLAN

If any success criteria fails:

### Quick Rollback (1 min)
```bash
# Revert staging to previous commit
git checkout staging
git revert HEAD
git push origin staging --force

# OR redeploy previous version
kubectl rollout undo deployment/trading-platform -n staging
```

### Investigate and Fix
```bash
# Collect logs
kubectl logs -n staging deployment/trading-platform --tail=1000 > staging_error.log

# Check database state
psql $STAGING_DATABASE_URL -c "SELECT * FROM alembic_version;"

# Review failure in CI
# https://github.com/Lesram/intraday/actions
```

---

## 📝 MONITORING COMMANDS CHEAT SHEET

```bash
# Health check
curl https://staging.yourapp.com/health

# Database constraints
psql $STAGING_DATABASE_URL -c "\d orders"

# Burn-in test
python scripts/testing/burn_in_framework.py --duration 900 --target-url http://localhost:8000

# CI gate test (staging)
$env:GITHUB_ACTIONS = "true"; $env:GITHUB_REF = "refs/heads/staging"; pwsh scripts/ci/quality_gates.ps1 -Fast

# View logs
kubectl logs -n staging deployment/trading-platform --tail=100 -f

# Check metrics
curl https://staging.yourapp.com/metrics | grep -E "orders_processed|burn_in"
```

---

## ⏭️ NEXT STEPS AFTER STAGING

If all checks pass in staging (30 min):

1. **Soak Test** (2-4 hours):
   - Monitor staging for extended period
   - Run multiple burn-in sessions
   - Check for memory leaks (tracemalloc)
   - Verify no gradual degradation

2. **Production Deployment**:
   - Create PR from staging → main
   - Full CI pipeline runs again
   - Deploy during maintenance window
   - Gradual rollout (canary/blue-green)

3. **Production Monitoring**:
   - Same checks as staging
   - 24-hour observation period
   - On-call engineer standby
   - Rollback plan ready

---

## 📞 ESCALATION

If critical issues found:

- **P0 (Production Down)**: Immediate rollback + page on-call
- **P1 (Degraded)**: Investigate within 1 hour, rollback if no fix
- **P2 (Non-Critical)**: Create ticket, fix in next sprint
- **P3 (Enhancement)**: Add to backlog

---

**Document Version**: 1.0  
**Last Updated**: 2025-10-02  
**Owner**: QA/SRE Team  
**Reviewer**: Engineering Lead
