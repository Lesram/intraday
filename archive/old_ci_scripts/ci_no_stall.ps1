#!/usr/bin/env pwsh
# CI Sequential Runner with Respx Management
# This script temporarily uninstalls respx to prevent pytest plugin conflicts,
# runs tests in light mode, then reinstalls respx.

param(
    [switch]$WithCoverageJson,
    [switch]$DryRun
)

Write-Host "CI Sequential Runner - Light Mode with Respx Management" -ForegroundColor Cyan
Write-Host "Current Time: $(Get-Date)" -ForegroundColor Gray

# Create output directories
$reportDir = "test_reports"
$logDir = "$reportDir/logs"
if (!(Test-Path $reportDir)) { New-Item -ItemType Directory -Path $reportDir -Force | Out-Null }
if (!(Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }

try {
    # Step 1: Temporarily uninstall respx
    Write-Host "Step 1: Temporarily removing respx plugin..." -ForegroundColor Yellow
    $respxCheck = pip list | Select-String "respx"
    if ($respxCheck) {
        Write-Host "Uninstalling respx to prevent plugin conflicts..."
        pip uninstall respx -y | Out-Host
        $respxWasInstalled = $true
    } else {
        Write-Host "Respx not installed, continuing..."
        $respxWasInstalled = $false
    }

    # Step 2: Clear coverage data
    Write-Host "Step 2: Clearing coverage data..." -ForegroundColor Yellow
    if (Get-Command coverage -ErrorAction SilentlyContinue) {
        coverage erase
        Write-Host "Coverage data cleared."
    }

    # Step 3: Run tests in light mode
    Write-Host "Step 3: Running tests in light mode..." -ForegroundColor Yellow
    
    # Get all test files (full suite)
    $testFiles = Get-ChildItem -Path "tests" -Recurse -Include "test_*.py" | Where-Object { 
        $_.FullName -notmatch "\\__pycache__\\" 
    } | ForEach-Object { $_.FullName.Replace("$PWD\", "").Replace("\", "/") }
    
    Write-Host "Found $($testFiles.Count) test files (full suite)"
    
    $successCount = 0
    $failCount = 0
    $testResults = @()

    foreach ($testFile in $testFiles) {
        $safeName = $testFile -replace '[\\/:*?"<>|]', '_'
        $logFile = "$logDir/$safeName.log"
        
        Write-Host "Running: $testFile" -ForegroundColor Cyan
        
        # Run test with timeout
        $startTime = Get-Date
        try {
            if ($WithCoverageJson) {
                $output = coverage run --parallel-mode --source=backend -m pytest "$testFile" -v --tb=short --timeout=60 2>&1
            } else {
                $output = python -m pytest "$testFile" -v --tb=short --timeout=60 2>&1
            }
            
            $exitCode = $LASTEXITCODE
            $duration = (Get-Date) - $startTime
            
            # Log the output
            $output | Out-File -FilePath $logFile -Encoding utf8
            
            if ($exitCode -eq 0) {
                Write-Host "  PASS ($([math]::Round($duration.TotalSeconds, 1))s)" -ForegroundColor Green
                $successCount++
            } else {
                Write-Host "  FAIL ($([math]::Round($duration.TotalSeconds, 1))s) - Exit Code: $exitCode" -ForegroundColor Red
                $failCount++
                
                # Show last few lines of output for failed tests
                if ($output) {
                    $output | Select-Object -Last 3 | ForEach-Object { Write-Host "    $_" -ForegroundColor Yellow }
                }
            }
        }
        catch {
            $duration = (Get-Date) - $startTime
            Write-Host "  ERROR ($([math]::Round($duration.TotalSeconds, 1))s): $_" -ForegroundColor Red
            "ERROR: $_" | Out-File -FilePath $logFile -Encoding utf8
            $failCount++
        }
    }

    # Step 4: Combine coverage if requested
    if ($WithCoverageJson) {
        Write-Host "Step 4: Combining coverage data..." -ForegroundColor Yellow
        if (Get-Command coverage -ErrorAction SilentlyContinue) {
            coverage combine
            coverage json -o "$reportDir/coverage.json"
            coverage xml -o "$reportDir/coverage.xml"
            Write-Host "Coverage reports generated: coverage.json, coverage.xml"
        }
    }

    # Step 5: Generate summary
    Write-Host "Step 5: Test Summary" -ForegroundColor Yellow
    Write-Host "======================"
    Write-Host "Total Tests: $($testFiles.Count)"
    Write-Host "Passed: $successCount" -ForegroundColor Green
    Write-Host "Failed: $failCount" -ForegroundColor $(if ($failCount -gt 0) { "Red" } else { "Green" })
    
    $totalDuration = ($testResults | Measure-Object -Property Duration -Sum).Sum
    Write-Host "Total Duration: $([math]::Round($totalDuration, 1)) seconds"

    # Step 6: Reinstall respx if it was installed
    if ($respxWasInstalled) {
        Write-Host "Step 6: Reinstalling respx..." -ForegroundColor Yellow
        pip install respx | Out-Host
        Write-Host "Respx reinstalled."
    }

    # Exit with appropriate code
    if ($failCount -gt 0) {
        Write-Host "Some tests failed. Check logs in $logDir for details." -ForegroundColor Red
        exit 1
    } else {
        Write-Host "All tests passed!" -ForegroundColor Green
        exit 0
    }

} catch {
    Write-Host "Script error: $_" -ForegroundColor Red
    
    # Ensure respx is reinstalled even if script fails
    if ($respxWasInstalled) {
        Write-Host "Attempting to reinstall respx after error..."
        pip install respx | Out-Host
    }
    
    exit 1
}
