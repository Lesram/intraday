# 🔍 Expected Pipeline Execution Output

## Phase 1: Category Discovery
```
2025-08-13 17:15:00 - INFO - Starting comprehensive test execution and analysis
2025-08-13 17:15:01 - INFO - Category 'unit' discovered via marker
2025-08-13 17:15:02 - INFO - Category 'api' discovered via marker
2025-08-13 17:15:02 - INFO - Category 'services' discovered via marker
2025-08-13 17:15:03 - INFO - Category 'risk' discovered via marker
2025-08-13 17:15:03 - INFO - Category 'strategies' discovered via marker
2025-08-13 17:15:04 - INFO - Category 'db' discovered via directory
2025-08-13 17:15:04 - INFO - Category 'integration' discovered via directory
2025-08-13 17:15:05 - INFO - Running categories: ['unit', 'api', 'services', 'risk', 'strategies', 'db', 'integration']
```

## Phase 2: Test Execution (Per Category)
```
2025-08-13 17:15:06 - INFO - Running unit tests (attempt 1)
Command: python -m pytest -q --maxfail=1 --timeout=60 --durations=25 --color=yes -n auto --cov=backend --cov-branch --cov-config=.coveragerc --cov-report=term --junitxml test_reports/junit/unit.xml -m unit

2025-08-13 17:15:20 - INFO - Running api tests (attempt 1)  
Command: python -m pytest -q --maxfail=1 --timeout=60 --durations=25 --color=yes -n auto --cov=backend --cov-branch --cov-config=.coveragerc --cov-report=term --junitxml test_reports/junit/api.xml -m api

2025-08-13 17:15:35 - INFO - Running services tests (attempt 1)
...
```

## Phase 3: Coverage Combination
```
2025-08-13 17:18:45 - INFO - Combining coverage data
2025-08-13 17:18:46 - INFO - Coverage combination completed
```

## Phase 4: Report Generation
```
2025-08-13 17:18:47 - INFO - Report generated: C:\Users\Marsel\intra\algotrading_platform\architect_review\FULL_TEST_AUDIT_REPORT.md
2025-08-13 17:18:47 - INFO - Coverage HTML: C:\Users\Marsel\intra\algotrading_platform\test_reports\htmlcov\index.html
```
