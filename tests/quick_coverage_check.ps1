#!/usr/bin/env pwsh
# Quick Coverage Check - Fast partial test run to estimate progress
# Runs a subset of tests and extracts coverage percentage

Write-Host "Running quick coverage check..." -ForegroundColor Cyan

# Run only unit tests (faster than full suite)
$output = python -m pytest tests/unit/ -q --cov=backend --cov-report=term 2>&1 | Select-String -Pattern "TOTAL"

if ($output) {
    Write-Host "`n$output" -ForegroundColor Green
    
    # Extract percentage
    if ($output -match '(\d+)%') {
        $coverage = $matches[1]
        Write-Host "`nCurrent Coverage: $coverage%" -ForegroundColor Yellow -BackgroundColor Black
        
        $remaining = 100 - [int]$coverage
        Write-Host "Remaining to 100%: $remaining%" -ForegroundColor Magenta
    }
} else {
    Write-Host "Could not extract coverage data" -ForegroundColor Red
}

# Test count
$testCount = python -m pytest tests/unit/ --co -q 2>&1 | Select-String -Pattern "test session starts" -Context 0,1
Write-Host "`n$testCount" -ForegroundColor Cyan
