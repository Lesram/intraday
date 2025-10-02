# ✅ PLATFORM CLEANUP CHECKLIST

**Use this checklist to track cleanup progress**

## 📋 Pre-Cleanup Review

- [ ] Read `AUDIT_EXECUTIVE_SUMMARY.md` (10 min)
- [ ] Review `COMPREHENSIVE_PLATFORM_AUDIT_REPORT.md` (30 min)
- [ ] Test cleanup script in dry-run mode: `.\cleanup_platform.ps1 -DryRun`
- [ ] Review dry-run output and verify it's safe to proceed

## 🔧 Phase 1: Automated Cleanup (30 minutes)

### Run Cleanup Script
- [ ] Execute: `.\cleanup_platform.ps1`
- [ ] Verify backup created in `backups/`
- [ ] Review statistics output
- [ ] Check `git status` to see changes

### Validate Changes
- [ ] Run tests: `.\quick_validation.ps1`
- [ ] Verify all tests still pass (23/23)
- [ ] Check imports still work:
  ```powershell
  python -c "from backend.database import DatabaseManager; print('✅ Database imports OK')"
  python -c "from backend.config.settings import settings; print('✅ Config imports OK')"
  python -c "from backend.strategies.engine import StrategyEngine; print('✅ Strategy imports OK')"
  ```

### Commit Cleanup
- [ ] Review changes: `git diff --stat`
- [ ] Stage changes: `git add .`
- [ ] Commit: `git commit -m "chore: platform cleanup and organization"`
- [ ] Tag: `git tag cleanup-v1.0 -m "Post-audit cleanup"`

## 🗄️ Phase 2: Database Consolidation (2-3 hours)

### Critical: Fix Database Layer
- [ ] Read "Phase 1: Critical Fixes" in audit report
- [ ] Create `backend/database/manager.py` (rename from `database.py`)
- [ ] Update imports across codebase
- [ ] Merge `models.py` + `models_production.py`
- [ ] Update `backend/database/__init__.py` to re-export from manager
- [ ] Remove or document `backend/infra/unified_database.py`

### Document Database Usage
- [ ] Create `DATABASE_USAGE.md` documenting:
  - Which .db file is used when
  - How to switch between databases
  - Backup and restore procedures
- [ ] Fix `.env.production` to use PostgreSQL URL
- [ ] Update environment documentation

### Validate Database Changes
- [ ] Run database tests: `pytest test/backend/database/`
- [ ] Test database connections in each environment
- [ ] Verify migrations still work
- [ ] Run full test suite: `.\quick_validation.ps1`

## 📚 Phase 3: Documentation Organization (1 hour)

### Move Documentation Files
- [ ] Create doc structure:
  ```powershell
  mkdir docs/testing, docs/deployment, docs/reports/phases, docs/integration, docs/ai
  ```
- [ ] Move MD files per audit report Section "A. Root Directory Clutter"
- [ ] Update links in README.md
- [ ] Verify all documentation is accessible

### Update README
- [ ] Add "Documentation Structure" section
- [ ] Add "Database Configuration" section
- [ ] Update "Quick Start" with new file locations
- [ ] Add link to audit reports

## 🧪 Phase 4: Testing Organization (1 hour)

### Merge Test Directories
- [ ] Review files in `tests/` directory
- [ ] Decide which tests to keep active
- [ ] Move tests from `tests/` into `test/`
- [ ] Delete empty `tests/` directory
- [ ] Update test paths in CI/CD

### Validate Test Organization
- [ ] Run all tests: `pytest test/`
- [ ] Verify coverage hasn't dropped
- [ ] Update test documentation
- [ ] Check CI/CD still works

## ✅ Phase 5: Final Validation (30 minutes)

### Run Complete Test Suite
- [ ] Pre-flight validation: Phase 1 of quick_validation.ps1
- [ ] 5-Layer tests: Phase 2 of quick_validation.ps1
- [ ] Verify 100% pass rate maintained
- [ ] Check no new warnings or errors

