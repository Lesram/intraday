#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Stop All Running Tests
    
.DESCRIPTION
    Stops all K6 and burn-in test processes that might be running in the background.
    Useful when you need to clean up after stopping the server or before starting new tests.
    
.EXAMPLE
    .\stop_all_tests.ps1
#>

Write-Host "=" -ForegroundColor Cyan -NoNewline; Write-Host ("=" * 69) -ForegroundColor Cyan
Write-Host "🛑 STOPPING ALL TEST PROCESSES" -ForegroundColor Cyan
Write-Host "=" -ForegroundColor Cyan -NoNewline; Write-Host ("=" * 69) -ForegroundColor Cyan
Write-Host ""

$StoppedCount = 0

# Stop K6 processes
Write-Host "🔍 Checking for K6 processes..." -ForegroundColor Yellow
$k6Processes = Get-Process | Where-Object {$_.ProcessName -like "*k6*"} -ErrorAction SilentlyContinue

if ($k6Processes) {
    foreach ($proc in $k6Processes) {
        Write-Host "   🛑 Stopping K6 process (PID: $($proc.Id), Started: $($proc.StartTime))" -ForegroundColor Red
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        $StoppedCount++
    }
    Write-Host "   ✅ Stopped $($k6Processes.Count) K6 process(es)" -ForegroundColor Green
} else {
    Write-Host "   ✅ No K6 processes running" -ForegroundColor Green
}
Write-Host ""

# Stop Python test processes (burn-in, performance tests, etc.)
Write-Host "🔍 Checking for Python test processes..." -ForegroundColor Yellow
$pythonProcesses = Get-Process python* -ErrorAction SilentlyContinue

if ($pythonProcesses) {
    # Try to identify test-related Python processes
    foreach ($proc in $pythonProcesses) {
        try {
            # Get command line to check if it's a test
            $procInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $($proc.Id)" -ErrorAction SilentlyContinue
            $cmdLine = $procInfo.CommandLine
            
            # Check if it's running test scripts
            if ($cmdLine -match "burn_in|k6_performance|automated_promotion|test") {
                Write-Host "   🛑 Stopping Python test process (PID: $($proc.Id))" -ForegroundColor Red
                Write-Host "      Command: $($cmdLine.Substring(0, [Math]::Min(80, $cmdLine.Length)))..." -ForegroundColor Gray
                Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
                $StoppedCount++
            }
        } catch {
            # Skip if we can't get command line info
        }
    }
    
    if ($StoppedCount -gt ($k6Processes.Count)) {
        $pythonStopped = $StoppedCount - ($k6Processes.Count)
        Write-Host "   ✅ Stopped $pythonStopped Python test process(es)" -ForegroundColor Green
    } else {
        Write-Host "   ℹ️  Found Python processes but none appear to be test-related" -ForegroundColor Cyan
    }
} else {
    Write-Host "   ✅ No Python processes running" -ForegroundColor Green
}
Write-Host ""

# Check for any remaining test artifacts
Write-Host "🔍 Checking for active test artifacts..." -ForegroundColor Yellow

# Check if K6 is still writing summary files
$recentK6Files = Get-ChildItem -Path "test_results\burn_in" -Filter "k6-summary-*.json" -ErrorAction SilentlyContinue | 
    Where-Object { $_.LastWriteTime -gt (Get-Date).AddMinutes(-5) }

if ($recentK6Files) {
    Write-Host "   ⚠️  Found recent K6 summary files (last 5 minutes):" -ForegroundColor Yellow
    foreach ($file in $recentK6Files) {
        Write-Host "      - $($file.Name) (Modified: $($file.LastWriteTime))" -ForegroundColor Gray
    }
} else {
    Write-Host "   ✅ No recent test artifacts found" -ForegroundColor Green
}
Write-Host ""

# Summary
Write-Host "=" -ForegroundColor Cyan -NoNewline; Write-Host ("=" * 69) -ForegroundColor Cyan
Write-Host "📊 SUMMARY" -ForegroundColor Cyan
Write-Host "=" -ForegroundColor Cyan -NoNewline; Write-Host ("=" * 69) -ForegroundColor Cyan
Write-Host ""

if ($StoppedCount -gt 0) {
    Write-Host "✅ Stopped $StoppedCount test process(es)" -ForegroundColor Green
    Write-Host ""
    Write-Host "All test processes have been terminated." -ForegroundColor White
    Write-Host "You can now safely restart your server or run new tests." -ForegroundColor White
} else {
    Write-Host "✅ No test processes were running" -ForegroundColor Green
    Write-Host ""
    Write-Host "System is clean - no active tests found." -ForegroundColor White
}

Write-Host ""
Write-Host "=" -ForegroundColor Cyan -NoNewline; Write-Host ("=" * 69) -ForegroundColor Cyan
