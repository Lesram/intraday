# Simple PowerShell CI Script with Light Mode

param(
    [string]$TestPath = "tests/api/test_api_main_import.py",
    [int]$Timeout = 30
)

# Ensure UTF-8 encoding 
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"

Write-Host "Starting CI Pipeline with Light Mode" -ForegroundColor Green

# Environment setup
$env:PYTEST_RUNNING = "1"
$env:DISABLE_ML = "1" 
$env:DISABLE_TORCH = "1"
$env:DISABLE_TRANSFORMERS = "1"
$env:PYTHONFAULTHANDLER = "1"

Write-Host "Environment secured for light mode" -ForegroundColor Green

# Validate light mode
Write-Host "Validating Light Mode..." -ForegroundColor Blue
python test_light_mode_final.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "Light mode validation failed" -ForegroundColor Red
    exit 1
}

# Run tests with light mode
Write-Host "Running Tests with Light Mode..." -ForegroundColor Blue
$timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$logFile = "ci_light_$timestamp.log"

python pytest_light.py $TestPath -v --tb=short --timeout=$Timeout --maxfail=5 --junit-xml=test_results.xml 2>&1 | Tee-Object -FilePath $logFile

$exitCode = $LASTEXITCODE
Write-Host ""
Write-Host "Test Results:" -ForegroundColor Cyan
Write-Host "   Exit Code: $exitCode" -ForegroundColor $(if ($exitCode -eq 0) { "Green" } else { "Red" })
Write-Host "   Log File: $logFile" -ForegroundColor Gray

if (Test-Path "test_results.xml") {
    Write-Host "   JUnit XML: test_results.xml created" -ForegroundColor Green
}

Write-Host "CI Pipeline Complete" -ForegroundColor $(if ($exitCode -eq 0) { "Green" } else { "Red" })
exit $exitCode
