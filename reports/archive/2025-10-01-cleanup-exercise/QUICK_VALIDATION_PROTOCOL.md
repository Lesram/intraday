# Quick Deployment Validation Protocol (Skip Burn-In)

**Version:** 1.0  
**Date:** October 1, 2025  
**Duration:** ~50-60 minutes (vs 3.5 hours with burn-in)

## Overview

This is an accelerated validation protocol that skips the long burn-in test (Phase 3) for scenarios where:
- You need faster feedback during development
- The burn-in will be run separately later (e.g., tonight)
- You want to validate functionality without 2+ hours of stability testing

---

## 🎯 Quick Test Protocol Summary

| Phase | Test Suite | Duration | Pass Criteria | Purpose |
|-------|-----------|----------|---------------|---------|
| **Phase 1** | Pre-Flight Validation | 2-3 min | 11/11 checks pass | System readiness |
| **Phase 2** | 5-Layer Comprehensive Tests | 30-45 min | 100% pass, >95% coverage | Full functional validation |
| **Phase 3** | ~~Burn-In Stability Test~~ | ~~135 min~~ | **SKIPPED** | _Run separately tonight_ |
| **Phase 4** | Automated Promotion Gates | 15-20 min | 6/6 gates pass* | Deployment approval |

**Total Duration:** ~50-60 minutes (vs 3.5 hours full suite)

*Note: Phase 4 Gate 6 (Burn-In Stability) will show as SKIPPED or N/A since burn-in wasn't run.

---

## Quick Execution Commands

### Option 1: Run All Three Phases Sequentially

```powershell
# Phase 1: Pre-Flight (2-3 min)
.\pre_burnin_checklist.ps1

# Phase 2: 5-Layer Tests (30-45 min)
.\venv\Scripts\python.exe scripts/testing/run_complete_five_layer_tests.py

# Phase 4: Promotion Gates (15-20 min)
.\venv\Scripts\python.exe scripts/testing/automated_promotion_gates.py
```

### Option 2: Single Command (Create Helper Script)

Create `quick_validation.ps1`:

```powershell
# Quick Validation Protocol - Phases 1, 2, 4 (Skip Burn-In)

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  QUICK DEPLOYMENT VALIDATION" -ForegroundColor Yellow
Write-Host "  Phases 1, 2, 4 (Skipping Burn-In)" -ForegroundColor Gray
Write-Host "========================================`n" -ForegroundColor Cyan

$ErrorActionPreference = "Continue"
$startTime = Get-Date
$phasesPass = 0
$totalPhases = 3

# Phase 1: Pre-Flight Validation
Write-Host "`n[PHASE 1/3] PRE-FLIGHT VALIDATION" -ForegroundColor Cyan
Write-Host "Duration: ~2-3 minutes`n" -ForegroundColor Gray
.\pre_burnin_checklist.ps1
if ($LASTEXITCODE -eq 0) {
    $phasesPass++
    Write-Host "`n✅ Phase 1 PASSED`n" -ForegroundColor Green
} else {
    Write-Host "`n❌ Phase 1 FAILED - Fix issues before proceeding`n" -ForegroundColor Red
    exit 1
}

# Phase 2: 5-Layer Comprehensive Tests
Write-Host "`n[PHASE 2/3] 5-LAYER COMPREHENSIVE TESTS" -ForegroundColor Cyan
Write-Host "Duration: ~30-45 minutes`n" -ForegroundColor Gray
.\venv\Scripts\python.exe scripts/testing/run_complete_five_layer_tests.py
if ($LASTEXITCODE -eq 0) {
    $phasesPass++
    Write-Host "`n✅ Phase 2 PASSED`n" -ForegroundColor Green
} else {
    Write-Host "`n⚠️  Phase 2 FAILED - Review test output`n" -ForegroundColor Yellow
    Write-Host "Continue to promotion gates? (Y/N): " -NoNewline
    $continue = Read-Host
    if ($continue -ne "Y" -and $continue -ne "y") {
        exit 1
    }
}

