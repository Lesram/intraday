# Quick Validation Protocol - Phases 1, 2, 4 (Skip Burn-In)
# Duration: ~50-60 minutes (vs 3.5 hours full suite)

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  QUICK DEPLOYMENT VALIDATION" -ForegroundColor Yellow
Write-Host "  Phases 1, 2, 4 (Skipping Burn-In)" -ForegroundColor Gray
Write-Host "========================================`n" -ForegroundColor Cyan

$ErrorActionPreference = "Continue"
$startTime = Get-Date
$phasesPass = 0
$totalPhases = 3

# Phase 1: Pre-Flight Validation
Write-Host "`n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host " [PHASE 1/3] PRE-FLIGHT VALIDATION" -ForegroundColor Cyan
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "Duration: ~2-3 minutes" -ForegroundColor Gray
Write-Host "Purpose: Verify system readiness`n" -ForegroundColor Gray

$phase1Start = Get-Date
.\pre_burnin_checklist.ps1
$phase1Duration = ((Get-Date) - $phase1Start).TotalSeconds

if ($LASTEXITCODE -eq 0) {
    $phasesPass++
    Write-Host "`n✅ Phase 1 PASSED ($([math]::Round($phase1Duration, 1))s)" -ForegroundColor Green
    Write-Host "   All 11 system checks passed" -ForegroundColor Gray
} else {
    Write-Host "`n❌ Phase 1 FAILED" -ForegroundColor Red
    Write-Host "   Fix system issues before proceeding" -ForegroundColor Yellow
    Write-Host "`n========================================`n" -ForegroundColor Cyan
    exit 1
}

# Phase 2: 5-Layer Comprehensive Tests
Write-Host "`n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host " [PHASE 2/3] 5-LAYER COMPREHENSIVE TESTS" -ForegroundColor Cyan
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "Duration: ~30-45 minutes" -ForegroundColor Gray
Write-Host "Purpose: Full functional validation`n" -ForegroundColor Gray
Write-Host "Testing:" -ForegroundColor Cyan
Write-Host "  - Layers 1-4: Database, Auth, Services, API" -ForegroundColor Gray
Write-Host "  - Layer 5: Business Workflows (End-to-End)" -ForegroundColor Gray
Write-Host "" 

$phase2Start = Get-Date
.\venv\Scripts\python.exe scripts/testing/run_complete_five_layer_tests.py
$phase2Duration = ((Get-Date) - $phase2Start).TotalMinutes

if ($LASTEXITCODE -eq 0) {
    $phasesPass++
    Write-Host "`n✅ Phase 2 PASSED ($([math]::Round($phase2Duration, 1)) min)" -ForegroundColor Green
    Write-Host "   All layers validated successfully" -ForegroundColor Gray
    Write-Host "   Coverage report: test_results/index.html" -ForegroundColor Gray
} else {
    Write-Host "`n⚠️  Phase 2 FAILED or HAD WARNINGS" -ForegroundColor Yellow
    Write-Host "   Review test output above for details" -ForegroundColor Gray
    Write-Host "`n   Continue to promotion gates anyway? (Y/N): " -NoNewline -ForegroundColor Cyan
    $continue = Read-Host
    if ($continue -eq "Y" -or $continue -eq "y") {
        Write-Host "   Continuing with warnings noted..." -ForegroundColor Yellow
    } else {
        Write-Host "`n❌ Validation stopped by user" -ForegroundColor Red
        Write-Host "`n========================================`n" -ForegroundColor Cyan
        exit 1
    }
}

# Phase 3: SKIPPED
Write-Host "`n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Yellow
Write-Host " [PHASE 3/3] BURN-IN STABILITY TEST - SKIPPED" -ForegroundColor Yellow
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Yellow
Write-Host "⏭️  This phase will be run separately (tonight)" -ForegroundColor Gray
Write-Host "Duration: 135 minutes (not run now)" -ForegroundColor Gray
Write-Host "Purpose: Long-term stability under sustained load" -ForegroundColor Gray
Write-Host "`nCommand to run later:" -ForegroundColor Cyan
Write-Host "  .\venv\Scripts\python.exe scripts/testing/burn_in_framework.py" -ForegroundColor White
Write-Host ""

# Phase 4: Promotion Gates
Write-Host "`n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host " [PHASE 4/3] AUTOMATED PROMOTION GATES" -ForegroundColor Cyan
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "Duration: ~15-20 minutes" -ForegroundColor Gray
Write-Host "Purpose: Deployment approval decision`n" -ForegroundColor Gray
Write-Host "Note: Gate 6 (Burn-In) will show as SKIPPED" -ForegroundColor Yellow
Write-Host ""

$phase4Start = Get-Date
.\venv\Scripts\python.exe scripts/testing/automated_promotion_gates.py
$phase4Duration = ((Get-Date) - $phase4Start).TotalMinutes

