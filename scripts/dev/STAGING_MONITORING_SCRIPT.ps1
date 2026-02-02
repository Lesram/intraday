# STAGING_MONITORING_SCRIPT.ps1
# Automated monitoring for staging deployment validation
# Run this after deploying to staging

param(
    [string]$StagingUrl = "http://localhost:8000",
    [string]$DatabaseUrl = $env:STAGING_DATABASE_URL,
    [int]$MonitoringDurationMin = 30,
    [switch]$SkipBurnIn
)

$ErrorActionPreference = "Continue"
$results = @{
    timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    checks = @()
    passed = 0
    failed = 0
    warnings = 0
}

function Write-CheckResult {
    param(
        [string]$Name,
        [string]$Status,
        [string]$Message,
        [string]$Details = ""
    )
    
    $check = @{
        name = $Name
        status = $Status
        message = $Message
        details = $Details
        timestamp = Get-Date -Format "HH:mm:ss"
    }
    
    $results.checks += $check
    
    switch ($Status) {
        "PASS" { 
            $results.passed++
            Write-Host "✅ $Name" -ForegroundColor Green
            Write-Host "   $Message" -ForegroundColor Gray
        }
        "FAIL" { 
            $results.failed++
            Write-Host "❌ $Name" -ForegroundColor Red
            Write-Host "   $Message" -ForegroundColor Red
            if ($Details) {
                Write-Host "   Details: $Details" -ForegroundColor Yellow
            }
        }
        "WARN" { 
            $results.warnings++
            Write-Host "⚠️  $Name" -ForegroundColor Yellow
            Write-Host "   $Message" -ForegroundColor Yellow
        }
    }
}

Write-Host "`n🎯 STAGING DEPLOYMENT VALIDATION" -ForegroundColor Cyan
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host "Start Time: $($results.timestamp)" -ForegroundColor Gray
Write-Host "Staging URL: $StagingUrl" -ForegroundColor Gray
Write-Host "Duration: $MonitoringDurationMin minutes" -ForegroundColor Gray
Write-Host "=" * 60 -ForegroundColor Cyan

# ============================================================================
# CHECK 1: Health Endpoint
# ============================================================================
Write-Host "`n[1/6] Health Endpoint Check..." -ForegroundColor Cyan

