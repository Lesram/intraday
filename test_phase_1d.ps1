# Test Phase 1D Invoke-TestFile function
function Invoke-TestFile {
    param([string]$TestPath, [string]$JUnitPath, [int]$TimeoutSec = 150)
    New-Item -ItemType Directory -Force -Path (Split-Path $JUnitPath) | Out-Null
    $args = @("-m", "coverage", "run", "--parallel-mode", "-m", "pytest", "-q", $TestPath,
              "--maxfail=0", "--disable-warnings", "--durations=20", "--junitxml", $JUnitPath)
    $proc = Start-Process -FilePath "python" -ArgumentList $args -PassThru -NoNewWindow
    if (-not $proc.WaitForExit($TimeoutSec * 1000)) { 
        Stop-Process -Id $proc.Id -Force
        return 124 
    }
    return $proc.ExitCode
}

Write-Host "Testing Phase 1D Invoke-TestFile function..." -ForegroundColor Green

# Set environment for light mode
$env:DISABLE_ML = "1"
$env:DISABLE_TORCH = "1"
$env:DISABLE_TRANSFORMERS = "1"
$env:PYTEST_RUNNING = "1"

# Test with a quick timeout to verify function works
$result = Invoke-TestFile -TestPath "tests/test_auth.py" -JUnitPath "test_reports/junit/test_phase_1d.xml" -TimeoutSec 30

Write-Host "Result: $result" -ForegroundColor Cyan

if ($result -eq 124) {
    Write-Host "TIMEOUT detected correctly" -ForegroundColor Yellow
} elseif ($result -eq 0) {
    Write-Host "PASSED - function working correctly" -ForegroundColor Green  
} else {
    Write-Host "FAILED - but function executed (exit code: $result)" -ForegroundColor Red
}

Write-Host "Phase 1D test complete" -ForegroundColor Green
