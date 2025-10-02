# Test Results Organization

This directory contains all test execution results, organized by date and test type following professional software development practices.

## Directory Structure

```
test_results/
├── README.md                          # This file
├── YYYY-MM-DD_Test-Description/       # Each test run gets its own dated directory
│   ├── phase1_quality_gates/         # Pre-merge quality gates
│   │   ├── quality_gates_results.json
│   │   ├── bandit_report.json        # SAST security scan
│   │   └── grype_report.json         # SBOM vulnerability scan
│   ├── phase2_5layer_tests/          # Functional test suite
│   │   └── prerun_test_results_*.json
│   ├── phase3_burnin/                # Extended stability testing
│   │   ├── burn_in_report_*.json
│   │   ├── session_result_*.json
│   │   └── k6_cache/                 # K6 performance test cache
│   ├── phase4_promotion/             # Deployment approval gates
│   │   └── promotion_report_*.json
│   └── reports/                      # Human-readable reports
│       ├── TEST_INFRASTRUCTURE_FIXES.md
│       └── *.md
├── burn_in/                          # Active burn-in results (current run)
└── promotion_gates/                  # Active promotion results (current run)
```

## Naming Convention

Test run directories follow the format: `YYYY-MM-DD_Test-Description`

**Examples:**
- `2025-10-01_4-Phase-Testing` - Full 4-phase testing pipeline
- `2025-10-15_Hotfix-Validation` - Hotfix verification
- `2025-11-01_Performance-Baseline` - Performance benchmarking
- `2025-12-01_Pre-Production-Gate` - Pre-production deployment gate

## Retention Policy

### Active Results (Current Run)
- **Location:** `test_results/burn_in/`, `test_results/promotion_gates/`
- **Purpose:** Current test execution in progress
- **Retention:** Overwritten by next test run
- **Archived:** Automatically copied to dated directory on completion

### Archived Results (Historical)
- **Location:** `test_results/YYYY-MM-DD_*`
- **Purpose:** Historical record of test executions
- **Retention:** Keep last 30 days by default
- **Cleanup:** Manual review before deletion

### Exception: Critical Test Runs
Keep indefinitely:
- ✅ Major release validation
- ✅ Production deployment gates
- ✅ Performance baseline runs
- ✅ Incident post-mortems
- ✅ Compliance audits

## Best Practices

### 1. Automated Archiving
Test frameworks automatically archive results to dated directories:
```python
# Example: burn_in_framework.py
result_dir = f"test_results/{datetime.now().strftime('%Y-%m-%d')}_{test_description}"
```

### 2. Human-Readable Reports
Always include markdown reports in the `reports/` subdirectory:
- Executive summaries
- Issue analysis
- Recommendations
- Trends and metrics

### 3. Machine-Readable Data
Store structured data (JSON) in phase-specific directories:
- Enables automated analysis
- Supports CI/CD integration
- Facilitates trend tracking

### 4. Version Control
**DO NOT** commit test results to git:
- Add `test_results/` to `.gitignore`
- Exception: Keep `test_results/README.md` in version control
- Store critical results in artifact storage (S3, Azure Blobs, etc.)

### 5. Clean Root Directory
**NEVER** leave test artifacts in root directory:
- ❌ Root clutter: `test_report.json`, `FIXES.md`, etc.
- ✅ Organized: `test_results/2025-10-01_4-Phase-Testing/reports/FIXES.md`

## Industry Standards

This structure follows common practices from:

### Microsoft Azure DevOps
```
TestResults/
  └── {BuildId}_{BuildName}/
      ├── CodeCoverage/
      ├── TestResults/
      └── Reports/
```

### Jenkins CI/CD
```
test-results/
  └── {JobName}_{BuildNumber}/
      ├── junit/
      ├── coverage/
      └── artifacts/
```

### AWS CodeBuild
```
test-reports/
  └── {Timestamp}_{Branch}/
      ├── unit-tests/
      ├── integration-tests/
      └── reports/
```

## Integration with CI/CD

### Phase 1: Quality Gates
```powershell
# scripts/ci/quality_gates.ps1
$resultDir = "test_results/$(Get-Date -Format 'yyyy-MM-dd')_quality-gates"
```

### Phase 3: Burn-In Testing
```python
# scripts/testing/burn_in_framework.py
result_dir = Path(f"test_results/{date.today()}_burn-in")
```

### Phase 4: Promotion Gates
```python
# scripts/testing/automated_promotion_gates.py
result_dir = Path(f"test_results/{date.today()}_promotion")
```

## Querying Historical Results

### Find all test runs in date range
```powershell
Get-ChildItem test_results -Directory | 
    Where-Object { $_.Name -match '^2025-10-.*' } |
    Sort-Object Name
```

### Compare burn-in stability over time
```powershell
Get-ChildItem test_results/*/phase3_burnin/burn_in_report_*.json |
    ForEach-Object {
        $report = Get-Content $_.FullName | ConvertFrom-Json
        [PSCustomObject]@{
            Date = $_.Directory.Parent.Name
            StabilityScore = $report.aggregate_metrics.stability_score
            RequestsProcessed = $report.aggregate_metrics.total_requests
        }
    } | Format-Table
```

### Find all promotion gate failures
```powershell
Get-ChildItem test_results/*/phase4_promotion/promotion_report_*.json |
    ForEach-Object {
        $report = Get-Content $_.FullName | ConvertFrom-Json
        if (-not $report.all_gates_passed) {
            [PSCustomObject]@{
                Date = $_.Directory.Parent.Name
                GatesPassed = $report.gates_passed
                GatesTotal = $report.gates_total
                Decision = $report.decision
            }
        }
    } | Format-Table
```

## Cleanup Script

```powershell
# cleanup_old_test_results.ps1
param(
    [int]$DaysToKeep = 30,
    [switch]$WhatIf
)

$cutoffDate = (Get-Date).AddDays(-$DaysToKeep)

Get-ChildItem test_results -Directory |
    Where-Object { 
        $_.Name -match '^\d{4}-\d{2}-\d{2}_' -and
        $_.CreationTime -lt $cutoffDate
    } |
    ForEach-Object {
        if ($WhatIf) {
            Write-Host "Would delete: $($_.Name)" -ForegroundColor Yellow
        } else {
            Write-Host "Deleting: $($_.Name)" -ForegroundColor Red
            Remove-Item $_.FullName -Recurse -Force
        }
    }
```

## Summary

✅ **Organized** - Dated directories with clear structure  
✅ **Professional** - Follows industry standards  
✅ **Maintainable** - Clear retention and cleanup policies  
✅ **Queryable** - Easy historical analysis  
✅ **CI/CD Ready** - Automated archiving support  

---

**Last Updated:** 2025-10-01  
**Maintained By:** Platform Engineering Team
