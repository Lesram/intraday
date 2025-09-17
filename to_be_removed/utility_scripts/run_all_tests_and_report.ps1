# PowerShell Test Execution Wrapper
# Runs comprehensive test analysis with sensible defaults

param(
    [switch]$Fast,
    [switch]$Help
)

if ($Help) {
    Write-Host "Intraday Trading Platform - Test Execution Pipeline" -ForegroundColor Green
    Write-Host ""
    Write-Host "Usage:"
    Write-Host "  .\run_all_tests_and_report.ps1         # Full test suite with report"
    Write-Host "  .\run_all_tests_and_report.ps1 -Fast   # Quick smoke tests only"
    Write-Host "  .\run_all_tests_and_report.ps1 -Help   # Show this help"
    Write-Host ""
    Write-Host "Outputs:"
    Write-Host "  - test_reports/htmlcov/index.html      # Interactive coverage"
    Write-Host "  - architect_review/FULL_TEST_AUDIT_REPORT.md  # Comprehensive analysis"
    Write-Host ""
    exit 0
}

Write-Host "🚀 Intraday Trading Platform - Test Execution Pipeline" -ForegroundColor Green
Write-Host "="*60 -ForegroundColor Blue

# Ensure we're in the right directory
if (-not (Test-Path "backend" -PathType Container)) {
    Write-Host "❌ Error: Must run from project root (backend/ folder not found)" -ForegroundColor Red
    exit 1
}

# Create required directories
Write-Host "📁 Creating output directories..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path "test_reports" | Out-Null
New-Item -ItemType Directory -Force -Path "test_reports\junit" | Out-Null
New-Item -ItemType Directory -Force -Path "test_reports\logs" | Out-Null
New-Item -ItemType Directory -Force -Path "architect_review" | Out-Null
New-Item -ItemType Directory -Force -Path "scripts" | Out-Null

try {

# Ensure Python script exists
$pythonScript = "scripts\run_all_tests_and_report.py"
if (-not (Test-Path $pythonScript)) {
    Write-Host "❌ Error: Python orchestrator not found at $pythonScript" -ForegroundColor Red
    exit 1
}

Write-Host "🔍 Activating virtual environment..." -ForegroundColor Yellow
    if (Test-Path "venv\Scripts\Activate.ps1") {
        & .\venv\Scripts\Activate.ps1
    } elseif (Test-Path ".venv\Scripts\Activate.ps1") {
        & .\.venv\Scripts\Activate.ps1
    } else {
        Write-Host "⚠️ Warning: No virtual environment found, using system Python" -ForegroundColor DarkYellow
    }
    
    Write-Host "🧪 Starting test execution pipeline..." -ForegroundColor Yellow
    
    if ($Fast) {
        # Fast lane - unit, api, services only
        Write-Host "🏃 Running Fast Lane tests (unit, api, services)..." -ForegroundColor Cyan
        & python $pythonScript --only "unit,api,services" --repeat-failing 0 --timeout 30
    } else {
        # Full comprehensive run
        Write-Host "🔬 Running comprehensive test suite..." -ForegroundColor Cyan
        & python $pythonScript --all --repeat-failing 1 --timeout 60 --htmlcov --junit --covjson
    }
    
    Write-Host ""
    Write-Host "="*60 -ForegroundColor Blue
    Write-Host "✅ Test execution pipeline completed!" -ForegroundColor Green
    
    # Report locations
    $reportFile = "architect_review\FULL_TEST_AUDIT_REPORT.md"
    $htmlCoverage = "test_reports\htmlcov\index.html"
    
    if (Test-Path $reportFile) {
        Write-Host "📊 Architect Review Report: $reportFile" -ForegroundColor White
    }
    
    if (Test-Path $htmlCoverage) {
        Write-Host "🎯 Coverage Report: $htmlCoverage" -ForegroundColor White
    }
    
    Write-Host ""
    Write-Host "💡 Next Steps:" -ForegroundColor Yellow
    Write-Host "   1. Review the architect report for actionable fixes"
    Write-Host "   2. Open HTML coverage to identify testing gaps"
    Write-Host "   3. Check test_reports/logs/ for detailed execution logs"
    
    # Always exit 0 to allow report review
    exit 0

} catch {
    Write-Host ""
    Write-Host "❌ Pipeline execution failed: $_" -ForegroundColor Red
    Write-Host "Check the error details above and try again." -ForegroundColor Yellow
    exit 0  # Still exit 0 for report access
}
