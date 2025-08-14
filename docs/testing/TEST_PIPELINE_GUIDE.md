# 🔬 Comprehensive Test Execution Pipeline

This pipeline provides a complete, deterministic test execution and analysis system for the intraday trading platform. It discovers test categories, runs them with proper isolation and coverage, then generates an architect-ready report with actionable insights.

## 🚀 Quick Start

### Run Full Test Suite with Report
```powershell
.\run_all_tests_and_report.ps1
```

### Run Fast Lane (Unit + API + Services)
```powershell
.\run_all_tests_and_report.ps1 -Fast
```

### VS Code Integration
1. Open Command Palette (`Ctrl+Shift+P`)
2. Select "Tasks: Run Task"
3. Choose "All Tests & Report" or "Fast Lane"

## 📁 Output Structure

```
test_reports/
├── junit/           # JUnit XML files per category
├── logs/            # Detailed execution logs per category  
├── coverage.xml     # Coverage for CI/CD integration
├── coverage.json    # Coverage data for analysis
└── htmlcov/         # Interactive HTML coverage report

architect_review/
└── FULL_TEST_AUDIT_REPORT.md  # Comprehensive analysis report
```

## 🎯 Test Categories

The pipeline automatically discovers and runs these test categories:

| Category | Parallel | Description | Discovery Method |
|----------|----------|-------------|------------------|
| `unit` | ✅ | Fast, isolated unit tests | Marker: `-m unit` |
| `api` | ✅ | HTTP/REST endpoint tests | Marker: `-m api` |
| `services` | ✅ | Business logic layer tests | Marker: `-m services` |
| `risk` | ✅ | Risk management tests | Marker: `-m risk` |
| `strategies` | ✅ | Trading strategy tests | Marker: `-m strategies` |
| `db` | ✅ | Database layer tests | Marker: `-m db` |
| `ws` | ❌ | WebSocket tests (sequential) | Marker: `-m ws` |
| `integration` | ❌ | Cross-system integration | Marker: `-m integration` |
| `e2e` | ❌ | End-to-end workflows | Marker: `-m e2e` |
| `perf` | ❌ | Performance benchmarks | Marker: `-m perf` |
| `chaos` | ❌ | Chaos engineering tests | Marker: `-m chaos` |

### Discovery Logic
1. **Marker Priority**: Try `pytest -m {category}` first
2. **Directory Fallback**: Use `tests/{category}/` if marker fails
3. **Skip Missing**: Log and continue if neither exists

## 🔧 Pipeline Features

### Deterministic Execution
- Uses global seed fixtures (no artificial delays)
- 60-second per-test timeout
- Consistent environment setup

### Intelligent Parallelization
- Small suites (`unit`, `api`, etc.): `-n auto` for speed
- Large suites (`integration`, `e2e`, etc.): Sequential for stability

### Comprehensive Coverage
- Branch coverage enabled (`--cov-branch`)
- Parallel coverage data collection
- Combined final reports (XML, JSON, HTML)

### Failure Analysis
- Automatic retry for flakiness detection
- Error grouping by type and subsystem
- Stack trace extraction with context

### Windows-Friendly
- PowerShell-native paths and execution
- POSIX normalization for cross-platform compatibility
- Robust error handling and logging

## 📊 Report Sections

The generated `FULL_TEST_AUDIT_REPORT.md` includes:

### 1. Executive Summary
- Overall pass/fail rates
- Per-category results table
- Per-package coverage breakdown

### 2. Failure Analysis
- Top failure types with occurrence counts
- Suspected subsystem identification
- Example stack traces with context

### 3. Performance & Flakiness
- Top 20 slowest tests across all suites
- Flaky test detection (failed→passed on retry)
- Execution time analysis

### 4. Coverage Gaps
- Per-package coverage table
- Top 10 files by missed lines
- Branch coverage analysis (when available)

### 5. System Health Assessment
- **API Health**: Factory pattern usage, route registration
- **WebSocket Health**: Coverage metrics, connection handling
- **Database Health**: Session factory issues, connection problems

### 6. Actionable Fixes (PR-Ready)
- Priority-ranked fix recommendations
- Specific file/function targets  
- Concrete implementation guidance

### 7. Architect Review Checklist
- Available artifacts for independent review
- Missing artifacts that would help analysis

## ⚙️ Configuration

### Coverage Requirements (.coveragerc)
```ini
[run]
source = backend
branch = True
parallel = True
fail_under = 40

[report]
precision = 1
show_missing = True
```

### Test Markers (pytest.ini)
```ini
[pytest]
markers =
    unit: Fast, isolated unit tests
    api: HTTP/REST endpoint tests
    services: Business logic tests
    # ... (see pytest.ini for full list)
```

## 🚨 Common Issues & Solutions

### "No tests collected"
- **Cause**: Category marker doesn't exist or no tests in directory
- **Solution**: Check `pytest.ini` markers or create `tests/{category}/` directory

### "Coverage combine failed"
- **Cause**: No parallel coverage files generated
- **Solution**: Ensure tests ran and `.coverage.*` files exist

### "Module not found"
- **Cause**: Missing dependencies or virtual environment not activated
- **Solution**: Run `pip install -r requirements-dev.txt`

### PowerShell execution policy error
- **Cause**: Windows security restrictions
- **Solution**: Run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

## 🔄 Integration with CI/CD

The pipeline generates standard artifacts for CI/CD integration:

```yaml
# Example GitHub Actions usage
- name: Run Test Pipeline
  run: powershell -ExecutionPolicy Bypass -File run_all_tests_and_report.ps1

- name: Upload Coverage
  uses: codecov/codecov-action@v3
  with:
    file: test_reports/coverage.xml

- name: Archive Test Results
  uses: actions/upload-artifact@v3
  with:
    name: test-results
    path: |
      test_reports/
      architect_review/
```

## 🎯 Customization

### Run Specific Categories Only
```bash
python scripts/run_all_tests_and_report.py --only "unit,api"
```

### Adjust Timeouts
```bash
python scripts/run_all_tests_and_report.py --timeout 120
```

### Skip Report Generation
```bash
python scripts/run_all_tests_and_report.py --no-htmlcov --no-covjson
```

### Increase Retry Attempts
```bash
python scripts/run_all_tests_and_report.py --repeat-failing 2
```

## 🏆 Success Metrics

The pipeline considers a run successful when:

- All test categories execute (failures recorded, not blocking)
- Coverage data successfully combined
- Comprehensive report generated
- Exit code 0 (allows report review even on test failures)

The actual test results and quality metrics are captured in the architect review report for action planning.

---

*This pipeline ensures comprehensive, reproducible test execution with actionable insights for continuous platform improvement.*
