@echo off
REM Local CI Pipeline Runner for Windows
REM Simulates the GitHub Actions CI pipeline locally

echo 🚀 Running Local CI Pipeline Simulation
echo ========================================

REM Track results
set LINT_RESULT=0
set TYPE_RESULT=0
set SECURITY_RESULT=0
set TEST_RESULT=0

echo.
echo 🔍 Step 1: Lint ^& Format Check
echo ================================

ruff check --no-fix .
if %ERRORLEVEL% EQU 0 (
    echo ✅ Ruff linting passed
) else (
    echo ❌ Ruff linting failed
    set LINT_RESULT=1
)

ruff format --check .
if %ERRORLEVEL% EQU 0 (
    echo ✅ Ruff formatting passed
) else (
    echo ❌ Ruff formatting failed
    set LINT_RESULT=1
)

echo.
echo 🧮 Step 2: Type Check
echo =====================

mypy --strict backend tests --ignore-missing-imports --show-error-codes
if %ERRORLEVEL% EQU 0 (
    echo ✅ MyPy type checking passed
) else (
    echo ❌ MyPy type checking failed
    set TYPE_RESULT=1
)

echo.
echo 🛡️ Step 3: Security Scan
echo ========================

REM Bandit security scan
bandit -r backend -lll
if %ERRORLEVEL% EQU 0 (
    echo ✅ Bandit security scan passed
) else (
    echo ❌ Bandit security scan failed
    set SECURITY_RESULT=1
)

REM pip-audit vulnerability scan
pip-audit --version >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    pip-audit
    if %ERRORLEVEL% EQU 0 (
        echo ✅ pip-audit vulnerability scan passed
    ) else (
        echo ⚠️ pip-audit found vulnerabilities ^(may be false positives^)
    )
) else (
    echo ⚠️ pip-audit not installed, skipping vulnerability scan
)

REM Safety check
safety --version >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    safety check
    if %ERRORLEVEL% EQU 0 (
        echo ✅ Safety vulnerability check passed
    ) else (
        echo ⚠️ Safety found potential issues ^(review manually^)
    )
) else (
    echo ⚠️ safety not installed, skipping vulnerability scan
)

REM Metrics label check
if exist "scripts\ci\check_metrics_labels.py" (
    echo.
    echo 🏷️ Checking metrics labels...
    python scripts\ci\check_metrics_labels.py
    if %ERRORLEVEL% EQU 0 (
        echo ✅ Metrics labels validation passed
    ) else (
        echo ❌ Metrics labels validation failed
        set SECURITY_RESULT=1
    )
)

echo.
echo 🧪 Step 4: Test ^& Coverage
echo ===========================

REM Set test environment variables
set TESTING=true
set DATABASE_URL=postgresql://testuser:testpass@localhost:5432/testdb
set REDIS_URL=redis://localhost:6379/0

REM Check if services are running
netstat -an | findstr :5432 >nul
if %ERRORLEVEL% NEQ 0 (
    echo ⚠️ PostgreSQL not running locally - integration tests may fail
)

netstat -an | findstr :6379 >nul
if %ERRORLEVEL% NEQ 0 (
    echo ⚠️ Redis not running locally - caching tests may fail
)

REM Run tests with coverage
pytest --cov=backend --cov-report=xml:coverage.xml --cov-report=html:htmlcov --cov-report=term-missing --cov-fail-under=85 --maxfail=1 --disable-warnings -x tests/
if %ERRORLEVEL% EQU 0 (
    echo ✅ Tests and coverage passed
) else (
    echo ❌ Tests or coverage failed
    set TEST_RESULT=1
)

REM Summary
echo.
echo 📋 CI Pipeline Results Summary
echo ==============================

if %LINT_RESULT% EQU 0 (
    echo ✅ Lint ^& Format: PASSED
) else (
    echo ❌ Lint ^& Format: FAILED
)

if %TYPE_RESULT% EQU 0 (
    echo ✅ Type Check: PASSED
) else (
    echo ❌ Type Check: FAILED
)

if %SECURITY_RESULT% EQU 0 (
    echo ✅ Security Scan: PASSED
) else (
    echo ❌ Security Scan: FAILED
)

if %TEST_RESULT% EQU 0 (
    echo ✅ Tests ^& Coverage: PASSED
) else (
    echo ❌ Tests ^& Coverage: FAILED
)

echo.

REM Final result
set /a TOTAL_FAILURES=%LINT_RESULT%+%TYPE_RESULT%+%SECURITY_RESULT%+%TEST_RESULT%

if %TOTAL_FAILURES% EQU 0 (
    echo 🎉 All quality gates passed! Ready for CI/CD
    echo.
    echo Next steps:
    echo   git add .
    echo   git commit -m "Your commit message"
    echo   git push origin your-branch
    exit /b 0
) else (
    echo ❌ %TOTAL_FAILURES% quality gate^(s^) failed
    echo.
    echo Please fix the issues above before committing.
    echo Run individual commands to debug:
    echo   ruff check . --fix     # Fix linting
    echo   mypy backend tests     # Check types
    echo   bandit -r backend      # Review security
    echo   pytest tests/          # Run tests
    exit /b 1
)
