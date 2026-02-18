# run_all_tests_and_report.ps1
# Three-tier test runner for the algotrading platform.
#
# Usage:
#   .\scripts\ci\run_all_tests_and_report.ps1 -Tier Smoke
#   .\scripts\ci\run_all_tests_and_report.ps1 -Tier Integration
#   .\scripts\ci\run_all_tests_and_report.ps1 -Tier Full
#   .\scripts\ci\run_all_tests_and_report.ps1                  # defaults to Smoke

param(
    [ValidateSet("Smoke", "Integration", "Full")]
    [string]$Tier = "Smoke"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Push-Location $ProjectRoot

try {
    switch ($Tier) {
        "Smoke" {
            Write-Host "=== Tier 1: Smoke Tests (< 30s) ===" -ForegroundColor Cyan
            python -m pytest -x -q -m "unit" --maxfail=3 --tb=short --timeout=15
        }
        "Integration" {
            Write-Host "=== Tier 2: Integration Tests (< 5 min) ===" -ForegroundColor Yellow
            python -m pytest -x -q -m "unit or api or services" --cov=backend --cov-branch --tb=short --timeout=30
        }
        "Full" {
            Write-Host "=== Tier 3: Full Suite ===" -ForegroundColor Magenta
            python -m pytest -v --cov=backend --cov-branch --cov-report=html:test_results --cov-report="term-missing:skip-covered" --timeout=30
        }
    }

    $ExitCode = $LASTEXITCODE
    if ($ExitCode -eq 0) {
        Write-Host "`n$Tier tier: ALL PASSED" -ForegroundColor Green
    } else {
        Write-Host "`n$Tier tier: FAILURES DETECTED (exit code $ExitCode)" -ForegroundColor Red
    }
    exit $ExitCode
} finally {
    Pop-Location
}
