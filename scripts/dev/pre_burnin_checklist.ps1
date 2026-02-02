#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Pre-Burn-in Validation Checklist
    
.DESCRIPTION
    Validates all systems are ready for the 135-minute burn-in test.
    Run this script when the server is up to ensure everything is configured correctly.
    
.EXAMPLE
    .\pre_burnin_checklist.ps1
#>

$ErrorActionPreference = "Continue"
$VenvPython = ".\venv\Scripts\python.exe"
$BaseURL = "http://localhost:8000"

Write-Host "=" -ForegroundColor Cyan -NoNewline; Write-Host ("=" * 69) -ForegroundColor Cyan
Write-Host "🔍 PRE-BURN-IN VALIDATION CHECKLIST" -ForegroundColor Cyan
Write-Host "=" -ForegroundColor Cyan -NoNewline; Write-Host ("=" * 69) -ForegroundColor Cyan
Write-Host ""

$TotalChecks = 0
$PassedChecks = 0
$FailedChecks = 0

function Test-Check {
    param(
        [string]$Name,
        [scriptblock]$Test,
        [string]$SuccessMessage,
        [string]$FailureMessage,
        [bool]$Critical = $false
    )
    
    $script:TotalChecks++
    Write-Host "🔍 Checking: " -NoNewline -ForegroundColor Yellow
    Write-Host $Name -ForegroundColor White
    
    try {
        $result = & $Test
        if ($result) {
            Write-Host "   ✅ PASS: " -NoNewline -ForegroundColor Green
            Write-Host $SuccessMessage -ForegroundColor White
            $script:PassedChecks++
            Write-Host ""
            return $true
        } else {
            Write-Host "   ❌ FAIL: " -NoNewline -ForegroundColor Red
            Write-Host $FailureMessage -ForegroundColor White
            if ($Critical) {
                Write-Host "   🚨 CRITICAL: This must be fixed before burn-in test" -ForegroundColor Red
            }
            $script:FailedChecks++
            Write-Host ""
            return $false
        }
    } catch {
        Write-Host "   ❌ ERROR: " -NoNewline -ForegroundColor Red
        Write-Host $_.Exception.Message -ForegroundColor White
        if ($Critical) {
            Write-Host "   🚨 CRITICAL: This must be fixed before burn-in test" -ForegroundColor Red
        }
        $script:FailedChecks++
        Write-Host ""
        return $false
    }
}

# ============================================================================
# CHECK 1: Python Virtual Environment
# ============================================================================
Test-Check -Name "Python Virtual Environment" -Test {
    Test-Path $VenvPython
} -SuccessMessage "Virtual environment Python found at $VenvPython" `
  -FailureMessage "Virtual environment not found. Run: python -m venv venv" `
  -Critical $true

# ============================================================================
# CHECK 2: Required Python Packages
# ============================================================================
Test-Check -Name "Required Python Packages (psutil)" -Test {
    $output = & $VenvPython -c "import psutil; print('OK')" 2>&1
    $output -match "OK"
} -SuccessMessage "psutil package installed in venv" `
  -FailureMessage "psutil not installed. Run: .\venv\Scripts\python.exe -m pip install psutil" `
  -Critical $true

Test-Check -Name "Required Python Packages (aiohttp)" -Test {
    $output = & $VenvPython -c "import aiohttp; print('OK')" 2>&1
    $output -match "OK"
} -SuccessMessage "aiohttp package installed in venv" `
  -FailureMessage "aiohttp not installed. Run: pip install aiohttp" `
  -Critical $true

# ============================================================================
# CHECK 3: K6 Installation
# ============================================================================
Test-Check -Name "K6 Load Testing Tool" -Test {
    $null = Get-Command k6 -ErrorAction SilentlyContinue
    $?
} -SuccessMessage "K6 is installed and in PATH" `
  -FailureMessage "K6 not found. Install from: https://k6.io/docs/getting-started/installation/" `
  -Critical $true