# Phase 3: SKIPPED
Write-Host "`n[PHASE 3/3] BURN-IN STABILITY TEST - SKIPPED" -ForegroundColor Yellow
Write-Host "⏭️  This phase will be run separately (tonight)" -ForegroundColor Gray
Write-Host "Duration: 135 minutes (not run now)`n" -ForegroundColor Gray

# Phase 4: Promotion Gates
Write-Host "`n[PHASE 4/3] AUTOMATED PROMOTION GATES" -ForegroundColor Cyan
Write-Host "Duration: ~15-20 minutes`n" -ForegroundColor Gray
Write-Host "Note: Gate 6 (Burn-In) will show as SKIPPED`n" -ForegroundColor Gray
.\venv\Scripts\python.exe scripts/testing/automated_promotion_gates.py
if ($LASTEXITCODE -eq 0) {
    $phasesPass++
    Write-Host "`n✅ Phase 4 PASSED`n" -ForegroundColor Green
} else {
    Write-Host "`n⚠️  Phase 4 has warnings - Review gate results`n" -ForegroundColor Yellow
}

# Summary
$duration = (Get-Date) - $startTime
$totalMinutes = [math]::Round($duration.TotalMinutes, 1)

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  QUICK VALIDATION RESULTS" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "`nPhases Completed: $phasesPass/3" -ForegroundColor White
Write-Host "Total Duration: $totalMinutes minutes" -ForegroundColor White
Write-Host "`nPhase Results:" -ForegroundColor Cyan
Write-Host "  ✅ Phase 1: Pre-Flight Validation" -ForegroundColor Green
if ($phasesPass -ge 2) {
    Write-Host "  ✅ Phase 2: 5-Layer Tests" -ForegroundColor Green
} else {
    Write-Host "  ❌ Phase 2: 5-Layer Tests" -ForegroundColor Red
}
Write-Host "  ⏭️  Phase 3: Burn-In (SKIPPED - run tonight)" -ForegroundColor Yellow
if ($phasesPass -ge 3) {
    Write-Host "  ✅ Phase 4: Promotion Gates" -ForegroundColor Green
} else {
    Write-Host "  ⚠️  Phase 4: Promotion Gates (with warnings)" -ForegroundColor Yellow
}

Write-Host "`n========================================" -ForegroundColor Cyan

