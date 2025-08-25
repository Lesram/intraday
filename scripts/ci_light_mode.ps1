# PowerShell CI Script with Light Mode
# This script runs the complete test suite using light mode to prevent ML library hangs

param(
    [string]$TestPath = "",
    [switch]$SkipInstall,
    [switch]$Verbose,
    [int]$Timeout = 60
)

# Ensure UTF-8 encoding 
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"

# Set working directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "🚀 Starting CI Pipeline with Light Mode" -ForegroundColor Green
Write-Host "📁 Working Directory: $(Get-Location)" -ForegroundColor Cyan
Write-Host "⏰ Timeout: $Timeout seconds" -ForegroundColor Yellow

# Install dependencies if needed
if (-not $SkipInstall) {
    Write-Host "`n📦 Installing dependencies..." -ForegroundColor Blue
    python -m pip install --upgrade pip
    if (Test-Path "requirements.txt") {
        pip install -r requirements.txt
    }
    pip install pytest pytest-asyncio pytest-timeout respx
}

# Environment setup
$env:PYTEST_RUNNING = "1"
$env:DISABLE_ML = "1" 
$env:DISABLE_TORCH = "1"
$env:DISABLE_TRANSFORMERS = "1"
$env:PYTHONFAULTHANDLER = "1"

Write-Host "`n🔒 Environment secured:" -ForegroundColor Green
Write-Host "   PYTEST_RUNNING=$env:PYTEST_RUNNING" -ForegroundColor Gray
Write-Host "   DISABLE_ML=$env:DISABLE_ML" -ForegroundColor Gray
Write-Host "   DISABLE_TORCH=$env:DISABLE_TORCH" -ForegroundColor Gray
Write-Host "   DISABLE_TRANSFORMERS=$env:DISABLE_TRANSFORMERS" -ForegroundColor Gray

# Validate light mode setup
Write-Host "`n🧪 Validating Light Mode..." -ForegroundColor Blue
python -c "try:`n    import conftest_light_mode`n    print('✅ Light mode validation successful')`nexcept Exception as e:`n    print('❌ Light mode validation failed:', e)`n    exit(1)"

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Light mode validation failed" -ForegroundColor Red
    exit 1
}

# Determine test path
$actualTestPath = if ($TestPath) { $TestPath } else { "tests/" }

# Run tests with light mode wrapper
Write-Host "`n🧪 Running Tests with Light Mode..." -ForegroundColor Blue
Write-Host "   Test Path: $actualTestPath" -ForegroundColor Gray

$testArgs = @(
    $actualTestPath,
    "-v",
    "--tb=short", 
    "--timeout=$Timeout",
    "--maxfail=10",
    "--junit-xml=test_results.xml"
)

if ($Verbose) {
    $testArgs += "--capture=no"
}

# Add current timestamp
$timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$logFile = "ci_light_mode_$timestamp.log"

Write-Host "📝 Logging to: $logFile" -ForegroundColor Cyan

# Execute tests with light mode wrapper
$testCommand = "python pytest_light.py " + ($testArgs -join " ")
Write-Host "🚀 Executing: $testCommand" -ForegroundColor Yellow

# Capture both output and errors
$process = Start-Process -FilePath "python" -ArgumentList @("pytest_light.py") + $testArgs -Wait -PassThru -RedirectStandardOutput "$logFile.out" -RedirectStandardError "$logFile.err"

# Display results
Write-Host "`n📊 Test Execution Complete" -ForegroundColor Green
Write-Host "   Exit Code: $($process.ExitCode)" -ForegroundColor $(if ($process.ExitCode -eq 0) { "Green" } else { "Red" })

# Show output
if (Test-Path "$logFile.out") {
    Write-Host "`n📄 Test Output:" -ForegroundColor Blue
    Get-Content "$logFile.out" | Select-Object -Last 50
}

if (Test-Path "$logFile.err" -and (Get-Item "$logFile.err").Length -gt 0) {
    Write-Host "`n⚠️  Test Errors:" -ForegroundColor Yellow  
    Get-Content "$logFile.err" | Select-Object -Last 20
}

# Generate summary
Write-Host "`n📋 Test Summary:" -ForegroundColor Cyan
if (Test-Path "test_results.xml") {
    Write-Host "   JUnit XML: test_results.xml created ✅" -ForegroundColor Green
} else {
    Write-Host "   JUnit XML: Not created ❌" -ForegroundColor Red
}

Write-Host "   Log files: $logFile.out, $logFile.err" -ForegroundColor Gray
Write-Host "   Timestamp: $timestamp" -ForegroundColor Gray

# Exit with same code as tests
Write-Host "`n🏁 CI Pipeline Complete" -ForegroundColor $(if ($process.ExitCode -eq 0) { "Green" } else { "Red" })
exit $process.ExitCode
