[CmdletBinding()]
param(
    [switch]$Fast
)

$ErrorActionPreference = 'Stop'

# Ensure we run from repo root
$RepoRoot = (Resolve-Path .).Path
$env:PYTHONPATH = $RepoRoot

$timestamp = Get-Date -Format 'yyyy-MM-dd_HH-mm-ss'
$resultsDir = Join-Path $RepoRoot 'test_results'
$reportsDir = Join-Path $RepoRoot 'reports'
$coverageHtmlDir = Join-Path $resultsDir 'coverage_html'

New-Item -ItemType Directory -Force -Path $resultsDir | Out-Null
New-Item -ItemType Directory -Force -Path $reportsDir | Out-Null
New-Item -ItemType Directory -Force -Path $coverageHtmlDir | Out-Null

$logPath = Join-Path $resultsDir "pytest_$timestamp.log"
$junitPath = Join-Path $resultsDir "junit_$timestamp.xml"

$pytestArgs = @(
    '-m', 'pytest'
)

if ($Fast) {
    Write-Host "Running FAST pytest suite (markers: unit or api or services)..." -ForegroundColor Cyan
    $pytestArgs += @(
        '-q',
        '-m', 'unit or api or services',
        '--cov=backend',
        '--cov-branch',
        '--cov-report=term-missing:skip-covered',
        "--cov-report=html:$coverageHtmlDir",
        '--maxfail=5',
        '--tb=short',
        "--junitxml=$junitPath"
    )
}
else {
    Write-Host "Running FULL pytest suite..." -ForegroundColor Cyan
    $pytestArgs += @(
        '-q',
        '--cov=backend',
        '--cov-branch',
        '--cov-report=term-missing',
        "--cov-report=html:$coverageHtmlDir",
        '--tb=short',
        "--junitxml=$junitPath"
    )
}

Write-Host "PYTHONPATH=$env:PYTHONPATH" -ForegroundColor DarkGray
Write-Host "Writing log to $logPath" -ForegroundColor DarkGray

# Run pytest and tee output to a log file.
& python @pytestArgs 2>&1 | Tee-Object -FilePath $logPath

Write-Host "Done. JUnit: $junitPath" -ForegroundColor Green
Write-Host "Coverage HTML: $coverageHtmlDir" -ForegroundColor Green
Write-Host "Log: $logPath" -ForegroundColor Green
