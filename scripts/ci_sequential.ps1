Param(
  [switch]$WithCoverageJson,
  [switch]$TestRun
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$PSDefaultParameterValues['Out-File:Encoding'] = 'utf8'

Write-Host "Starting SEQUENTIAL Batched CI Runner with Light Mode" -ForegroundColor Green
Write-Host "Working Directory: $(Get-Location)" -ForegroundColor Cyan

New-Item -ItemType Directory -Force -Path "test_reports","test_reports\junit","test_reports\coverage_html","test_reports\logs" | Out-Null

# Environment setup for Light Mode
$env:PYTHONFAULTHANDLER = "1"
$env:PYTHONUNBUFFERED   = "1"
$env:DISABLE_ML         = "1"
$env:DISABLE_TORCH      = "1"
$env:DISABLE_TRANSFORMERS = "1"
$env:PYTEST_RUNNING     = "1"
$env:PYTHONIOENCODING   = "utf-8"

Write-Host "Environment secured for Light Mode" -ForegroundColor Green

# Validate Light Mode before starting batches
Write-Host "Validating Light Mode setup..." -ForegroundColor Blue
python -c "try:`n    import conftest_light_mode`n    print('Light Mode validation successful')`nexcept Exception as e:`n    print('Light Mode validation failed:', e)`n    exit(1)"

if ($LASTEXITCODE -ne 0) {
    Write-Host "Light Mode validation failed - aborting" -ForegroundColor Red
    exit 1
}

# Helper to sanitize file names for XML output
function Get-SafeFileName($filePath) {
    return $filePath -replace '[\\\/]', '_' -replace '\.py$', ''
}

# Phase 1D: Per-file hard timeout with process isolation
function Invoke-TestFile {
    param([string]$TestPath, [string]$JUnitPath, [int]$TimeoutSec = 150)
    New-Item -ItemType Directory -Force -Path (Split-Path $JUnitPath) | Out-Null
    $args = @("-m", "coverage", "run", "--parallel-mode", "-m", "pytest", "-q", $TestPath,
              "--maxfail=0", "--disable-warnings", "--durations=20", "--junitxml", $JUnitPath)
    $proc = Start-Process -FilePath "python" -ArgumentList $args -PassThru -NoNewWindow
    if (-not $proc.WaitForExit($TimeoutSec * 1000)) { 
        Stop-Process -Id $proc.Id -Force
        return 124 
    }
    return $proc.ExitCode
}

# Helper to get test files from a directory
function Get-TestFilesFromDirectory($directory) {
    $testFiles = @()
    if (Test-Path $directory) {
        Get-ChildItem -Path $directory -Recurse -Filter "test_*.py" | ForEach-Object {
            $testFiles += $_.FullName.Replace($PWD.Path + "\", "").Replace("\", "/")
        }
    }
    return $testFiles
}

# Helper to run individual test files sequentially within a batch
function Invoke-SequentialTestBatch($batchName, $testDirectory, $filter = "") {
    Write-Host "`n=== Starting Sequential Batch: $batchName ===" -ForegroundColor Yellow
    
    # Get all test files in the directory
    $testFiles = Get-TestFilesFromDirectory $testDirectory
    
    if ($filter) {
        Write-Host "Filter applied: $filter" -ForegroundColor Gray
    }
    
    if ($testFiles.Count -eq 0) {
        Write-Host "No test files found in $testDirectory" -ForegroundColor Yellow
        return @{ passed = 0; failed = 0; total = 0 }
    }
    
    Write-Host "Found $($testFiles.Count) test files in $testDirectory" -ForegroundColor Cyan
    
    # If test run, limit to first 3 files
    if ($TestRun -and $testFiles.Count -gt 3) {
        $testFiles = $testFiles[0..2]
        Write-Host "TEST RUN: Limited to first 3 files" -ForegroundColor Yellow
    }
    
    $batchResults = @{
        passed = 0
        failed = 0
        total = $testFiles.Count
        failedFiles = @()
    }
    
    $batchJunitFiles = @()
    
    # Process each test file individually
    foreach ($testFile in $testFiles) {
        $safeName = Get-SafeFileName $testFile
        $junit = "test_reports\junit\${safeName}.xml"
        $batchJunitFiles += $junit
        
        Write-Host "  Running: $testFile" -ForegroundColor Cyan
        
        # Phase 1D: Use Invoke-TestFile with hard timeout and process isolation
        try {
            # Ensure environment is secured for Light Mode
            $env:DISABLE_ML = "1"
            $env:DISABLE_TORCH = "1" 
            $env:DISABLE_TRANSFORMERS = "1"
            $env:PYTEST_RUNNING = "1"
            
            # Use Invoke-TestFile with 150-second hard timeout
            $exitCode = Invoke-TestFile -TestPath $testFile -JUnitPath $junit -TimeoutSec 150
            
            if ($exitCode -eq 0) {
                Write-Host "    PASSED" -ForegroundColor Green
                $batchResults.passed++
            } elseif ($exitCode -eq 124) {
                Write-Host "    TIMEOUT (150s exceeded)" -ForegroundColor Magenta
                $batchResults.failed++
                $batchResults.failedFiles += "$testFile (TIMEOUT)"
            } else {
                Write-Host "    FAILED (exit code: $exitCode)" -ForegroundColor Red
                $batchResults.failed++
                $batchResults.failedFiles += $testFile
            }
        } catch {
            Write-Host "    ERROR: $_" -ForegroundColor Red
            $batchResults.failed++
            $batchResults.failedFiles += $testFile
        }
    }
    
    # Create combined JUnit XML for the batch (optional, since we now have individual files)
    $combinedJunit = "test_reports\junit\${batchName}.xml"
    if ($batchJunitFiles.Count -gt 0) {
        # Simple combination - just concatenate the XML files (basic approach)
        $combinedContent = '<?xml version="1.0" encoding="utf-8"?><testsuites>'
        foreach ($junitFile in $batchJunitFiles) {
            if (Test-Path $junitFile) {
                $content = Get-Content $junitFile -Raw
                if ($content -match '<testsuite[^>]*>.*</testsuite>') {
                    $combinedContent += $matches[0]
                }
            }
        }
        $combinedContent += '</testsuites>'
        $combinedContent | Out-File $combinedJunit -Encoding utf8
    }

    # Summary for this batch
    $successRate = if ($batchResults.total -gt 0) { [math]::Round(($batchResults.passed / $batchResults.total) * 100, 1) } else { 0 }
    Write-Host "  Batch $batchName Summary: $($batchResults.passed)/$($batchResults.total) passed (${successRate}%)" -ForegroundColor $(if ($batchResults.failed -eq 0) { "Green" } else { "Yellow" })

    return $batchResults
}

# Define batches - using sequential approach
Write-Host "`nConfiguring sequential test batches..." -ForegroundColor Blue

if ($TestRun) {
    Write-Host "TEST RUN MODE: Limited batch execution" -ForegroundColor Yellow
    $batches = @(
        @{ name="api-test";          directory="tests/api"; filter="" }
    )
} else {
    $batches = @(
        @{ name="api";          directory="tests/api"; filter="" },
        @{ name="services";     directory="tests/services"; filter="" },
        @{ name="risk";         directory="tests/risk"; filter="" },
        @{ name="integration";  directory="tests/integration"; filter="not perf and not mlheavy" },
        @{ name="ws";           directory="tests/ws"; filter="not perf" },
        @{ name="mlops-core";   directory="tests/mlops"; filter="not mlheavy" },
        @{ name="unit-core";    directory="tests/unit"; filter="not perf and not mlheavy" }
    )
}

Write-Host "Total batches configured: $($batches.Count)" -ForegroundColor Cyan

# Execute all batches sequentially
$overallResults = @{
    totalPassed = 0
    totalFailed = 0
    totalTests = 0
    batchSummary = @{}
}

foreach ($batch in $batches) {
    $startTime = Get-Date
    $result = Invoke-SequentialTestBatch $batch.name $batch.directory $batch.filter
    $endTime = Get-Date
    $duration = ($endTime - $startTime).TotalSeconds
    
    $overallResults.totalPassed += $result.passed
    $overallResults.totalFailed += $result.failed
    $overallResults.totalTests += $result.total
    $overallResults.batchSummary[$batch.name] = @{
        passed = $result.passed
        failed = $result.failed
        total = $result.total
        duration = $duration
        failedFiles = $result.failedFiles
    }
}

# Generate coverage reports after all files processed
Write-Host "`nProcessing coverage data..." -ForegroundColor Blue
try {
    Write-Host "Combining coverage data files..." -ForegroundColor Gray
    coverage combine | Out-Null
    
    Write-Host "Generating coverage XML..." -ForegroundColor Gray
    coverage xml -o test_reports\coverage.xml
    
    Write-Host "Generating coverage HTML..." -ForegroundColor Gray  
    coverage html -d test_reports\coverage_html
    
    if ($WithCoverageJson) {
        Write-Host "Generating coverage JSON..." -ForegroundColor Gray
        try { 
            coverage json -o test_reports\coverage.json
            Write-Host "Coverage JSON generated successfully" -ForegroundColor Green 
        } catch { 
            "coverage json not available" | Out-File test_reports\logs\coverage_json_missing.txt
            Write-Host "Coverage JSON not available - logged to coverage_json_missing.txt" -ForegroundColor Yellow
        }
    }
    Write-Host "Coverage reports generated successfully" -ForegroundColor Green
} catch {
    Write-Host "Coverage report generation failed: $_" -ForegroundColor Yellow
    $_ | Out-File "test_reports\logs\coverage_error.log"
}

# Generate combined JUnit XML
Write-Host "`nMerging JUnit XML files..." -ForegroundColor Blue
try {
    python scripts\merge_junit.py 2>&1 | Out-File "test_reports\logs\junit_merge.log"
    if ($LASTEXITCODE -eq 0) {
        Write-Host "JUnit XML files merged successfully -> test_reports\junit\all.xml" -ForegroundColor Green
    } else {
        Write-Host "JUnit XML merge failed" -ForegroundColor Yellow
    }
} catch {
    Write-Host "JUnit XML merge error: $_" -ForegroundColor Yellow
}

# Generate final summary
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$successRate = if ($overallResults.totalTests -gt 0) { 
    [math]::Round(($overallResults.totalPassed / $overallResults.totalTests) * 100, 1) 
} else { 0 }

$summary = @"
=== SEQUENTIAL Batched CI Runner Summary ===
Execution Time: $timestamp
Light Mode: ENABLED
Sequential Execution: File-by-file to prevent stalls

Overall Results:
  Total Tests: $($overallResults.totalTests)
  Passed: $($overallResults.totalPassed)
  Failed: $($overallResults.totalFailed)
  Success Rate: ${successRate}%

Batch Details:
"@

foreach ($batchName in $overallResults.batchSummary.Keys) {
    $batch = $overallResults.batchSummary[$batchName]
    $batchRate = if ($batch.total -gt 0) { [math]::Round(($batch.passed / $batch.total) * 100, 1) } else { 0 }
    $duration = [math]::Round($batch.duration, 1)
    $summary += "`n  ${batchName}: $($batch.passed)/$($batch.total) passed (${batchRate}%) - ${duration}s"
    
    if ($batch.failedFiles.Count -gt 0) {
        $summary += "`n    Failed: $($batch.failedFiles -join ', ')"
    }
}

$summary += "`n`nArtifacts Generated:"
$summary += "`n  Combined JUnit XML: test_reports\junit\all.xml"
$summary += "`n  Individual JUnit XMLs: test_reports\junit\*.xml"
$summary += "`n  Logs: test_reports\logs\*"
if (-not $TestRun) {
    $summary += "`n  Coverage HTML: test_reports\coverage_html\index.html"
    $summary += "`n  Coverage XML: test_reports\coverage.xml"
}

$summary | Out-File "test_reports\logs\ci_sequential_summary.txt"
Write-Host "`n$summary" -ForegroundColor Cyan

# Final exit status
if ($overallResults.totalFailed -eq 0) {
    Write-Host "`nAll tests completed successfully!" -ForegroundColor Green
    exit 0
} else {
    Write-Host "`n$($overallResults.totalFailed) tests failed" -ForegroundColor Red
    exit 1
}
