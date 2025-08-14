#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Run fast unit, API, and service tests with coverage reporting

.DESCRIPTION
    Executes pytest with markers for unit, api, and services tests.
    Provides coverage reporting optimized for quick feedback during development.
    
.EXAMPLE
    .\test-fast.ps1
#>

# Ensure we're in the correct directory
Set-Location $PSScriptRoot

# Activate virtual environment if it exists
if (Test-Path "venv\Scripts\Activate.ps1") {
    & "venv\Scripts\Activate.ps1"
}

Write-Host "🚀 Running fast test suite..." -ForegroundColor Green

python -m pytest `
    -q `
    -m "unit or api or services" `
    --cov=backend `
    --cov-branch `
    --cov-report=term-missing:skip-covered `
    --maxfail=5 `
    --timeout=30

$exitCode = $LASTEXITCODE
Write-Host "✅ Fast test suite completed with exit code: $exitCode" -ForegroundColor $(if ($exitCode -eq 0) { "Green" } else { "Red" })
exit $exitCode