### Verify System Health
- [ ] Test server startup: `python main.py`
- [ ] Health check: `curl http://localhost:8000/health`
- [ ] Auth test: `curl http://localhost:8000/api/v1/auth/login`
- [ ] Database connectivity test

### Documentation Update
- [ ] Update architecture diagrams if needed
- [ ] Document cleanup changes in CHANGELOG
- [ ] Update team documentation
- [ ] Create migration guide for team members

## 🎯 Tonight: Burn-In Test

- [ ] Run burn-in test: `.\venv\Scripts\python.exe scripts\testing\burn_in_framework.py`
- [ ] Monitor for 135 minutes
- [ ] Review stability report
- [ ] Check for memory leaks
- [ ] Verify performance metrics

## 🚀 Post Burn-In: Promotion Gates

- [ ] Re-run promotion gates: `.\venv\Scripts\python.exe scripts\testing\automated_promotion_gates.py`
- [ ] Verify all 6 gates pass
- [ ] Review deployment approval
- [ ] Prepare for production deployment

## 📊 Success Metrics Checklist

After cleanup, verify these targets are met:

### File Organization
- [ ] Root directory < 60 files ✅ Target: 50
- [ ] Test files in root = 0 ✅ Target: 0
- [ ] htmlcov folders = 1 ✅ Target: 1
- [ ] Database .db files ≤ 4 ✅ Target: 4
- [ ] Documentation organized ✅ All in docs/

### System Health
- [ ] All tests passing ✅ Target: 100%
- [ ] No broken imports ✅ All imports work
- [ ] Server starts clean ✅ No warnings
- [ ] Database connections work ✅ All environments

### Performance
- [ ] Disk space < 5 GB ✅ Target: ~5.0 GB
- [ ] Test suite < 2 min ✅ Quick validation
- [ ] CI/CD builds pass ✅ No failures

### Documentation
- [ ] README up-to-date ✅
- [ ] Architecture docs current ✅
- [ ] API docs generated ✅
- [ ] Deployment guide ready ✅

## 🎓 Lessons Learned (Document After Cleanup)

### What Went Well
- [ ] Document successes
- [ ] Note best practices to keep
- [ ] Identify process improvements

### What to Improve
- [ ] Document pain points
- [ ] Note areas needing better structure
- [ ] Plan preventive measures

### Future Recommendations
- [ ] Set up pre-commit hooks
- [ ] Establish cleanup cadence
- [ ] Define file organization standards
- [ ] Create architectural decision records (ADRs)

## 📞 Help & Resources

**If Something Goes Wrong:**
1. Restore from backup: `backups/platform_backup_YYYYMMDD_HHMMSS.zip`
2. Revert git changes: `git reset --hard HEAD~1`
3. Review audit report for detailed guidance
4. Check specific error in troubleshooting section

**Key Files:**
- Audit Report: `COMPREHENSIVE_PLATFORM_AUDIT_REPORT.md`
- Executive Summary: `AUDIT_EXECUTIVE_SUMMARY.md`
- Cleanup Script: `cleanup_platform.ps1`
- This Checklist: `CLEANUP_CHECKLIST.md`

**Estimated Time Investment:**
- Phase 1 (Automated): 30 minutes ⚡
- Phase 2 (Database): 2-3 hours 🔧
- Phase 3 (Docs): 1 hour 📚
- Phase 4 (Tests): 1 hour 🧪
- Phase 5 (Validate): 30 minutes ✅
- **Total: 5-6 hours**

**When to Do What:**
- Before burn-in: Phase 1 (optional: Phases 2-5)
- After burn-in: Phases 2-5 (if not done earlier)
- Before production: Validate everything ✅

---

**Current Status:**

Cleanup Phase: [ ] Not Started  [ ] In Progress  [ ] Complete  
Validation: [ ] Passed  [ ] Failed  
Production Ready: [ ] Yes  [ ] No  [ ] After burn-in  

Last Updated: _______________  
Updated By: _______________  

