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
"=== Pip Freeze ===" | Add-Content test_reports\logs\env.txt
pip list --format=freeze 2>&1 | Add-Content test_reports\logs\env.txt
"=== Git ===" | Add-Content test_reports\logs\env.txt
git rev-parse HEAD 2>&1 | Add-Content test_reports\logs\env.txt

# Pytest (JUnit)
$junitXml = "test_reports\junit\all.xml"
"=== Pytest (JUnit) ===" | Out-File test_reports\logs\pytest_console.log
python -m pytest -q --disable-warnings --durations=20 --junitxml $junitXml `
  2>&1 | Add-Content test_reports\logs\pytest_console.log
$testsExit = $LASTEXITCODE

# Coverage run (separate)
"=== Coverage run ===" | Out-File test_reports\logs\coverage_console.log
coverage run -m pytest -q --disable-warnings `
  2>&1 | Add-Content test_reports\logs\coverage_console.log
$covRunExit = $LASTEXITCODE

coverage xml -o test_reports\coverage.xml
coverage html -d test_reports\coverage_html
if ($WithCoverageJson) { try { coverage json -o test_reports\coverage.json } catch { "coverage json not available" | Out-File test_reports\logs\coverage_json_missing.txt } }

# Summary
[xml]$j = Get-Content $junitXml
$tests = [int]$j.testsuite.tests
$fail = [int]$j.testsuite.failures
$err  = [int]$j.testsuite.errors
$skip = [int]$j.testsuite.skipped

[xml]$c = Get-Content "test_reports\coverage.xml"
$pct = [math]::Round([double]$c.coverage.'line-rate' * 100, 2)

$summary = @"
=== SUMMARY ===
Tests total: $tests  Failures: $fail  Errors: $err  Skipped: $skip
Pytest exit (JUnit pass): $testsExit
Coverage line-rate: $pct%
Coverage run exit: $covRunExit
Artifacts:
 - test_reports\junit\all.xml
 - test_reports\coverage.xml
 - test_reports\coverage_html\index.html
 - test_reports\logs\pytest_console.log
 - test_reports\logs\coverage_console.log
 - test_reports\logs\env.txt
"@

$summary | Out-File "test_reports\logs\ci_full_summary.txt"

exit 0
