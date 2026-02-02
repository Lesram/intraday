<#
.SYNOPSIS
    Run ML comprehensive tests one-by-one with timeout and coverage.
    Follows the non-stalling protocol with progress updates.
    
    RUN FROM PROJECT ROOT: powershell -File tests\run_ml_tests.ps1
#>
param(
    [int]$TimeoutSeconds = 120,  # 2 minutes per file (ML tests can be slower)
    [switch]$WithCoverage,
    [switch]$Fast  # Skip coverage for speed
)

$ErrorActionPreference = "Continue"
$startTime = Get-Date

Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host "ML COMPREHENSIVE TESTS - ONE BY ONE" -ForegroundColor Cyan
Write-Host "Timeout: $TimeoutSeconds seconds per file" -ForegroundColor Cyan
Write-Host "Coverage: $(-not $Fast -and $WithCoverage)" -ForegroundColor Cyan
Write-Host "Started: $startTime" -ForegroundColor Cyan
Write-Host "=" * 70 -ForegroundColor Cyan

# ML comprehensive test files (19 files total)
$mlTestFiles = @(
    # === tests/unit/ - Core comprehensive tests (17 files) ===
    "tests/unit/test_ml_model_manager_comprehensive.py",
    "tests/unit/test_ml_training_comprehensive.py",
    "tests/unit/test_ml_validation_comprehensive.py",
    "tests/unit/test_ml_prediction_service_comprehensive.py",
    "tests/unit/test_ml_lifecycle_scheduler_comprehensive.py",
    "tests/unit/test_ml_drift_comprehensive.py",
    "tests/unit/test_ml_lifecycle_comprehensive.py",
    "tests/unit/test_ml_data_processing_comprehensive.py",
    "tests/unit/test_ml_feature_engineering_comprehensive.py",
    "tests/unit/test_ml_ensemble_framework_comprehensive.py",
    "tests/unit/test_ml_pipeline_comprehensive.py",
    "tests/unit/test_ml_model_management_comprehensive.py",
    "tests/unit/test_ml_model_selection_comprehensive.py",
    "tests/unit/test_ml_monitoring_comprehensive.py",
    "tests/unit/test_ml_active_model_pointer_comprehensive.py",
    "tests/unit/test_ml_mlops_modules.py",
    # === tests/ root - Additional ML tests (3 files) ===
    "tests/test_ml_lifecycle_api.py",
    "tests/test_ml_data_processing_comprehensive.py",
    "tests/test_ml_pipeline_comprehensive.py"
)

# Verify files exist
$existingFiles = @()
foreach ($file in $mlTestFiles) {
    if (Test-Path $file) {
        $existingFiles += $file
    } else {
        Write-Host "WARNING: File not found: $file" -ForegroundColor Yellow
    }
}

$total = $existingFiles.Count
$passed = 0
$failed = 0
$timedOut = 0
$totalTestCount = 0
$stallingFiles = @()
$failedFiles = @()
$results = @()

Write-Host "`nFound $total ML test files to run`n" -ForegroundColor Yellow

