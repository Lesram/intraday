<#
.SYNOPSIS
    Run Alpaca integration tests one-by-one with timeout and coverage.
    Follows the non-stalling protocol with progress updates.
    
    RUN FROM PROJECT ROOT: powershell -File tests\run_alpaca_tests.ps1
#>
param(
    [int]$TimeoutSeconds = 120,  # 2 minutes per file
    [switch]$WithCoverage,
    [switch]$Fast  # Skip coverage for speed
)

$ErrorActionPreference = "Continue"
$startTime = Get-Date

Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host "ALPACA INTEGRATION TESTS - PHASE 3" -ForegroundColor Cyan
Write-Host "Timeout: $TimeoutSeconds seconds per file" -ForegroundColor Cyan
Write-Host "Coverage: $(-not $Fast -and $WithCoverage)" -ForegroundColor Cyan
Write-Host "Started: $startTime" -ForegroundColor Cyan
Write-Host "=" * 70 -ForegroundColor Cyan

# Alpaca integration test files (5 files total)
$alpacaTestFiles = @(
    # === Comprehensive Alpaca tests ===
    "tests/unit/test_alpaca_stream_comprehensive.py",
    "tests/unit/test_alpaca_data_comprehensive.py",
    "tests/unit/test_alpaca_outbox_comprehensive.py",
    "tests/unit/test_alpaca_market_data_stream_comprehensive.py",
    "tests/unit/test_alpaca_stream_production_comprehensive.py"
)

# Verify files exist
$existingFiles = @()
foreach ($file in $alpacaTestFiles) {
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

Write-Host "`nFound $total Alpaca test files to run`n" -ForegroundColor Yellow

$counter = 0
foreach ($file in $existingFiles) {
    $counter++
    
    Write-Host "`n[$counter/$total] Testing: $file" -ForegroundColor White
    Write-Host "   Started: $(Get-Date -Format 'HH:mm:ss')" -ForegroundColor Gray
    
    $fileStart = Get-Date
    
    # Build pytest command
    if ($WithCoverage -and -not $Fast) {
        $pytestArgs = @(
            "-m", "pytest",
            "-v",
            "--timeout=60",
            "--cov=backend.integrations",
            "--cov-report=term-missing:skip-covered",
            $file
        )
    } else {
        $pytestArgs = @(
            "-m", "pytest",
            "-v",
            "--timeout=60",
            "--tb=short",
            $file
        )
    }
    
    # Run with timeout
    $process = Start-Process -FilePath "python" -ArgumentList $pytestArgs -PassThru -NoNewWindow -RedirectStandardOutput "test_stdout.tmp" -RedirectStandardError "test_stderr.tmp"
    
    $completed = $process.WaitForExit($TimeoutSeconds * 1000)
    
    $fileEnd = Get-Date
    $duration = ($fileEnd - $fileStart).TotalSeconds
    
    if (-not $completed) {
        # Timeout - kill process
        $process.Kill()
        $timedOut++
        $stallingFiles += $file
        
        Write-Host "   TIMEOUT after $TimeoutSeconds seconds!" -ForegroundColor Red
        $results += @{
            File = $file
            Status = "TIMEOUT"
            Duration = $duration
            Tests = 0
        }
        continue
    }
    
    # Get output
    $stdout = Get-Content "test_stdout.tmp" -Raw -ErrorAction SilentlyContinue
    $stderr = Get-Content "test_stderr.tmp" -Raw -ErrorAction SilentlyContinue
    
    # Parse test count from output
    $testCount = 0
    if ($stdout -match "(\d+) passed") {
        $testCount = [int]$Matches[1]
    }
    $totalTestCount += $testCount
    
    if ($process.ExitCode -eq 0) {
        $passed++
        Write-Host "   PASSED ($testCount tests in $([math]::Round($duration, 1))s)" -ForegroundColor Green
        $results += @{
            File = $file
            Status = "PASSED"
            Duration = $duration
            Tests = $testCount
        }
    } else {
        $failed++
        $failedFiles += $file
        Write-Host "   FAILED ($testCount tests in $([math]::Round($duration, 1))s)" -ForegroundColor Red
        
        # Show failure details
        if ($stderr) {
            Write-Host "   Error: $($stderr.Substring(0, [Math]::Min(200, $stderr.Length)))" -ForegroundColor Red
        }
        
        $results += @{
            File = $file
            Status = "FAILED"
            Duration = $duration
            Tests = $testCount
        }
    }
}

# Cleanup temp files
Remove-Item "test_stdout.tmp", "test_stderr.tmp" -Force -ErrorAction SilentlyContinue

# Summary
$endTime = Get-Date
$totalDuration = ($endTime - $startTime).TotalSeconds

Write-Host "`n" + "=" * 70 -ForegroundColor Cyan
Write-Host "PHASE 3 ALPACA TESTS SUMMARY" -ForegroundColor Cyan
Write-Host "=" * 70 -ForegroundColor Cyan

Write-Host "`nResults:" -ForegroundColor White
Write-Host "  Total files:  $total" -ForegroundColor White
Write-Host "  Passed:       $passed" -ForegroundColor Green
Write-Host "  Failed:       $failed" -ForegroundColor $(if ($failed -gt 0) { "Red" } else { "White" })
Write-Host "  Timed out:    $timedOut" -ForegroundColor $(if ($timedOut -gt 0) { "Red" } else { "White" })
Write-Host "  Total tests:  $totalTestCount" -ForegroundColor White
Write-Host "  Duration:     $([math]::Round($totalDuration, 1))s" -ForegroundColor White

if ($failedFiles.Count -gt 0) {
    Write-Host "`nFailed files:" -ForegroundColor Red
    foreach ($f in $failedFiles) {
        Write-Host "  - $f" -ForegroundColor Red
    }
}

if ($stallingFiles.Count -gt 0) {
    Write-Host "`nTimed out files:" -ForegroundColor Yellow
    foreach ($f in $stallingFiles) {
        Write-Host "  - $f" -ForegroundColor Yellow
    }
}

Write-Host "`n" + "=" * 70 -ForegroundColor Cyan

# Exit with appropriate code
if ($failed -gt 0 -or $timedOut -gt 0) {
    exit 1
} else {
    Write-Host "ALL PHASE 3 TESTS PASSED!" -ForegroundColor Green
    exit 0
}