if ($phasesPass -eq 3) {
    Write-Host "`n🎉 QUICK VALIDATION COMPLETE!" -ForegroundColor Green
    Write-Host "✅ Platform is functionally validated" -ForegroundColor White
    Write-Host "⏭️  Run burn-in test tonight for full approval" -ForegroundColor Yellow
    Write-Host "`nNext Step:" -ForegroundColor Cyan
    Write-Host "  .\venv\Scripts\python.exe scripts/testing/burn_in_framework.py" -ForegroundColor White
    Write-Host "`n========================================`n" -ForegroundColor Cyan
    exit 0
} else {
    Write-Host "`n⚠️  VALIDATION INCOMPLETE" -ForegroundColor Yellow
    Write-Host "Some phases failed - review output above" -ForegroundColor White
    Write-Host "`n========================================`n" -ForegroundColor Cyan
    exit 1
}
```

---

## 📋 Detailed Phase Breakdown

### Phase 1: Pre-Flight Validation ✈️ (2-3 min)

**Command:**
```powershell
.\pre_burnin_checklist.ps1
```

**What It Checks:**
- Python environment active
- Required packages installed
- K6 available
- Server running and healthy
- Authentication working
- SLI/SLO endpoints responding
- All services available (signals, orders, risk)

**Pass Criteria:** 11/11 checks ✅

**On Failure:** Fix issues before proceeding to Phase 2

---

### Phase 2: 5-Layer Comprehensive Tests 🏗️ (30-45 min)

**Command:**
```powershell
.\venv\Scripts\python.exe scripts/testing/run_complete_five_layer_tests.py
```

**What It Tests:**
- **Layers 1-4:** Database, Auth, Services, API (Foundation)
- **Layer 5:** Business Workflows (End-to-End)

**Pass Criteria:** 
- 100% test pass rate
- >95% code coverage
- No critical errors

**On Failure:** 
- Review pytest output
- Check logs in `logs/` directory
- Decision: Fix and re-run, or note issues and continue to gates

---

### Phase 3: Burn-In Stability Test 🔥 ~~(135 min)~~ **SKIPPED**

**Status:** ⏭️ **SKIPPED - Run Tonight**

**Original Command:**
```powershell
# Run this separately tonight:
.\venv\Scripts\python.exe scripts/testing/burn_in_framework.py
```

**Why Skip Now:**
- Takes 2+ hours (135 minutes)
- Tests long-term stability under sustained load
- Can be run separately as overnight/evening job
- Functional tests (Phase 2) already validate core functionality

**Impact on Phase 4:**
- Gate 6 (Burn-In Stability) will show as SKIPPED or N/A
- Other 5 gates will still validate
- Overall deployment approval will note "pending burn-in"

---

### Phase 4: Automated Promotion Gates 🚪 (15-20 min)

**Command:**
```powershell
.\venv\Scripts\python.exe scripts/testing/automated_promotion_gates.py
```

**6 Gates Evaluated:**

| Gate | Name | Status | Impact |
|------|------|--------|--------|
| 1 | System Readiness | ✅ Will Pass | Validated in Phase 1 |
| 2 | Unit Test Coverage | ✅ Will Pass | Validated in Phase 2 |
| 3 | Integration Testing | ✅ Will Pass | Validated in Phase 2 |
| 4 | Performance Validation | ✅ Will Pass | K6 test working |
| 5 | SLI/SLO Compliance | ✅ Will Pass | Endpoints operational |
| 6 | Burn-In Stability | ⚠️ SKIPPED | Not run yet |

**Expected Result:**
- 5/6 gates pass with HIGH confidence
- Gate 6 shows as SKIPPED or deferred
- Overall: "FUNCTIONAL VALIDATION COMPLETE - BURN-IN PENDING"

**Pass Criteria:**
- Gates 1-5 all pass
- Gate 6 acknowledged as pending
- No critical blockers identified

---

## 📊 Expected Timeline

```
T+0:00    Start quick_validation.ps1
T+0:03    Phase 1 complete ✅
T+0:48    Phase 2 complete ✅ (worst case 45 min)
T+0:48    Phase 3 SKIPPED ⏭️
T+1:08    Phase 4 complete ✅ (worst case 20 min)
───────────────────────────────────────────
TOTAL:    ~50-70 minutes
```

**Compared to Full Suite:**
- Full Suite: ~210 minutes (3.5 hours)
- Quick Suite: ~60 minutes (1 hour)
- **Time Saved: 150 minutes (2.5 hours)**

---

## ✅ Success Criteria (Quick Validation)

### Must Pass:
- ✅ Phase 1: All 11 pre-flight checks
- ✅ Phase 2: 100% test pass rate, >95% coverage
- ✅ Phase 4: Gates 1-5 all pass with HIGH confidence

### Acceptable Warnings:
- ⚠️ Gate 6 (Burn-In) shows as SKIPPED - expected
- ⚠️ "Burn-in test recommended before production" - expected

### Result:
**"FUNCTIONALLY VALIDATED - BURN-IN PENDING"**

This means:
- ✅ All functional tests pass
- ✅ Core platform ready for deployment
- ⏭️ Long-term stability validation pending (tonight)

---

## 🚨 When to Use Quick Validation vs Full Suite

### Use Quick Validation (Phases 1, 2, 4) When:
- ✅ During active development (need fast feedback)
- ✅ Before committing code changes
- ✅ Burn-in will be run separately (tonight, as scheduled)
- ✅ You need functional validation quickly
- ✅ Making small, low-risk changes

### Use Full Suite (All 4 Phases) When:
- 🎯 Before production deployment (final approval)
- 🎯 After major architectural changes
- 🎯 Before releasing to customers
- 🎯 When you have 3+ hours available
- 🎯 Need complete stability validation

---

## 📝 Next Steps After Quick Validation

### If All Phases Pass (5/6 Gates):

```powershell
# Tonight: Run the full burn-in test
.\venv\Scripts\python.exe scripts/testing/burn_in_framework.py  # 135 min

