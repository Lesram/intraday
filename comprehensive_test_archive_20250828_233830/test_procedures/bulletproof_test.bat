@echo off
cd /d "C:\Users\Marsel\intra\algotrading_platform"
echo === BULLETPROOF TEST EXECUTION ===
echo Current Directory: %CD%
echo Date/Time: %DATE% %TIME%
echo.
echo Verifying environment:
echo - Tests directory exists: 
dir tests >nul 2>&1 && echo YES || echo NO
echo.
echo Starting comprehensive test execution...
echo Target: ALL 3,907 tests
echo Results: bulletproof_comprehensive_results.xml
echo.
python -m pytest tests/ --maxfail=0 --continue-on-collection-errors --disable-warnings --tb=no --junit-xml=bulletproof_comprehensive_results.xml
echo.
echo === TEST EXECUTION COMPLETE ===
echo Return code: %ERRORLEVEL%
echo.
if exist bulletproof_comprehensive_results.xml (
    echo Results file created successfully
    echo File size: 
    for %%A in (bulletproof_comprehensive_results.xml) do echo %%~zA bytes
) else (
    echo ERROR: Results file was not created
)
pause
