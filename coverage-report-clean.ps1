# PowerShell Coverage Report Script
# Validates coverage using the enhanced coverage checker

param(
    [string]$Mode = "strict"
)

Write-Host "Running comprehensive coverage analysis..." -ForegroundColor Cyan

# Ensure test_reports directory exists
if (-not (Test-Path "test_reports")) {
    New-Item -ItemType Directory -Path "test_reports" -Force | Out-Null
    Write-Host "Created test_reports directory" -ForegroundColor Yellow
}

# Activate virtual environment if needed
if ($env:VIRTUAL_ENV -eq $null -and (Test-Path "venv\Scripts\Activate.ps1")) {
    Write-Host "Activating virtual environment..." -ForegroundColor Yellow
    & "venv\Scripts\Activate.ps1"
}

# Determine whether to use soft mode for local development
$softFlag = ""
if ($Mode -eq "soft" -or $args -contains "--soft") {
    $softFlag = "--soft"
    Write-Host "Using soft mode - warnings only" -ForegroundColor Yellow
}

# Run coverage checker with optional soft mode
Write-Host "Executing coverage checker..." -ForegroundColor Blue
if ($softFlag -ne "") {
    python scripts/check_coverage.py $softFlag
} else {
    python scripts/check_coverage.py
}

$exitCode = $LASTEXITCODE

if ($exitCode -eq 0) {
    Write-Host "Coverage check passed!" -ForegroundColor Green
} else {
    Write-Host "Coverage check failed!" -ForegroundColor Red
}

exit $exitCode
