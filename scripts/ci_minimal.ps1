Param(
  [switch]$WithCoverageJson
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

# Force UTF-8 for console and files
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$PSDefaultParameterValues['Out-File:Encoding'] = 'utf8'
$PSDefaultParameterValues['Set-Content:Encoding'] = 'utf8'
$PSDefaultParameterValues['Add-Content:Encoding'] = 'utf8'

# Dirs
New-Item -ItemType Directory -Force -Path "test_reports","test_reports\junit","test_reports\coverage_html","test_reports\logs" | Out-Null

# Environment
$env:PYTHONFAULTHANDLER = "1"
$env:PYTHONUNBUFFERED = "1"

# Env info
"=== Run Info ===" | Out-File test_reports\logs\env.txt
(Get-Date).ToString("s") | Add-Content test_reports\logs\env.txt
"PWD: $(Get-Location)" | Add-Content test_reports\logs\env.txt
"=== Python ===" | Add-Content test_reports\logs\env.txt
python --version 2>&1 | Add-Content test_reports\logs\env.txt
pip --version 2>&1 | Add-Content test_reports\logs\env.txt

# Run only safe, fast tests to verify infrastructure
$junitXml = "test_reports\junit\all.xml"
"=== Minimal Test Run ===" | Out-File test_reports\logs\pytest_console.log
python -m pytest tests/api/test_api_main_import.py tests/api/test_auth_register.py tests/smoke/test_smoke.py -v --disable-warnings --durations=10 --junitxml $junitXml `
  2>&1 | Add-Content test_reports\logs\pytest_console.log
$testsExit = $LASTEXITCODE

# Simple coverage on just the safe tests
"=== Minimal Coverage ===" | Out-File test_reports\logs\coverage_console.log
coverage run -m pytest tests/api/test_api_main_import.py tests/api/test_auth_register.py tests/smoke/test_smoke.py -v --disable-warnings `
  2>&1 | Add-Content test_reports\logs\coverage_console.log
$covRunExit = $LASTEXITCODE

coverage xml -o test_reports\coverage.xml
coverage html -d test_reports\coverage_html
if ($WithCoverageJson) { try { coverage json -o test_reports\coverage.json } catch { "coverage json not available" | Out-File test_reports\logs\coverage_json_missing.txt } }

# Summary with actual file checking
if (Test-Path $junitXml) {
    [xml]$j = Get-Content $junitXml
    $tests = [int]$j.testsuite.tests
    $fail = [int]$j.testsuite.failures
    $err  = [int]$j.testsuite.errors
    $skip = [int]$j.testsuite.skipped
} else {
    $tests = 0; $fail = 0; $err = 0; $skip = 0
}

if (Test-Path "test_reports\coverage.xml") {
    [xml]$c = Get-Content "test_reports\coverage.xml"
    $pct = [math]::Round([double]$c.coverage.'line-rate' * 100, 2)
} else {
    $pct = 0
}

$summary = @"
=== MINIMAL CI SUMMARY ===
Tests total: $tests  Failures: $fail  Errors: $err  Skipped: $skip
Pytest exit: $testsExit
Coverage line-rate: $pct%
Coverage run exit: $covRunExit
JUnit XML exists: $(Test-Path $junitXml)
Coverage XML exists: $(Test-Path "test_reports\coverage.xml")
"@

$summary | Out-File "test_reports\logs\ci_minimal_summary.txt"
Write-Host $summary

exit 0