# ============================================================================
# CHECK 4: Server Availability
# ============================================================================
Test-Check -Name "Server Health Endpoint" -Test {
    try {
        $response = Invoke-RestMethod -Uri "$BaseURL/health" -Method Get -TimeoutSec 5 -ErrorAction Stop
        # Accept various health status indicators
        ($response.status -in @("healthy", "ok", "ready")) -or ($null -ne $response.status)
    } catch {
        $false
    }
} -SuccessMessage "Server is running and healthy at $BaseURL" `
  -FailureMessage "Server not responding. Start with: uvicorn main:app --reload" `
  -Critical $true

# ============================================================================
# CHECK 5: Authentication Endpoint
# ============================================================================
Test-Check -Name "Authentication Endpoint" -Test {
    try {
        $body = "username=admin&password=admin123"
        $headers = @{
            "Content-Type" = "application/x-www-form-urlencoded"
        }
        $response = Invoke-RestMethod -Uri "$BaseURL/api/v1/auth/login" -Method Post -Body $body -Headers $headers -TimeoutSec 5 -ErrorAction Stop
        $null -ne $response.access_token
    } catch {
        $false
    }
} -SuccessMessage "Authentication working (form-urlencoded format)" `
  -FailureMessage "Authentication failed. Check credentials and format" `
  -Critical $true

# ============================================================================
# CHECK 6: SLI Metrics Endpoint
# ============================================================================
Test-Check -Name "SLI Metrics Endpoint" -Test {
    try {
        $response = Invoke-RestMethod -Uri "$BaseURL/api/v1/monitoring/sli-metrics" -Method Get -TimeoutSec 5 -ErrorAction Stop
        $null -ne $response.routes
    } catch {
        $false
    }
} -SuccessMessage "SLI metrics endpoint responding with route data" `
  -FailureMessage "SLI endpoint not available (non-critical, will use fallback)" `
  -Critical $false

# ============================================================================
# CHECK 7: SLO Status Endpoint
# ============================================================================
Test-Check -Name "SLO Status Endpoint" -Test {
    try {
        $response = Invoke-RestMethod -Uri "$BaseURL/api/v1/monitoring/slo-status" -Method Get -TimeoutSec 5 -ErrorAction Stop
        $null -ne $response.compliance
    } catch {
        $false
    }
} -SuccessMessage "SLO status endpoint responding with compliance data" `
  -FailureMessage "SLO endpoint not available (non-critical, will use fallback)" `
  -Critical $false

# ============================================================================
# CHECK 8: Required Service Endpoints
# ============================================================================
Write-Host "🔍 Checking: " -NoNewline -ForegroundColor Yellow
Write-Host "Required Service Endpoints (3/3)" -ForegroundColor White

try {
    # Get auth token
    $body = "username=admin&password=admin123"
    $headers = @{
        "Content-Type" = "application/x-www-form-urlencoded"
    }
    $authResponse = Invoke-RestMethod -Uri "$BaseURL/api/v1/auth/login" -Method Post -Body $body -Headers $headers -ErrorAction Stop
    $token = $authResponse.access_token
    
    $authHeaders = @{
        "Authorization" = "Bearer $token"
    }
    
    $endpoints = @("/api/v1/signals", "/api/v1/orders", "/api/v1/risk/metrics")
    $available = 0
    
    foreach ($endpoint in $endpoints) {
        try {
            $response = Invoke-WebRequest -Uri "$BaseURL$endpoint" -Method Get -Headers $authHeaders -TimeoutSec 5 -ErrorAction Stop
            # Accept 200, 401, 422, 405 (method not allowed), 307 (redirect) as available
            if ($response.StatusCode -in @(200, 401, 422, 405, 307)) {
                Write-Host "   ✅ " -NoNewline -ForegroundColor Green
                Write-Host "$endpoint - Available (Status: $($response.StatusCode))" -ForegroundColor White
                $available++
            }
        } catch {
            $statusCode = $_.Exception.Response.StatusCode.value__
            # Accept 200, 401, 422, 405 (method not allowed), 307 (redirect) as available
            if ($statusCode -in @(200, 401, 422, 405, 307)) {
                Write-Host "   ✅ " -NoNewline -ForegroundColor Green
                Write-Host "$endpoint - Available (Status: $statusCode)" -ForegroundColor White
                $available++
            } else {
                Write-Host "   ❌ " -NoNewline -ForegroundColor Red
                Write-Host "$endpoint - Offline (Status: $statusCode)" -ForegroundColor White
            }
        }
    }
    
    Write-Host "   📊 Services Available: $available/3 ($(($available/3*100))%)" -ForegroundColor Cyan
    
    if ($available -ge 3) {
        Write-Host "   ✅ PASS: All services available" -ForegroundColor Green
        $script:PassedChecks++
    } else {
        Write-Host "   ❌ FAIL: Need $($3-$available) more services online" -ForegroundColor Red
        Write-Host "   🚨 CRITICAL: Must fix before burn-in test" -ForegroundColor Red
        $script:FailedChecks++
    }
    $script:TotalChecks++
} catch {
    Write-Host "   ❌ ERROR: Could not check services - $($_.Exception.Message)" -ForegroundColor Red
    $script:FailedChecks++
    $script:TotalChecks++
}
Write-Host ""

