@echo off
REM FIXED DIRECTORY BATCH TEST EXECUTION
cd /d "C:\Users\Marsel\intra\algotrading_platform"
echo === BATCH TEST RUNNER EXECUTION ===
echo Current Directory: %CD%
echo Date/Time: %DATE% %TIME%
echo.
echo Verifying batch test runner exists:
if exist "batch_test_runner.py" (
    echo ✅ batch_test_runner.py found
) else (
    echo ❌ batch_test_runner.py not found
    pause
    exit /b 1
)
echo.
echo Verifying tests directory:
if exist "tests" (
    echo ✅ tests directory found
) else (
    echo ❌ tests directory not found
    pause
    exit /b 1
)
echo.
echo Starting batch test execution...
echo Target: ALL tests in small batches
echo.
python batch_test_runner.py tests/ --batch-size 5 --timeout 120
echo.
echo === BATCH TEST EXECUTION COMPLETE ===
echo Return code: %ERRORLEVEL%
pause