$counter = 0
foreach ($file in $existingFiles) {
    $counter++
    
    Write-Host "`n[$counter/$total] Testing: $file" -ForegroundColor White
    Write-Host "   Started: $(Get-Date -Format 'HH:mm:ss')" -ForegroundColor Gray
    
    $fileStart = Get-Date
    
    # Build pytest command
    if ($WithCoverage -and -not $Fast) {
        $pytestArgs = "$file -v --tb=short --cov=backend.ml --cov-report=term-missing:skip-covered"
    } else {
        $pytestArgs = "$file -v --tb=short"
    }
    
    # Run pytest with timeout
    $job = Start-Job -ScriptBlock {
        param($filePath, $args)
        Set-Location $using:PWD
        $output = & python -m pytest $filePath -v --tb=short 2>&1
        return @{
            Output = $output
            ExitCode = $LASTEXITCODE
        }
    } -ArgumentList $file
    
    # Progress indicator while waiting
    $waited = 0
    $progressInterval = 10
    while ($job.State -eq "Running" -and $waited -lt $TimeoutSeconds) {
        Start-Sleep -Seconds 1
        $waited++
        if ($waited % $progressInterval -eq 0) {
            Write-Host "   ... $waited seconds elapsed" -ForegroundColor Gray
        }
    }
    
    # Check if completed or timed out
    if ($job.State -eq "Running") {
        # Timeout occurred
        Stop-Job $job
        Remove-Job $job -Force
        $timedOut++
        $stallingFiles += $file
        Write-Host "   ⏰ TIMEOUT after $TimeoutSeconds seconds!" -ForegroundColor Red
        $results += @{
            File = $file
            Status = "TIMEOUT"
            Tests = 0
            Duration = $TimeoutSeconds
        }
    }
    else {
        $jobResult = Receive-Job $job
        Remove-Job $job -Force
        
        $duration = [math]::Round(((Get-Date) - $fileStart).TotalSeconds, 1)
        $outputText = $jobResult.Output -join "`n"
        
        # Parse test count from output
        $testMatch = [regex]::Match($outputText, "(\d+) passed")
        $testCount = if ($testMatch.Success) { [int]$testMatch.Groups[1].Value } else { 0 }
        $totalTestCount += $testCount
        
        $skipMatch = [regex]::Match($outputText, "(\d+) skipped")
        $skipCount = if ($skipMatch.Success) { [int]$skipMatch.Groups[1].Value } else { 0 }
        
        # Check status using pytest summary line format
        # Look for actual failure count in summary line like "1 failed, 10 passed"
        $failMatch = [regex]::Match($outputText, "(\d+) failed")
        $failCount = if ($failMatch.Success) { [int]$failMatch.Groups[1].Value } else { 0 }
        
        if ($failCount -eq 0 -and $testCount -gt 0) {
            $passed++
            Write-Host "   ✅ PASSED: $testCount tests ($skipCount skipped) in ${duration}s" -ForegroundColor Green
            $results += @{
                File = $file
                Status = "PASSED"
                Tests = $testCount
                Skipped = $skipCount
                Duration = $duration
            }
        }
        elseif ($outputText -match "no tests ran") {
            $passed++
            Write-Host "   ⚪ SKIP (no tests) in ${duration}s" -ForegroundColor Gray
            $results += @{
                File = $file
                Status = "SKIPPED"
                Tests = 0
                Duration = $duration
            }
        }
        else {
            $failed++
            $failedFiles += $file
            Write-Host "   ❌ FAILED: $failCount failures in ${duration}s" -ForegroundColor Yellow
            # Show brief error
            $errorLines = $outputText -split "`n" | Where-Object { $_ -match "^FAILED |^E   |AssertionError" } | Select-Object -First 3
            foreach ($line in $errorLines) {
                Write-Host "      $line" -ForegroundColor Red
            }
            $results += @{
                File = $file
                Status = "FAILED"
                Tests = $testCount
                Failures = $failCount
                Duration = $duration
            }
        }
    }
}

# Summary
$totalDuration = [math]::Round(((Get-Date) - $startTime).TotalSeconds, 1)

Write-Host "`n" -NoNewline
Write-Host ("=" * 70) -ForegroundColor Cyan
Write-Host "ML TESTS SUMMARY" -ForegroundColor Cyan
Write-Host ("=" * 70) -ForegroundColor Cyan

Write-Host "`nFiles:" -ForegroundColor White
Write-Host "  Total:     $total" -ForegroundColor White
Write-Host "  Passed:    $passed" -ForegroundColor Green
Write-Host "  Failed:    $failed" -ForegroundColor $(if ($failed -gt 0) { "Yellow" } else { "Green" })
Write-Host "  Timed Out: $timedOut" -ForegroundColor $(if ($timedOut -gt 0) { "Red" } else { "Green" })

Write-Host "`nTests:" -ForegroundColor White
Write-Host "  Total Tests Run: $totalTestCount" -ForegroundColor Cyan

Write-Host "`nDuration: ${totalDuration}s ($([math]::Round($totalDuration/60, 1)) min)" -ForegroundColor White

if ($stallingFiles.Count -gt 0) {
    Write-Host "`n⚠️  STALLING FILES:" -ForegroundColor Red
    foreach ($f in $stallingFiles) {
        Write-Host "  - $f" -ForegroundColor Red
    }
}

if ($failedFiles.Count -gt 0) {
    Write-Host "`n❌ FAILED FILES:" -ForegroundColor Yellow
    foreach ($f in $failedFiles) {
        Write-Host "  - $f" -ForegroundColor Yellow
    }
}

Write-Host "`n" -NoNewline
Write-Host ("=" * 70) -ForegroundColor Cyan

# Exit with appropriate code
if ($timedOut -gt 0) {
    Write-Host "EXIT CODE: 2 (timeouts detected)" -ForegroundColor Red
    exit 2
} elseif ($failed -gt 0) {
    Write-Host "EXIT CODE: 1 (failures detected)" -ForegroundColor Yellow
    exit 1
} else {
    Write-Host "EXIT CODE: 0 (all passed)" -ForegroundColor Green
    exit 0
}
