# STANDARDIZED TEST EXECUTION - POWERSHELL VERSION
# This script ensures we stay in the correct directory

Set-Location "C:\Users\Marsel\intra\algotrading_platform"
Write-Host "======================================================================" -ForegroundColor Green
Write-Host "STANDARDIZED ALGOTRADING PLATFORM TEST EXECUTION" -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Green
Write-Host "Current Directory: $(Get-Location)" -ForegroundColor Yellow
Write-Host "Tests Directory Exists: $(Test-Path 'tests')" -ForegroundColor Yellow
Write-Host "Platform Root: C:\Users\Marsel\intra\algotrading_platform" -ForegroundColor Yellow
Write-Host ""

# Verify we're in the right place
if (-not (Test-Path "tests")) {
    Write-Host "ERROR: Tests directory not found!" -ForegroundColor Red
    Write-Host "Current location: $(Get-Location)" -ForegroundColor Red
    exit 1
}

# Clean up any existing results
if (Test-Path "full_test_results.xml") {
    Remove-Item "full_test_results.xml"
    Write-Host "Cleaned up previous results file" -ForegroundColor Yellow
}

Write-Host "Starting comprehensive test execution..." -ForegroundColor Green
Write-Host "Target: All 3,907 tests" -ForegroundColor Green
Write-Host ""

# Run pytest with explicit working directory maintenance
& python -m pytest tests/ --tb=line -v --continue-on-collection-errors --maxfail=9999 --disable-warnings --junit-xml=full_test_results.xml

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Green
Write-Host "TEST EXECUTION COMPLETED" -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Green
Write-Host "Final Directory: $(Get-Location)" -ForegroundColor Yellow
Write-Host "Results File Exists: $(Test-Path 'full_test_results.xml')" -ForegroundColor Yellow

if (Test-Path "full_test_results.xml") {
    $fileSize = (Get-Item "full_test_results.xml").Length
    Write-Host "Results File Size: $fileSize bytes" -ForegroundColor Green
} else {
    Write-Host "WARNING: Results file was not created!" -ForegroundColor Red
}
