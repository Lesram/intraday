# QUICK VALIDATION CHECKLIST

**Time**: 2-3 hours | **Status**: Ready to begin

---

## ⚡ QUICK START (5 minutes)

```powershell
# 1. Activate venv (DONE ✅)
.\venv\Scripts\Activate.ps1

# 2. Verify alpaca-py (DONE ✅ - v0.42.2)
python -c "import alpaca; print('✅ alpaca-py OK')"

# 3. Check DATABASE_URL
echo $env:DATABASE_URL
# If empty: $env:DATABASE_URL = "postgresql+asyncpg://user:pass@localhost:5432/trading_db"

# 4. Start PostgreSQL
docker-compose up -d postgres
Start-Sleep -Seconds 10
```

---

## 🔧 CRITICAL: Update Migration (SKIP FOR NOW - DATABASE NEEDED)

**⚠️ ISSUE**: Alembic requires a real PostgreSQL database connection.

**Current Situation**:
- DATABASE_URL is set to placeholder: `postgresql+asyncpg://user:pass@localhost:5432/trading_db`
- Need actual PostgreSQL running OR can skip migration for testing

**Option A: Skip Migration (Recommended for Now)**
```powershell
# The idempotency migration is optional for testing the other fixes
# You can validate all other fixes without applying the migration
# Migration is only needed for database-level duplicate prevention (defense-in-depth)

# Continue to validation steps below
```

**Option B: Set Up Real PostgreSQL** (if you want to test idempotency)
```powershell
# 1. Start PostgreSQL with docker-compose
docker-compose up -d postgres
Start-Sleep -Seconds 15

# 2. Set real DATABASE_URL (update with your credentials)
$env:DATABASE_URL = "postgresql+asyncpg://trading:SecurePass123!@localhost:5432/trading_db"

# 3. Get current head
alembic current
# Output example: abc123def456 (head) OR empty if no migrations

# 4. If you have migrations, update the file:
# File: migrations/versions/add_idempotency_constraints.py
# Line 18: Change down_revision = None to actual head
# Then: alembic upgrade head
```

**For This Validation**: Skip migration, test everything else ✅

---

## ✅ VALIDATION SEQUENCE (Most tests work WITHOUT database)

### 1. New Tests ⏸️ SKIP (Requires PostgreSQL)
```powershell
# These tests need a real database - skip for now
# pytest tests/test_alembic_head.py -v
# pytest tests/test_idempotency.py -v -s
```

### 2. PostgreSQL Enforcement ✅ (Works without DB!)
```powershell
# Test 1: Missing URL should FAIL
$old = $env:DATABASE_URL
$env:DATABASE_URL = $null
python -c "from backend.database import DatabaseConfig; DatabaseConfig()"
# Expected: DatabaseError with clear message

# Test 2: SQLite should FAIL  
$env:DATABASE_URL = "sqlite:///test.db"
python -c "from backend.database import DatabaseConfig; DatabaseConfig()"
# Expected: DatabaseError about PostgreSQL required

# Restore
$env:DATABASE_URL = $old
```

### 3. CI Bypass Blocks (5 min)
```powershell
# Block -SkipTests in CI
$env:GITHUB_ACTIONS = "true"
$env:GITHUB_REF = "refs/heads/main"
pwsh scripts/ci/quality_gates.ps1 -SkipTests
# Expected: Exit code 2, error message

# Block -Fast in staging
$env:GITHUB_REF = "refs/heads/staging"
pwsh scripts/ci/quality_gates.ps1 -Fast
# Expected: Exit code 2, error message

# Allow -Fast in dev
$env:GITHUB_REF = "refs/heads/dev"
pwsh scripts/ci/quality_gates.ps1 -Fast
# Expected: Proceeds

# Cleanup
Remove-Item Env:\GITHUB_ACTIONS
Remove-Item Env:\GITHUB_REF
```

