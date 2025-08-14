# Auto-fix and test script for AlgoTrading Platform (PowerShell version)
# This script attempts to automatically fix common code issues and run tests

param(
    [switch]$SkipTypeCheck,
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"

Write-Host "🤖 Starting auto-fix and test cycle..." -ForegroundColor Blue

try {
    # Step 1: Auto-format code
    Write-Host "🎨 Step 1: Auto-formatting code..." -ForegroundColor Yellow
    
    & black backend/ tests/
    if ($LASTEXITCODE -ne 0) { throw "Black formatting failed" }
    
    & ruff format backend/ tests/
    if ($LASTEXITCODE -ne 0) { throw "Ruff formatting failed" }
    
    Write-Host "✅ Formatting completed" -ForegroundColor Green

    # Step 2: Auto-fix linting issues
    Write-Host "🔧 Step 2: Auto-fixing linting issues..." -ForegroundColor Yellow
    & ruff check backend/ tests/ --fix
    # Note: ruff check may return non-zero if some issues couldn't be fixed, but continue
    Write-Host "✅ Linting auto-fix completed" -ForegroundColor Green

    # Step 3: Run type checking (informational)
    if (-not $SkipTypeCheck) {
        Write-Host "📝 Step 3: Running type checking..." -ForegroundColor Yellow
        & mypy --strict backend/ tests/ --ignore-missing-imports --show-error-codes
        if ($LASTEXITCODE -ne 0) {
            Write-Host "⚠️  Type checking found issues - manual review needed" -ForegroundColor Yellow
            Write-Host "🔄 Continuing with tests anyway..." -ForegroundColor Yellow
        }
    }

    # Step 4: Run fast test suite 
    if (-not $SkipTests) {
        Write-Host "🏃‍♂️ Step 4: Running fast test suite..." -ForegroundColor Yellow
        $fastTestArgs = @(
            "tests/unit/", "tests/contract/",
            "tests/integration/test_core_trading_flow.py",
            "tests/integration/test_authentication.py", 
            "tests/e2e/test_golden_path.py",
            "-n", "auto", "--tb=short", "--durations=10", "--strict-markers",
            "--disable-warnings", "--maxfail=3", "--timeout=300"
        )
        
        & pytest @fastTestArgs
        if ($LASTEXITCODE -ne 0) { throw "Fast tests failed" }
        Write-Host "✅ Fast tests passed!" -ForegroundColor Green

        # Step 5: Run coverage check
        Write-Host "📊 Step 5: Running coverage check..." -ForegroundColor Yellow
        $coverageArgs = @(
            "tests/unit/", "tests/contract/", "tests/integration/",
            "--cov=backend", "--cov-report=term-missing", "--cov-report=xml",
            "--cov-fail-under=80",
            "-n", "auto", "--tb=short", "--disable-warnings", "--quiet"
        )
        
        & pytest @coverageArgs
        if ($LASTEXITCODE -ne 0) { throw "Coverage check failed" }
        Write-Host "✅ Coverage check passed!" -ForegroundColor Green
    }

    Write-Host ""
    Write-Host "🎉 Auto-fix and test cycle completed successfully!" -ForegroundColor Green
    Write-Host "📊 Coverage report generated: coverage.xml" -ForegroundColor Cyan
    Write-Host "💡 Tip: Run pytest tests/ for comprehensive testing" -ForegroundColor Cyan

} catch {
    Write-Host "❌ Error: $_" -ForegroundColor Red
    exit 1
}
