Param(
  [switch]$WithCoverageJson
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$PSDefaultParameterValues['Out-File:Encoding'] = 'utf8'

Write-Host "Starting Batched CI Runner with Light Mode" -ForegroundColor Green
Write-Host "Working Directory: $(Get-Location)" -ForegroundColor Cyan

New-Item -ItemType Directory -Force -Path "test_reports","test_reports\junit","test_reports\coverage_html","test_reports\logs" | Out-Null

# Environment setup for Light Mode
$env:PYTHONFAULTHANDLER = "1"
$env:PYTHONUNBUFFERED   = "1"
$env:DISABLE_ML         = "1"    # hard block heavy imports
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

# Helper to run a batch and append coverage
function Invoke-TestBatch($batchName, $testArgs) {
    $junit = "test_reports\junit\$batchName.xml"
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    
    Write-Host "`n=== Running Batch: $batchName ===" -ForegroundColor Yellow
    Write-Host "Args: $($testArgs -join ' ')" -ForegroundColor Gray
    Write-Host "Time: $timestamp" -ForegroundColor Gray
    
    # Create batch-specific log
    "=== $batchName batch started at $timestamp ===" | Out-File "test_reports\logs\pytest_$batchName.log"
    
    # Use our light mode pytest wrapper for reliable execution
    $testCommand = "python pytest_light.py -q --maxfail=0 --disable-warnings --timeout=60 --junitxml $junit"
    $fullCommand = "$testCommand $($testArgs -join ' ')"
    
    Write-Host "Executing: $fullCommand" -ForegroundColor Cyan
    
    # Run with light mode wrapper (no parallel execution to avoid stalls)
    Invoke-Expression "$fullCommand 2>&1 | Add-Content test_reports\logs\pytest_$batchName.log"
    $testResult = $LASTEXITCODE
    
    # Coverage run with append (also using light mode)
    "=== $batchName coverage started ===" | Out-File "test_reports\logs\coverage_$batchName.log" -Append
    $coverageCommand = "coverage run --append -m pytest -q --maxfail=0 --disable-warnings --timeout=60"
    $fullCoverageCommand = "$coverageCommand $($testArgs -join ' ')"
    
    # Set light mode environment for coverage run too
    $env:DISABLE_ML = "1"
    $env:DISABLE_TORCH = "1"
    $env:DISABLE_TRANSFORMERS = "1"
    $env:PYTEST_RUNNING = "1"
    
    Write-Host "Coverage run for $batchName..." -ForegroundColor Magenta
    Invoke-Expression "$fullCoverageCommand 2>&1 | Add-Content test_reports\logs\coverage_$batchName.log"
    $coverageResult = $LASTEXITCODE
    
    # Log results
    $batchEnd = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "=== $batchName batch completed at $batchEnd (test: $testResult, coverage: $coverageResult) ===" | Out-File "test_reports\logs\pytest_$batchName.log" -Append
    
    if ($testResult -eq 0) {
        Write-Host "Batch ${batchName}: PASSED" -ForegroundColor Green
    } else {
        Write-Host "Batch ${batchName}: FAILED (exit code: $testResult)" -ForegroundColor Red
    }
}

# Batches optimized for our platform structure and Light Mode
Write-Host "`nConfiguring test batches..." -ForegroundColor Blue
$batches = @(
    @{ name="api";          args=@("tests/api") },
    @{ name="services";     args=@("tests/services") },
    @{ name="risk";         args=@("tests/risk") },
    @{ name="integration";  args=@("tests/integration","-k","not perf and not mlheavy") },
    @{ name="ws";           args=@("tests/ws","-k","not perf") },
    @{ name="mlops-core";   args=@("tests/mlops","-k","not mlheavy") },
    @{ name="unit-core";    args=@("tests/unit","-k","not perf and not mlheavy") }
)

Write-Host "Total batches configured: $($batches.Count)" -ForegroundColor Cyan

# Execute all batches
$batchResults = @{}
foreach ($b in $batches) {
    $startTime = Get-Date
    Invoke-TestBatch $b.name $b.args
    $endTime = Get-Date
    $duration = $endTime - $startTime
    $batchResults[$b.name] = @{
        duration = $duration.TotalSeconds
        exitCode = $LASTEXITCODE
    }
}

# Combine and generate coverage reports
Write-Host "`nGenerating combined coverage reports..." -ForegroundColor Blue
coverage combine 2>&1 | Out-File "test_reports\logs\coverage_combine.log"
coverage xml -o test_reports\coverage.xml 2>&1 | Add-Content "test_reports\logs\coverage_combine.log"
coverage html -d test_reports\coverage_html 2>&1 | Add-Content "test_reports\logs\coverage_combine.log"

if ($WithCoverageJson) { 
    try { 
        coverage json -o test_reports\coverage.json 2>&1 | Add-Content "test_reports\logs\coverage_combine.log"
        Write-Host "Coverage JSON generated" -ForegroundColor Green
    } catch { 
        "coverage json not available" | Out-File test_reports\logs\coverage_json_missing.txt 
        Write-Host "Coverage JSON not available" -ForegroundColor Yellow
    } 
}

# Generate comprehensive summary
Write-Host "`nGenerating final summary..." -ForegroundColor Blue
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

# Coverage summary
try {
    [xml]$c = Get-Content "test_reports\coverage.xml"
    $pct = [math]::Round([double]$c.coverage.'line-rate' * 100, 2)
    $coverageSummary = "Batched coverage line-rate: $pct%"
} catch {
    $coverageSummary = "Coverage data not available"
}

# Batch execution summary
$summary = @"
=== Batched CI Runner Summary ===
Execution Time: $timestamp
Light Mode: ENABLED
Environment: ML libraries disabled

Batch Results:
"@

foreach ($batch in $batches) {
    $name = $batch.name
    $result = $batchResults[$name]
    $status = if ($result.exitCode -eq 0) { "PASSED" } else { "FAILED ($($result.exitCode))" }
    $duration = [math]::Round($result.duration, 1)
    $summary += "`n  $name`: $status (${duration}s)"
}

$summary += "`n`nCoverage: $coverageSummary"
$summary += "`nReports: test_reports\coverage_html\index.html"
$summary += "`nJUnit XMLs: test_reports\junit\*.xml"
$summary += "`nLogs: test_reports\logs\*"

$summary | Out-File "test_reports\logs\ci_batched_summary.txt"
Write-Host "`n$summary" -ForegroundColor Cyan

# Final status
$failedBatches = $batchResults.GetEnumerator() | Where-Object { $_.Value.exitCode -ne 0 }
if ($failedBatches.Count -eq 0) {
    Write-Host "`nAll batches completed successfully!" -ForegroundColor Green
    exit 0
} else {
    Write-Host "`nSome batches failed:" -ForegroundColor Red
    foreach ($failed in $failedBatches) {
        Write-Host "  - $($failed.Name): exit code $($failed.Value.exitCode)" -ForegroundColor Red
    }
    exit 1
}
