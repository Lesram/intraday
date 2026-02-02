#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Run a single test file with pytest
    
.DESCRIPTION
    This script runs a single test file using pytest with appropriate options.
    It's designed to work with the chaos and fuzz testing infrastructure.
    
.PARAMETER TestFile
    The path to the test file to run
    
.EXAMPLE
    .\scripts\run_one.ps1 -TestFile tests\chaos\test_broker_faults.py
    
.EXAMPLE
    .\scripts\run_one.ps1 -TestFile tests\fuzz\test_chaos.py
#>

param(
    [Parameter(Mandatory=$true)]
    [string]$TestFile
)

# Set error action preference
$ErrorActionPreference = "Stop"

# Check if test file exists
if (-not (Test-Path $TestFile)) {
    Write-Error "Test file not found: $TestFile"
    exit 1
}

# Change to the repository root directory
$RepoRoot = Split-Path $PSScriptRoot -Parent
Push-Location $RepoRoot

try {
    Write-Host "Running test file: $TestFile" -ForegroundColor Green
    Write-Host "Repository root: $RepoRoot" -ForegroundColor Gray
    
    # Run pytest with appropriate options
    python -m pytest $TestFile -v --tb=short
    
    $exitCode = $LASTEXITCODE
    if ($exitCode -eq 0) {
        Write-Host "✅ Test completed successfully" -ForegroundColor Green
    } else {
        Write-Host "❌ Test failed with exit code: $exitCode" -ForegroundColor Red
    }
    
    exit $exitCode
    
} finally {
    Pop-Location
}
