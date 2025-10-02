# STAGING QUICK START

**Time**: 5 minutes to get started  
**Prerequisites**: PR merged to staging branch

---

## 🚀 QUICK START (5 min)

### Step 1: Create Pull Request
```bash
# Open browser to:
https://github.com/Lesram/intraday/pull/new/fix/order-flow-gate

# Select:
# Base: staging
# Compare: fix/order-flow-gate

# Use PR template from STAGING_DEPLOYMENT_PLAN.md
```

### Step 2: Wait for CI (15-20 min)
- ✅ Watch GitHub Actions pipeline
- ✅ Verify all tests pass
- ✅ Check security scans pass
- ✅ Merge when green

### Step 3: Auto-Deploy to Staging
- Staging environment auto-deploys
- Wait 2-3 minutes for rollout

### Step 4: Run Validation Script
```powershell
# Run automated validation
.\STAGING_MONITORING_SCRIPT.ps1 -StagingUrl "http://your-staging-server:8000"

# OR with database validation
$env:STAGING_DATABASE_URL = "postgresql://user:pass@staging-db:5432/trading"
.\STAGING_MONITORING_SCRIPT.ps1 -StagingUrl "http://your-staging-server:8000"

# OR skip burn-in for faster check
.\STAGING_MONITORING_SCRIPT.ps1 -StagingUrl "http://your-staging-server:8000" -SkipBurnIn
```

**Expected Output**:
```
🎯 STAGING DEPLOYMENT VALIDATION
============================================================
Start Time: 2025-10-02 13:30:00
Staging URL: http://your-staging-server:8000
Duration: 30 minutes
============================================================

[1/6] Health Endpoint Check...
✅ Health Endpoint
   Server is healthy

[2/6] Database Constraints Check...
✅ Database Constraints
   All 3 UNIQUE constraints exist

[3/6] Code Verification Check...
✅ No Placeholder Code
   No placeholder comments found in test_order_lifecycle.py
✅ Burn-In Strict Validation
   Found 6 ValueError validations

[4/6] CI Bypass Block Check...
✅ CI Bypass Blocks
   -Fast flag correctly blocked in staging

[5/6] Burn-In Session Check...
✅ Burn-In Session
   Business flow validated

[6/6] False Positive Metrics Check...
✅ False Positive Metrics
   No false positive metrics detected

============================================================
VALIDATION SUMMARY
============================================================

Results:
  ✅ Passed:  6
  ❌ Failed:  0
  ⚠️  Warnings: 0

Success Rate: 100.0%

🎉 ALL CRITICAL CHECKS PASSED!
   Staging deployment is validated and ready.
```

---

## 📊 MANUAL CHECKS (if script unavailable)

### Check 1: Health Endpoint
```powershell
curl http://your-staging-server:8000/health
# Expected: {"status": "healthy", "database": "connected"}
```

### Check 2: Database Constraints
```bash
psql $STAGING_DATABASE_URL -c "\d orders"
# Look for: uq_orders_account_client_order_id constraint
```

### Check 3: Burn-In Validation
```bash
# Look at staging logs for burn-in results
kubectl logs -n staging deployment/trading-platform --tail=100 | grep "Orders processed"
# Expected: "Orders processed: 42" (not 0)
```

---

## ✅ SUCCESS CRITERIA

All checks must pass:
- [x] CI pipeline green (all tests pass)
- [x] Health endpoint responds
- [x] Database constraints exist
- [x] No placeholder code
- [x] CI bypass blocks work
- [x] Burn-in shows >0 orders
- [x] No false positive metrics

---

## 🚨 IF CHECKS FAIL

**Option 1: Quick Fix**
```bash
# Fix issue locally
git checkout fix/order-flow-gate
# Make fix
git commit -m "fix: address staging validation issue"
git push origin fix/order-flow-gate

# Re-run CI
# Re-validate staging
```

**Option 2: Rollback**
```bash
# Revert staging
git checkout staging
git revert HEAD
git push origin staging

# OR rollback deployment
kubectl rollout undo deployment/trading-platform -n staging
```

---

## ⏭️ NEXT: PRODUCTION DEPLOYMENT

After staging validates successfully:

1. **Soak Test** (2-4 hours): Monitor staging
2. **Create Production PR**: staging → main
3. **Deploy to Production**: During maintenance window
4. **Monitor Production**: Same validation checks

---

## 📞 HELP

**Documentation**:
- Full plan: `STAGING_DEPLOYMENT_PLAN.md`
- Validation details: `COMPLETE_VALIDATION_RESULTS.md`
- Immediate tests: `IMMEDIATE_VALIDATION.md`

**Issues**:
- CI failures: Check GitHub Actions logs
- Health check fails: Check staging logs
- Database issues: Verify connection string
- Burn-in fails: Check K6 installation

**Escalation**:
- P0/P1: Page on-call engineer
- P2/P3: Create issue in GitHub
