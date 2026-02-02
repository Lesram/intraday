<#
.SYNOPSIS
    Run each test file one-by-one with a 60-second timeout.
    Identifies stalling tests and logs results.
    
    RUN FROM PROJECT ROOT: powershell -File tests\test_one_by_one.ps1
#>
param(
    [int]$TimeoutSeconds = 60  # 60 seconds (fast discovery)
)

$ErrorActionPreference = "Continue"
$startTime = Get-Date

Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host "ALL TESTS ONE-BY-ONE WITH $TimeoutSeconds SECOND TIMEOUT" -ForegroundColor Cyan
Write-Host "Started: $startTime" -ForegroundColor Cyan
Write-Host "=" * 70 -ForegroundColor Cyan

# Get ALL test files from the consolidated tests directory
$testFiles = Get-ChildItem -Path "tests" -Recurse -Filter "test_*.py" -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notlike "*\__pycache__\*" } |
    Sort-Object FullName -Unique

$total = $testFiles.Count
$passed = 0
$failed = 0
$timedOut = 0
$stallingFiles = @()
$failedFiles = @()

Write-Host "`nFound $total test files to run`n" -ForegroundColor Yellow

$counter = 0
foreach ($file in $testFiles) {
    $counter++
    $relativePath = $file.FullName.Replace((Get-Location).Path + "\", "")
    
    Write-Host "[$counter/$total] Testing: $relativePath" -ForegroundColor White -NoNewline
    
    $fileStart = Get-Date
    
    # Run pytest with timeout
    $job = Start-Job -ScriptBlock {
        param($filePath)
        Set-Location $using:PWD
        & python -m pytest $filePath -q --tb=no -x 2>&1
        return $LASTEXITCODE
    } -ArgumentList $file.FullName
    
    # Wait for job with timeout
    $completed = Wait-Job $job -Timeout $TimeoutSeconds
    
    if ($null -eq $completed) {
        # Timeout occurred
        Stop-Job $job
        Remove-Job $job -Force
        $timedOut++
        $stallingFiles += @{
            File = $relativePath
            Duration = $TimeoutSeconds
            Reason = "TIMEOUT after $TimeoutSeconds seconds"
        }
        Write-Host " ⏰ TIMEOUT!" -ForegroundColor Red
        Write-Host "   >>> STALLING TEST DETECTED: $relativePath" -ForegroundColor Red
    }
    else {
        $output = Receive-Job $job
        $exitCode = $job.ChildJobs[0].JobStateInfo.Reason
        Remove-Job $job -Force
        
        $duration = ((Get-Date) - $fileStart).TotalSeconds
        
        # Check if passed or failed based on output
        $outputText = $output -join "`n"
        if ($outputText -match "passed" -and $outputText -notmatch "failed|error") {
            $passed++
            Write-Host " ✅ PASS ($([math]::Round($duration, 1))s)" -ForegroundColor Green
        }
        elseif ($outputText -match "no tests ran") {
            $passed++  # Empty file, counts as pass
            Write-Host " ⚪ SKIP (no tests) ($([math]::Round($duration, 1))s)" -ForegroundColor Gray
        }
        else {
            $failed++
            $failedFiles += @{
                File = $relativePath
                Duration = $duration
                Output = $outputText
            }
            Write-Host " ❌ FAIL ($([math]::Round($duration, 1))s)" -ForegroundColor Yellow
        }
    }
}

# Summary
$totalDuration = ((Get-Date) - $startTime).TotalMinutes

Write-Host "`n" + ("=" * 70) -ForegroundColor Cyan
Write-Host "SUMMARY" -ForegroundColor Cyan
Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host "Total files:    $total"
Write-Host "Passed:         $passed" -ForegroundColor Green
Write-Host "Failed:         $failed" -ForegroundColor Yellow
Write-Host "Timed out:      $timedOut" -ForegroundColor Red
Write-Host "Duration:       $([math]::Round($totalDuration, 2)) minutes"

if ($stallingFiles.Count -gt 0) {
    Write-Host "`n" + ("=" * 70) -ForegroundColor Red
    Write-Host "🚨 STALLING TESTS (TIMED OUT)" -ForegroundColor Red
    Write-Host "=" * 70 -ForegroundColor Red
    foreach ($stall in $stallingFiles) {
        Write-Host "  - $($stall.File)" -ForegroundColor Red
    }
}

if ($failedFiles.Count -gt 0) {
    Write-Host "`n" + ("=" * 70) -ForegroundColor Yellow
    Write-Host "❌ FAILED TESTS" -ForegroundColor Yellow
    Write-Host "=" * 70 -ForegroundColor Yellow
    foreach ($fail in $failedFiles) {
        Write-Host "  - $($fail.File) ($([math]::Round($fail.Duration, 1))s)" -ForegroundColor Yellow
    }
}

Write-Host "`nDone at $(Get-Date)" -ForegroundColor Cyan
