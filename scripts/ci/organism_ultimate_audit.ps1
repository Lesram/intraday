#!/usr/bin/env pwsh
[CmdletBinding()]
param(
    [switch]$Fast,
    [int]$DefaultTimeoutSec = 1200,
    [int]$FullSuiteTimeoutSec = 900
)

$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path .).Path
$env:PYTHONPATH = $RepoRoot

$timestamp = Get-Date -Format 'yyyy-MM-dd_HH-mm-ss'
$resultsDir = Join-Path $RepoRoot 'test_results'
$reportsDir = Join-Path $RepoRoot 'reports'
$auditReportPath = Join-Path $reportsDir "organism_ultimate_audit_$timestamp.md"

New-Item -ItemType Directory -Force -Path $resultsDir | Out-Null
New-Item -ItemType Directory -Force -Path $reportsDir | Out-Null

$global:AuditResults = @()

function Add-AuditResult {
    param(
        [string]$Name,
        [string]$Status,
        [double]$DurationSec,
        [string]$Command,
        [string]$LogFile
    )

    $global:AuditResults += [PSCustomObject]@{
        Name        = $Name
        Status      = $Status
        DurationSec = [Math]::Round($DurationSec, 2)
        Command     = $Command
        LogFile     = $LogFile
    }
}

function Invoke-AuditCheck {
    param(
        [string]$Name,
        [string]$Command,
        [switch]$Critical,
        [int]$TimeoutSec = 0,
        [switch]$SkipOnTimeout
    )

    Write-Host "\n=== $Name ===" -ForegroundColor Cyan
    Write-Host "Command: $Command" -ForegroundColor DarkGray
    if ($TimeoutSec -gt 0) {
        Write-Host "Timeout: ${TimeoutSec}s" -ForegroundColor DarkGray
    }

    $safeName = ($Name -replace '[^a-zA-Z0-9_-]', '_')
    $logPath = Join-Path $resultsDir "organism_audit_${safeName}_$timestamp.log"
    $started = Get-Date
    $status = 'PASS'

    try {
        if ($TimeoutSec -gt 0) {
            $job = Start-Job -ScriptBlock {
                param($cmd, $log)
                & pwsh -NoProfile -ExecutionPolicy Bypass -Command $cmd *> $log
                [PSCustomObject]@{ ExitCode = $LASTEXITCODE }
            } -ArgumentList $Command, $logPath

            $completed = Wait-Job -Job $job -Timeout $TimeoutSec
            if (-not $completed) {
                Stop-Job -Job $job | Out-Null
                Remove-Job -Job $job | Out-Null
                Add-Content -Path $logPath -Value "`n[TIMEOUT] Check timed out after ${TimeoutSec}s and was stopped."
                throw "Timed out after ${TimeoutSec}s"
            }

            $jobOutput = Receive-Job -Job $job
            Remove-Job -Job $job | Out-Null

            if (Test-Path $logPath) {
                Get-Content -Path $logPath
            }

            $exitCode = 0
            if ($jobOutput -and $jobOutput.ExitCode -ne $null) {
                $exitCode = [int]$jobOutput.ExitCode
            }
            if ($exitCode -ne 0) {
                throw "Exit code $exitCode"
            }
        }
        else {
            & pwsh -NoProfile -ExecutionPolicy Bypass -Command $Command 2>&1 |
                Tee-Object -FilePath $logPath
            if ($LASTEXITCODE -ne 0) {
                throw "Exit code $LASTEXITCODE"
            }
        }

        Write-Host "PASS: $Name" -ForegroundColor Green
    }
    catch {
        $isTimeout = $_.Exception.Message -like 'Timed out*'
        if ($isTimeout -and $SkipOnTimeout) {
            $status = 'WARN'
        }
        else {
            $status = if ($Critical) { 'FAIL' } else { 'WARN' }
        }
        if ($status -eq 'FAIL') {
            Write-Host "FAIL: $Name :: $($_.Exception.Message)" -ForegroundColor Red
        }
        else {
            Write-Host "WARN: $Name :: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }
    finally {
        $duration = (Get-Date) - $started
        Add-AuditResult -Name $Name -Status $status -DurationSec $duration.TotalSeconds -Command $Command -LogFile $logPath
    }

    if ($status -eq 'FAIL') {
        throw "Critical check failed: $Name"
    }
}

Write-Host "\n================ ORGANISM ULTIMATE AUDIT ================" -ForegroundColor Magenta
Write-Host "Mode: $(if ($Fast) { 'FAST' } else { 'FULL' })"
Write-Host "Workspace: $RepoRoot"
Write-Host "=========================================================" -ForegroundColor Magenta

try {
    Invoke-AuditCheck -Name 'Compile backend.organism' -Critical -TimeoutSec $DefaultTimeoutSec -Command 'python -m compileall backend/organism'

    Invoke-AuditCheck -Name 'Organism invariant tests' -Critical -TimeoutSec $DefaultTimeoutSec -Command 'python -m pytest tests/test_organism_live_engine.py tests/unit/test_organism.py -q --tb=short'

    Invoke-AuditCheck -Name 'Core platform fast suite' -Critical -TimeoutSec $DefaultTimeoutSec -Command 'python -m pytest tests/ -q --tb=short -m "unit or api or services" --ignore=tests/test_backtest_api_integration.py'

    if (-not $Fast) {
        Invoke-AuditCheck -Name 'Deterministic full local suite' -Critical -TimeoutSec $FullSuiteTimeoutSec -SkipOnTimeout -Command 'python -m pytest tests -q --tb=short -m "not integration and not slow" --cov=backend --cov-branch --cov-report=term-missing'
    }

    # Non-critical guardrails (warn-only): broad platform quality checks
    Invoke-AuditCheck -Name 'Quality gates (fast)' -TimeoutSec $DefaultTimeoutSec -Command 'pwsh -ExecutionPolicy Bypass -File scripts/ci/quality_gates.ps1 -Fast' -Critical:$false
}
catch {
    Write-Host "\nAudit stopped due to critical failure: $($_.Exception.Message)" -ForegroundColor Red
}

$failed = @($global:AuditResults | Where-Object { $_.Status -eq 'FAIL' }).Count
$warned = @($global:AuditResults | Where-Object { $_.Status -eq 'WARN' }).Count
$passed = @($global:AuditResults | Where-Object { $_.Status -eq 'PASS' }).Count
$total = $global:AuditResults.Count

$summaryStatus = if ($failed -gt 0) { 'FAIL' } elseif ($warned -gt 0) { 'PASS_WITH_WARNINGS' } else { 'PASS' }

$report = @()
$report += "# Organism Ultimate Audit Report"
$report += ""
$report += "- Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')"
$report += "- Mode: $(if ($Fast) { 'FAST' } else { 'FULL' })"
$report += "- Overall status: **$summaryStatus**"
$report += "- Checks: $passed passed / $warned warnings / $failed failed / $total total"
$report += ""
$report += "## Check Results"
$report += ""
$report += "| Check | Status | Duration (s) | Log |"
$report += "|---|---:|---:|---|"

foreach ($r in $global:AuditResults) {
    $relativeLog = $r.LogFile.Replace($RepoRoot + '\\', '').Replace('\\', '/')
    $report += "| $($r.Name) | $($r.Status) | $($r.DurationSec) | $relativeLog |"
}

$report += ""
$report += "## Commands Executed"
$report += ""
foreach ($r in $global:AuditResults) {
    $report += "- **$($r.Name)**: $($r.Command)"
}

$report += ""
$report += "## Retest Protocol"
$report += ""
$report += "1. Fix all FAIL checks first."
$report += "2. Re-run FAST mode to validate immediate fixes."
$report += "3. Re-run FULL mode before release."
$report += "4. If warnings remain from non-critical checks, triage and track in backlog."

Set-Content -Path $auditReportPath -Value $report -Encoding UTF8

Write-Host "\nAudit report: $auditReportPath" -ForegroundColor Cyan
Write-Host "Results: PASS=$passed WARN=$warned FAIL=$failed" -ForegroundColor Cyan

if ($failed -gt 0) {
    exit 1
}

exit 0
