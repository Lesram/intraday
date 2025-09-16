@echo off
cd /d "C:\Users\Marsel\intra\algotrading_platform"
echo Current Directory: %CD%
echo.
echo Starting comprehensive test execution...
echo Target: All 3,907 tests
echo.
python -m pytest tests/ --tb=short --maxfail=999 --continue-on-collection-errors --junit-xml=comprehensive_test_results.xml
echo.
echo Test execution completed.
echo Results saved to: comprehensive_test_results.xml
pause