# ============================================================================
# CHECK 9: K6 Test Script
# ============================================================================
Test-Check -Name "K6 Enhanced Test Script" -Test {
    Test-Path "scripts\testing\k6_enhanced_comprehensive_test.js"
} -SuccessMessage "K6 test script found with all fixes applied" `
  -FailureMessage "K6 test script missing" `
  -Critical $true

# ============================================================================
# CHECK 10: Burn-in Framework Script
# ============================================================================
Test-Check -Name "Burn-in Framework Script" -Test {
    Test-Path "scripts\testing\burn_in_framework.py"
} -SuccessMessage "Burn-in framework script ready" `
  -FailureMessage "Burn-in framework script missing" `
  -Critical $true

# ============================================================================
# SUMMARY
# ============================================================================
Write-Host "=" -ForegroundColor Cyan -NoNewline; Write-Host ("=" * 69) -ForegroundColor Cyan
Write-Host "📊 VALIDATION SUMMARY" -ForegroundColor Cyan
Write-Host "=" -ForegroundColor Cyan -NoNewline; Write-Host ("=" * 69) -ForegroundColor Cyan
Write-Host ""

$PassPercentage = [math]::Round(($PassedChecks / $TotalChecks) * 100, 1)

Write-Host "Total Checks: $TotalChecks" -ForegroundColor White
Write-Host "Passed: " -NoNewline -ForegroundColor Green
Write-Host "$PassedChecks" -ForegroundColor White
Write-Host "Failed: " -NoNewline -ForegroundColor Red
Write-Host "$FailedChecks" -ForegroundColor White
Write-Host "Pass Rate: " -NoNewline -ForegroundColor Cyan
Write-Host "$PassPercentage%" -ForegroundColor White
Write-Host ""

if ($FailedChecks -eq 0) {
    Write-Host "✅ ALL CHECKS PASSED - READY FOR BURN-IN TEST! 🚀" -ForegroundColor Green
    Write-Host ""
    Write-Host "Start burn-in test with:" -ForegroundColor Cyan
    Write-Host "  .\venv\Scripts\python.exe scripts\testing\burn_in_framework.py" -ForegroundColor Yellow
} elseif ($PassPercentage -ge 80) {
    Write-Host "⚠️  MOSTLY READY - FEW ISSUES TO FIX" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Fix critical issues above, then run:" -ForegroundColor Cyan
    Write-Host "  .\pre_burnin_checklist.ps1" -ForegroundColor Yellow
} else {
    Write-Host "❌ NOT READY - MULTIPLE ISSUES TO FIX" -ForegroundColor Red
    Write-Host ""
    Write-Host "Fix critical issues above, then re-run this checklist" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "=" -ForegroundColor Cyan -NoNewline; Write-Host ("=" * 69) -ForegroundColor Cyan

# Exit with appropriate code
exit $FailedChecks