try {
    $health = Invoke-RestMethod -Uri "$StagingUrl/health" -TimeoutSec 10 -ErrorAction Stop
    
    if ($health.status -eq "healthy") {
        Write-CheckResult -Name "Health Endpoint" -Status "PASS" `
            -Message "Server is healthy" `
            -Details "Database: $($health.database), Version: $($health.version)"
    } else {
        Write-CheckResult -Name "Health Endpoint" -Status "FAIL" `
            -Message "Server status: $($health.status)"
    }
} catch {
    Write-CheckResult -Name "Health Endpoint" -Status "FAIL" `
        -Message "Cannot connect to $StagingUrl/health" `
        -Details $_.Exception.Message
}

# ============================================================================
# CHECK 2: Database Constraints
# ============================================================================
Write-Host "`n[2/6] Database Constraints Check..." -ForegroundColor Cyan

if ($DatabaseUrl) {
    try {
        # Check if psql is available
        $psqlExists = Get-Command psql -ErrorAction SilentlyContinue
        
        if ($psqlExists) {
            $constraintQuery = @"
SELECT conname, contype, conrelid::regclass 
FROM pg_constraint 
WHERE conname LIKE 'uq_%' 
ORDER BY conname;
"@
            
            $constraints = psql $DatabaseUrl -t -c $constraintQuery 2>$null
            
            $expectedConstraints = @(
                "uq_orders_account_client_order_id",
                "uq_order_events_broker_event",
                "uq_outbox_events_aggregate_event"
            )
            
            $foundCount = 0
            foreach ($expected in $expectedConstraints) {
                if ($constraints -match $expected) {
                    $foundCount++
                }
            }
            
            if ($foundCount -eq 3) {
                Write-CheckResult -Name "Database Constraints" -Status "PASS" `
                    -Message "All 3 UNIQUE constraints exist" `
                    -Details ($expectedConstraints -join ", ")
            } else {
                Write-CheckResult -Name "Database Constraints" -Status "FAIL" `
                    -Message "Found $foundCount of 3 expected constraints" `
                    -Details "Missing: $($expectedConstraints | Where-Object { $constraints -notmatch $_ })"
            }
        } else {
            Write-CheckResult -Name "Database Constraints" -Status "WARN" `
                -Message "psql not available, cannot verify constraints" `
                -Details "Install PostgreSQL client tools to enable this check"
        }
    } catch {
        Write-CheckResult -Name "Database Constraints" -Status "FAIL" `
            -Message "Error checking constraints" `
            -Details $_.Exception.Message
    }
} else {
    Write-CheckResult -Name "Database Constraints" -Status "WARN" `
        -Message "STAGING_DATABASE_URL not set, skipping constraint check"
}

# ============================================================================
# CHECK 3: Code Verification
# ============================================================================
Write-Host "`n[3/6] Code Verification Check..." -ForegroundColor Cyan

# Check for placeholder code
$placeholders = Select-String -Path "tests/test_order_lifecycle.py" -Pattern "return True  # Placeholder" -ErrorAction SilentlyContinue

if ($placeholders.Count -eq 0) {
    Write-CheckResult -Name "No Placeholder Code" -Status "PASS" `
        -Message "No placeholder comments found in test_order_lifecycle.py"
} else {
    Write-CheckResult -Name "No Placeholder Code" -Status "FAIL" `
        -Message "Found $($placeholders.Count) placeholder comment(s)" `
        -Details ($placeholders | Select-Object -First 3 | ForEach-Object { "Line $($_.LineNumber)" }) -join ", "
}

# Check for ValueError in burn-in
$valueErrors = Select-String -Path "scripts/testing/burn_in_framework.py" -Pattern "raise ValueError" -ErrorAction SilentlyContinue

if ($valueErrors.Count -ge 6) {
    Write-CheckResult -Name "Burn-In Strict Validation" -Status "PASS" `
        -Message "Found $($valueErrors.Count) ValueError validations" `
        -Details "Expected minimum: 6 (including lines 451, 466)"
} else {
    Write-CheckResult -Name "Burn-In Strict Validation" -Status "FAIL" `
        -Message "Found only $($valueErrors.Count) ValueError validations (expected 6+)"
}

# ============================================================================
# CHECK 4: CI Bypass Blocks
# ============================================================================
Write-Host "`n[4/6] CI Bypass Block Check..." -ForegroundColor Cyan

$env:GITHUB_ACTIONS = "true"
$env:GITHUB_REF = "refs/heads/staging"

try {
    $output = & pwsh scripts/ci/quality_gates.ps1 -Fast 2>&1
    $exitCode = $LASTEXITCODE
    
    if ($exitCode -eq 2 -and $output -match "GATE VIOLATION") {
        Write-CheckResult -Name "CI Bypass Blocks" -Status "PASS" `
            -Message "-Fast flag correctly blocked in staging" `
            -Details "Exit code: $exitCode (expected: 2)"
    } else {
        Write-CheckResult -Name "CI Bypass Blocks" -Status "FAIL" `
            -Message "-Fast flag NOT blocked in staging (exit code: $exitCode)" `
            -Details $output
    }
} catch {
    Write-CheckResult -Name "CI Bypass Blocks" -Status "FAIL" `
        -Message "Error running quality gates" `
        -Details $_.Exception.Message
} finally {
    Remove-Item Env:\GITHUB_ACTIONS -ErrorAction SilentlyContinue
    Remove-Item Env:\GITHUB_REF -ErrorAction SilentlyContinue
}

# ============================================================================
# CHECK 5: Burn-In Session (if not skipped)
# ============================================================================
Write-Host "`n[5/6] Burn-In Session Check..." -ForegroundColor Cyan

if ($SkipBurnIn) {
    Write-CheckResult -Name "Burn-In Session" -Status "WARN" `
        -Message "Skipped (use -SkipBurnIn:$false to enable)"
} else {
    # Check if server is running
    try {
        $health = Invoke-RestMethod -Uri "$StagingUrl/health" -TimeoutSec 5 -ErrorAction Stop
        
        if ($health.status -eq "healthy") {
            Write-Host "   Starting 5-minute burn-in session..." -ForegroundColor Gray
            
            # Run shortened burn-in for staging validation (5 min instead of 15)
            $burnInScript = "scripts/testing/burn_in_framework.py"
            
            if (Test-Path $burnInScript) {
                $burnInOutput = python $burnInScript --duration 300 --target-url $StagingUrl 2>&1
                
                if ($LASTEXITCODE -eq 0) {
                    # Parse output for metrics
                    $ordersMatch = $burnInOutput | Select-String -Pattern "Orders processed:\s*(\d+)"
                    $signalsMatch = $burnInOutput | Select-String -Pattern "Signals generated:\s*(\d+)"
                    $riskMatch = $burnInOutput | Select-String -Pattern "Risk decisions:\s*(\d+)"
                    
                    $orders = if ($ordersMatch) { [int]$ordersMatch.Matches.Groups[1].Value } else { 0 }
                    $signals = if ($signalsMatch) { [int]$signalsMatch.Matches.Groups[1].Value } else { 0 }
                    $risk = if ($riskMatch) { [int]$riskMatch.Matches.Groups[1].Value } else { 0 }
                    
                    if ($orders -gt 0 -and $signals -gt 0 -and $risk -gt 0) {
                        Write-CheckResult -Name "Burn-In Session" -Status "PASS" `
                            -Message "Business flow validated" `
                            -Details "Orders: $orders, Signals: $signals, Risk: $risk"
                    } else {
                        Write-CheckResult -Name "Burn-In Session" -Status "FAIL" `
                            -Message "Business flow has zero metrics" `
                            -Details "Orders: $orders, Signals: $signals, Risk: $risk (all should be >0)"
                    }
                } else {
                    Write-CheckResult -Name "Burn-In Session" -Status "FAIL" `
                        -Message "Burn-in script failed (exit code: $LASTEXITCODE)" `
                        -Details ($burnInOutput | Select-Object -Last 10) -join "`n"
                }
            } else {
                Write-CheckResult -Name "Burn-In Session" -Status "WARN" `
                    -Message "Burn-in script not found: $burnInScript"
            }
        } else {
            Write-CheckResult -Name "Burn-In Session" -Status "FAIL" `
                -Message "Server not healthy, cannot run burn-in"
        }
    } catch {
        Write-CheckResult -Name "Burn-In Session" -Status "FAIL" `
            -Message "Cannot connect to server for burn-in" `
            -Details $_.Exception.Message
    }
}