if ($LASTEXITCODE -eq 0) {
    $phasesPass++
    Write-Host "`n✅ Phase 4 PASSED ($([math]::Round($phase4Duration, 1)) min)" -ForegroundColor Green
    Write-Host "   All available gates passed" -ForegroundColor Gray
} else {
    Write-Host "`n⚠️  Phase 4 has warnings or failures" -ForegroundColor Yellow
    Write-Host "   Review gate results above" -ForegroundColor Gray
}

# Summary
$totalDuration = (Get-Date) - $startTime
$totalMinutes = [math]::Round($totalDuration.TotalMinutes, 1)

Write-Host "`n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host " QUICK VALIDATION RESULTS" -ForegroundColor Yellow
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan

Write-Host "`nPhases Completed: $phasesPass/3" -ForegroundColor White
Write-Host "Total Duration: $totalMinutes minutes" -ForegroundColor White

Write-Host "`nPhase Results:" -ForegroundColor Cyan
Write-Host "  ✅ Phase 1: Pre-Flight Validation ($([math]::Round($phase1Duration, 1))s)" -ForegroundColor Green

if ($phasesPass -ge 2) {
    Write-Host "  ✅ Phase 2: 5-Layer Tests ($([math]::Round($phase2Duration, 1)) min)" -ForegroundColor Green
} else {
    Write-Host "  ❌ Phase 2: 5-Layer Tests (failed)" -ForegroundColor Red
}

Write-Host "  ⏭️  Phase 3: Burn-In (SKIPPED - run tonight)" -ForegroundColor Yellow

if ($phasesPass -ge 3) {
    Write-Host "  ✅ Phase 4: Promotion Gates ($([math]::Round($phase4Duration, 1)) min)" -ForegroundColor Green
} else {
    Write-Host "  ⚠️  Phase 4: Promotion Gates (with warnings)" -ForegroundColor Yellow
}

Write-Host "`n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan

if ($phasesPass -eq 3) {
    Write-Host "`n🎉 QUICK VALIDATION COMPLETE!" -ForegroundColor Green
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Green
    Write-Host "`nStatus: FUNCTIONALLY VALIDATED ✅" -ForegroundColor Green
    Write-Host "`nWhat this means:" -ForegroundColor Cyan
    Write-Host "  ✅ All functional tests passed" -ForegroundColor White
    Write-Host "  ✅ Core platform ready for deployment" -ForegroundColor White
    Write-Host "  ⏭️  Long-term stability validation pending" -ForegroundColor Yellow
    
    Write-Host "`nNext Step - Run Burn-In Tonight:" -ForegroundColor Cyan
    Write-Host "  .\venv\Scripts\python.exe scripts/testing/burn_in_framework.py" -ForegroundColor White
    Write-Host "  (Duration: ~135 minutes / 2.25 hours)" -ForegroundColor Gray
    
    Write-Host "`nAfter Burn-In - Re-run Promotion Gates:" -ForegroundColor Cyan
    Write-Host "  .\venv\Scripts\python.exe scripts/testing/automated_promotion_gates.py" -ForegroundColor White
    Write-Host "  (Expected: All 6/6 gates pass → DEPLOYMENT READY)" -ForegroundColor Gray
    
    Write-Host "`n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
    Write-Host "Time Saved vs Full Suite: $([math]::Round(150 - $totalMinutes, 1)) minutes" -ForegroundColor Green
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`n" -ForegroundColor Cyan
    exit 0
    
} elseif ($phasesPass -eq 2) {
    Write-Host "`n⚠️  PARTIAL VALIDATION" -ForegroundColor Yellow
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Yellow
    Write-Host "`nStatus: Core tests passed, promotion gates had warnings" -ForegroundColor Yellow
    Write-Host "`nWhat to do:" -ForegroundColor Cyan
    Write-Host "  1. Review promotion gate output above" -ForegroundColor White
    Write-Host "  2. Address any critical warnings" -ForegroundColor White
    Write-Host "  3. Re-run gates if needed:" -ForegroundColor White
    Write-Host "     .\venv\Scripts\python.exe scripts/testing/automated_promotion_gates.py" -ForegroundColor Gray
    Write-Host "  4. Burn-in test still recommended tonight" -ForegroundColor White
    Write-Host "`n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`n" -ForegroundColor Yellow
    exit 0
    
} else {
    Write-Host "`n❌ VALIDATION INCOMPLETE" -ForegroundColor Red
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Red
    Write-Host "`nStatus: Critical phases failed" -ForegroundColor Red
    Write-Host "`nWhat to do:" -ForegroundColor Cyan
    Write-Host "  1. Review failure output above" -ForegroundColor White
    Write-Host "  2. Fix identified issues" -ForegroundColor White
    Write-Host "  3. Re-run quick validation:" -ForegroundColor White
    Write-Host "     .\quick_validation.ps1" -ForegroundColor Gray
    Write-Host "`n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`n" -ForegroundColor Red
    exit 1
}