# After burn-in completes: Re-run promotion gates
.\venv\Scripts\python.exe scripts/testing/automated_promotion_gates.py  # 20 min

# Expected: All 6/6 gates pass → READY FOR DEPLOYMENT
```

### If Phase 2 Fails:

```powershell
# 1. Review test failures
# 2. Fix critical issues
# 3. Re-run just Phase 2 to verify:
.\venv\Scripts\python.exe scripts/testing/run_complete_five_layer_tests.py

# 4. Once fixed, re-run quick validation from Phase 1
```

### If Phase 4 Has Critical Warnings:

```powershell
# 1. Review which gate(s) failed (besides Gate 6)
# 2. Address root causes
# 3. Re-run promotion gates:
.\venv\Scripts\python.exe scripts/testing/automated_promotion_gates.py
```

---

## 💡 Pro Tips

### 1. Run Quick Validation Multiple Times
Since it's only ~1 hour, you can run it several times during development:
```powershell
# Morning: After making changes
.\quick_validation.ps1

# Afternoon: After more changes  
.\quick_validation.ps1

# Evening: Final check before burn-in
.\quick_validation.ps1

# Night: Full burn-in test
.\venv\Scripts\python.exe scripts/testing/burn_in_framework.py
```

### 2. Save Time with Selective Re-runs
If only Phase 2 fails, no need to re-run Phase 1:
```powershell
# Just re-run Phase 2
.\venv\Scripts\python.exe scripts/testing/run_complete_five_layer_tests.py

# Then jump to Phase 4
.\venv\Scripts\python.exe scripts/testing/automated_promotion_gates.py
```

### 3. Review Coverage While Running
Phase 2 generates coverage reports in `test_results/`:
```powershell
# While tests are running, open another terminal:
.\view_coverage.bat  # View coverage HTML report
```

### 4. Monitor Server Health
Keep server terminal visible during tests to catch any errors:
```powershell
# Server terminal should show:
# - No 500 errors
# - Successful authentication
# - Normal request flow
```

---

## 🎯 Quick Reference Card

```
┌─────────────────────────────────────────────────┐
│       QUICK VALIDATION (Skip Burn-In)           │
├─────────────────────────────────────────────────┤
│ Duration: ~50-60 minutes                        │
│                                                 │
│ Phase 1: Pre-Flight         2-3 min      ✅    │
│ Phase 2: 5-Layer Tests      30-45 min    ✅    │
│ Phase 3: Burn-In            SKIPPED      ⏭️     │
│ Phase 4: Promotion Gates    15-20 min    ✅    │
│                                                 │
│ Result: Functional Validation Complete         │
│         Burn-In Pending (tonight)               │
├─────────────────────────────────────────────────┤
│ Single Command:                                 │
│   .\quick_validation.ps1                        │
│                                                 │
│ Or Step-by-Step:                                │
│   .\pre_burnin_checklist.ps1                    │
│   .\venv\Scripts\python.exe \                   │
│     scripts/testing/run_complete_five_layer_\   │
│     tests.py                                    │
│   .\venv\Scripts\python.exe \                   │
│     scripts/testing/automated_promotion_\       │
│     gates.py                                    │
└─────────────────────────────────────────────────┘
```

---

**Last Updated:** October 1, 2025  
**Use Case:** Fast functional validation, burn-in deferred  
**Time Savings:** 2.5 hours vs full suite