### 4. Full Test Suite ⏸️ SKIP (Requires PostgreSQL)
```powershell
# Most tests need database - skip for now
# pytest tests/ -v --maxfail=5
```

### 5. Alpaca Real API ⏸️ SKIP (Requires Alpaca credentials)
```powershell
# Requires ALPACA_API_KEY and ALPACA_SECRET_KEY - skip for now
# pytest scripts/testing/test_layers_1_to_4_consolidated.py::PreRunTestSuite::test_layer3_paper_trading -v -s --durations=10
```

### 6. Security Waivers (10 min)
```powershell
# Run bandit
bandit -r backend/ -f json -o security/bandit_results.json

# Check HIGH findings
cat security/bandit_results.json | jq '.results[] | select(.issue_severity=="HIGH")'

# Document each in security/waivers.yml with:
# - issue_id, severity, reason, owner, expiry, ticket
```

### 7. Code Verification (5 min)
```powershell
# Verify no "return True" placeholders
Select-String -Path tests/test_order_lifecycle.py -Pattern "return True  # Placeholder"
# Expected: No matches

# Verify burn-in raises ValueError (not warning)
Select-String -Path scripts/testing/burn_in_framework.py -Pattern "raise ValueError" -Context 0,2
# Expected: 2 matches (line 448 and 463)

# Verify CI absolute blocks
Select-String -Path scripts/ci/quality_gates.ps1 -Pattern "NEVER allowed" -Context 0,2
# Expected: Match showing -SkipTests blocked
```

---

## 📊 PASS/FAIL CRITERIA

### ✅ MUST PASS
- [ ] test_alembic_head.py: 2/2 tests pass
- [ ] test_idempotency.py: 3/3 tests pass
- [ ] Full test suite: All pass
- [ ] Alpaca test: >50ms duration
- [ ] PostgreSQL required: Rejects SQLite/missing URL
- [ ] CI blocks: -SkipTests blocked in ALL CI
- [ ] CI blocks: -Fast blocked in staging/prod
- [ ] Security waivers: File exists with entries
- [ ] Code review: No placeholders found

### ❌ MUST FAIL (Good Failures)
- [ ] DatabaseConfig() with no DATABASE_URL
- [ ] DatabaseConfig() with SQLite URL
- [ ] quality_gates.ps1 -SkipTests in CI
- [ ] quality_gates.ps1 -Fast in staging
- [ ] test_alembic_head.py after `alembic downgrade -1`

---

## 🚨 IF SOMETHING FAILS

### "ModuleNotFoundError: alpaca"
```powershell
pip install alpaca-py
```

### "DATABASE_URL not set"
```powershell
docker-compose up -d postgres
$env:DATABASE_URL = "postgresql+asyncpg://trading:password@localhost:5432/trading_db"
```

### "Migration already exists"
```powershell
# Check current revision
alembic current
# Update line 18 in migrations/versions/add_idempotency_constraints.py
```

### "Constraint already exists" (during migration)
```
# This is OK - constraints may already exist
# Migration has try/except to handle this
```

### Alpaca test <15ms (too fast)
```powershell
# Verify SDK import works
python -c "from alpaca.trading.client import TradingClient; print('OK')"
# If fails: pip install alpaca-py
```

---

## 📝 AFTER VALIDATION

1. **Update migration revision ID** ✅
2. **Document security waivers** ✅
3. **Get VP approval for waivers** ⏸️
4. **Update skip ticket IDs** ⏸️
5. **Deploy to staging** ⏸️
6. **Monitor staging burn-in** ⏸️
7. **Production deployment** ⏸️

---

## 🎯 VALIDATION COMPLETE WHEN

✅ All 9 "MUST PASS" criteria met  
✅ All 5 "MUST FAIL" scenarios fail correctly  
✅ Security waivers documented  
✅ Migration applied successfully  
✅ No placeholder code found  

**Then**: Ready for staging deployment 🚀

---

**Quick Reference**: See `FALSE_POSITIVES_NEXT_STEPS.md` for detailed instructions
