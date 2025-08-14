#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Generate     Write-Host "X Coverage check failed!" -ForegroundColor Redomprehensive coverage report and check package floors

.DESCRIPTION
    Runs coverage analysis and validates per-package minimum thresholds.
    Supports soft mode for development and strict mode for CI/CD.
    
.PARAMETER Soft
    Run in soft mode - emit warnings without failing
    
.EXAMPLE
    .\coverage-report.ps1
    .\coverage-report.ps1 -Soft
#>

param(
    [switch]$Soft = $false
)

# Ensure we're in the correct directory
Set-Location $PSScriptRoot

# Activate virtual environment if it exists  
if (Test-Path "venv\Scripts\Activate.ps1") {
    & "venv\Scripts\Activate.ps1"
}

# Create test reports directory
if (-not (Test-Path "test_reports")) {
    New-Item -ItemType Directory -Path "test_reports" -Force
}

Write-Host "📊 Generating coverage report and checking package floors..." -ForegroundColor Magenta

$softFlag = if ($Soft) { "--soft" } else { "" }

if ($softFlag) {
    python scripts/check_coverage.py --soft
} else {
    python scripts/check_coverage.py  
}

$exitCode = $LASTEXITCODE

if ($exitCode -eq 0) {
    Write-Host "Check Coverage check passed!" -ForegroundColor Green
} else {
    Write-Host "X Coverage check failed!" -ForegroundColor Red
}

exit $exitCode