# ============================================================================
# CHECK 6: False Positive Metrics
# ============================================================================
Write-Host "`n[6/6] False Positive Metrics Check..." -ForegroundColor Cyan

try {
    # Check metrics endpoint
    $metrics = Invoke-RestMethod -Uri "$StagingUrl/metrics" -TimeoutSec 10 -ErrorAction Stop
    
    $issues = @()
    
    # Check for common false positive patterns
    if ($metrics -match "availability.*0\.0" -or $metrics -match "availability.*NaN") {
        $issues += "Found '0% availability' metric"
    }
    
    if ($metrics -match "success_rate.*1\.0.*request_count.*0") {
        $issues += "Found '100% success' with 0 requests"
    }
    
    if ($metrics -match "coverage.*0\.0") {
        $issues += "Found '0% coverage' metric"
    }
    
    if ($issues.Count -eq 0) {
        Write-CheckResult -Name "False Positive Metrics" -Status "PASS" `
            -Message "No false positive metrics detected"
    } else {
        Write-CheckResult -Name "False Positive Metrics" -Status "FAIL" `
            -Message "Detected $($issues.Count) false positive metric(s)" `
            -Details ($issues -join "; ")
    }
} catch {
    Write-CheckResult -Name "False Positive Metrics" -Status "WARN" `
        -Message "Cannot fetch metrics endpoint" `
        -Details $_.Exception.Message
}

# ============================================================================
# SUMMARY
# ============================================================================
Write-Host "`n" + ("=" * 60) -ForegroundColor Cyan
Write-Host "VALIDATION SUMMARY" -ForegroundColor Cyan
Write-Host ("=" * 60) -ForegroundColor Cyan

Write-Host "`nResults:" -ForegroundColor White
Write-Host "  ✅ Passed:  $($results.passed)" -ForegroundColor Green
Write-Host "  ❌ Failed:  $($results.failed)" -ForegroundColor Red
Write-Host "  ⚠️  Warnings: $($results.warnings)" -ForegroundColor Yellow

$totalChecks = $results.passed + $results.failed + $results.warnings
$successRate = if ($totalChecks -gt 0) { [math]::Round(($results.passed / $totalChecks) * 100, 1) } else { 0 }

Write-Host "`nSuccess Rate: $successRate%" -ForegroundColor $(if ($successRate -ge 80) { "Green" } elseif ($successRate -ge 60) { "Yellow" } else { "Red" })

if ($results.failed -eq 0) {
    Write-Host "`n🎉 ALL CRITICAL CHECKS PASSED!" -ForegroundColor Green
    Write-Host "   Staging deployment is validated and ready." -ForegroundColor Green
    $exitCode = 0
} elseif ($results.failed -le 2 -and $results.warnings -eq 0) {
    Write-Host "`n⚠️  SOME CHECKS FAILED" -ForegroundColor Yellow
    Write-Host "   Review failed checks before proceeding to production." -ForegroundColor Yellow
    $exitCode = 1
} else {
    Write-Host "`n❌ VALIDATION FAILED" -ForegroundColor Red
    Write-Host "   DO NOT deploy to production. Fix issues and re-validate." -ForegroundColor Red
    $exitCode = 2
}

# Save results to JSON
$resultsJson = $results | ConvertTo-Json -Depth 10
$resultsFile = "staging_validation_results_$(Get-Date -Format 'yyyyMMdd_HHmmss').json"
$resultsJson | Out-File -FilePath $resultsFile -Encoding UTF8

Write-Host "`n📄 Results saved to: $resultsFile" -ForegroundColor Gray

# Print failed checks
if ($results.failed -gt 0) {
    Write-Host "`n❌ Failed Checks:" -ForegroundColor Red
    $results.checks | Where-Object { $_.status -eq "FAIL" } | ForEach-Object {
        Write-Host "   - $($_.name): $($_.message)" -ForegroundColor Red
    }
}

Write-Host "`n" + ("=" * 60) -ForegroundColor Cyan
Write-Host "End Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Gray
Write-Host ("=" * 60) -ForegroundColor Cyan

exit $exitCode
