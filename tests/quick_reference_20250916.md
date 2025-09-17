# Test Suite Quick Reference Guide
**Created:** September 16, 2025  
**Status:** CAN BE REMOVED (Reference documentation)  
**Purpose:** Quick commands for running unified test suite

## Quick Commands

### Basic Test Execution
```bash
# Run all tests
cd c:\Users\Marsel\intra\algotrading_platform
C:/Users/Marsel/intra/algotrading_platform/venv/Scripts/python.exe -m pytest

# Run with coverage
C:/Users/Marsel/intra/algotrading_platform/venv/Scripts/python.exe -m pytest --cov=backend --cov-report=html:test_results/coverage_html

# Run specific test file
C:/Users/Marsel/intra/algotrading_platform/venv/Scripts/python.exe -m pytest tests/test_auth.py -v
```

### Advanced Execution
```bash
# Parallel execution (faster)
C:/Users/Marsel/intra/algotrading_platform/venv/Scripts/python.exe -m pytest -n auto --cov=backend

# Run specific test categories
C:/Users/Marsel/intra/algotrading_platform/venv/Scripts/python.exe -m pytest -m "api" 
C:/Users/Marsel/intra/algotrading_platform/venv/Scripts/python.exe -m pytest -m "auth"

# Comprehensive reporting
C:/Users/Marsel/intra/algotrading_platform/venv/Scripts/python.exe -m pytest --cov=backend --cov-report=html:test_results/coverage_html --cov-report=xml:test_results/coverage.xml --junitxml=test_results/results.xml
```

### Automated Analysis
```bash
# Run comprehensive test suite analysis
C:/Users/Marsel/intra/algotrading_platform/venv/Scripts/python.exe tests/unified_test_suite_runner_20250916.py

# Run quick validation
C:/Users/Marsel/intra/algotrading_platform/venv/Scripts/python.exe tests/quick_validation_20250916.py
```

## Coverage Reports
- **HTML:** `test_results/coverage_html/index.html`
- **XML:** `test_results/coverage.xml`  
- **Terminal:** Displayed during test execution

## Test Organization
- **All Tests:** `tests/` directory
- **Results:** `test_results/` directory
- **Reports:** `reports/` directory
- **Configuration:** `pytest.ini`

## Key Features
✅ 30-second timeout protection  
✅ Parallel execution support  
✅ Comprehensive coverage reporting  
✅ Organized result consolidation  
✅ Multiple output formats  

*Follow new file organization protocol - all test artifacts are marked for removal after use.*