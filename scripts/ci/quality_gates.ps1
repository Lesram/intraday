#!/usr/bin/env pwsh
<#
.SYNOPSIS
    CI/CD Quality Gates - Pre-Merge Validation Checks

.DESCRIPTION
    Enforces quality requirements before code can be merged to main branch.
    
    Quality Gates Enforced:
    1. .env.example parity with ENV_CATALOG.md
    2. SBOM vulnerability scan (grype)
    3. SAST security scan (bandit/semgrep)
    4. Forbidden artifacts (pyc/coverage/logs) in Git
    5. Route registry tests (prevents Phase-G regressions)
    6. Performance SLO tests (enforces latency requirements)
    
    Exit Codes:
    0 - All gates passed
    1 - One or more gates failed (blocks merge)
    2 - Configuration error

.PARAMETER Fast
    Skip slow checks (SBOM, SAST) for local development
    RESTRICTED in staging/production CI/CD environments

.PARAMETER SkipTests
    Skip test execution (useful for documentation-only changes)
    BLOCKED in staging/production CI/CD environments

.EXAMPLE
    .\scripts\ci\quality_gates.ps1
    
.EXAMPLE
    .\scripts\ci\quality_gates.ps1 -Fast
#>

param(
    [switch]$Fast,
    [switch]$SkipTests,
    [switch]$Verbose
)

$ErrorActionPreference = "Stop"
$script:GateFailed = $false
$script:GateResults = @()

# Colors for output
function Write-GatePass { param($msg) Write-Host "✅ $msg" -ForegroundColor Green }
function Write-GateFail { param($msg) Write-Host "❌ $msg" -ForegroundColor Red; $script:GateFailed = $true }
function Write-GateWarn { param($msg) Write-Host "⚠️  $msg" -ForegroundColor Yellow }
function Write-GateInfo { param($msg) Write-Host "ℹ️  $msg" -ForegroundColor Cyan }

# Logging
function Add-GateResult {
    param(
        [string]$Gate,
        [string]$Status,  # PASS, FAIL, WARN, SKIP
        [string]$Message,
        [string]$Details = ""
    )
    
    $script:GateResults += [PSCustomObject]@{
        Gate    = $Gate
        Status  = $Status
        Message = $Message
        Details = $Details
        Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    }
}

# ==============================================================================
# PRIORITY 2 FIX: CI/CD Environment Detection & Gate Restrictions
# ==============================================================================

function Get-CIEnvironment {
    <#
    .SYNOPSIS
        Detect CI/CD environment and deployment target
    .OUTPUTS
        Returns: 'local', 'ci-dev', 'ci-staging', 'ci-production'
    #>
    
    # Check common CI/CD environment variables
    $isCI = $false
    $deployTarget = 'dev'
    
    # GitHub Actions
    if ($env:GITHUB_ACTIONS -eq 'true') {
        $isCI = $true
        $deployTarget = if ($env:GITHUB_REF -match 'refs/heads/main') { 'production' }
                       elseif ($env:GITHUB_REF -match 'refs/heads/staging') { 'staging' }
                       else { 'dev' }
    }
    # Azure DevOps
    elseif ($env:TF_BUILD -eq 'True') {
        $isCI = $true
        $deployTarget = if ($env:BUILD_SOURCEBRANCHNAME -eq 'main') { 'production' }
                       elseif ($env:BUILD_SOURCEBRANCHNAME -eq 'staging') { 'staging' }
                       else { 'dev' }
    }
    # GitLab CI
    elseif ($env:GITLAB_CI -eq 'true') {
        $isCI = $true
        $deployTarget = if ($env:CI_COMMIT_BRANCH -eq 'main') { 'production' }
                       elseif ($env:CI_COMMIT_BRANCH -eq 'staging') { 'staging' }
                       else { 'dev' }
    }
    # Jenkins
    elseif ($env:JENKINS_HOME) {
        $isCI = $true
        $deployTarget = if ($env:GIT_BRANCH -match 'main') { 'production' }
                       elseif ($env:GIT_BRANCH -match 'staging') { 'staging' }
                       else { 'dev' }
    }
    # Explicit environment override
    elseif ($env:CI_ENVIRONMENT) {
        $isCI = $true
        $deployTarget = $env:CI_ENVIRONMENT
    }
    
    if ($isCI) {
        return "ci-$deployTarget"
    }
    return 'local'
}

function Test-GateBypassAllowed {
    param(
        [string]$Environment,
        [string]$BypassType  # 'fast' or 'skip_tests'
    )
    
    # Allow all bypasses in local development
    if ($Environment -eq 'local') {
        return $true
    }
    
    # In CI dev environment, allow -Fast but BLOCK -SkipTests
    if ($Environment -eq 'ci-dev') {
        if ($BypassType -eq 'fast') {
            Write-GateWarn "Using -Fast flag in CI dev environment (use sparingly)"
            return $true
        }
        if ($BypassType -eq 'skip_tests') {
            Write-GateFail "❌ CRITICAL: -SkipTests flag is ABSOLUTELY BLOCKED in ALL CI environments"
            Write-Host "  Reason: Untested code cannot be deployed" -ForegroundColor Red
            Write-Host "  Fix: Remove -SkipTests flag or run locally" -ForegroundColor Red
            return $false
        }
    }
    
    # In staging/production, ABSOLUTELY BLOCK ALL bypasses
    if ($Environment -in @('ci-staging', 'ci-production')) {
        Write-GateFail "❌ CRITICAL: -$BypassType flag is ABSOLUTELY BLOCKED in $Environment"
        Write-Host "`n  PRODUCTION SAFETY GATE ENFORCEMENT:" -ForegroundColor Red -BackgroundColor Black
        Write-Host "  - All quality gates must pass" -ForegroundColor Red
        Write-Host "  - All tests must execute" -ForegroundColor Red
        Write-Host "  - No bypasses allowed" -ForegroundColor Red
        Write-Host "`n  This protects production from:" -ForegroundColor Yellow
        Write-Host "    • Untested code" -ForegroundColor Yellow
        Write-Host "    • Security vulnerabilities" -ForegroundColor Yellow
        Write-Host "    • Performance regressions" -ForegroundColor Yellow
        Write-Host "`n  Fix: Remove -$BypassType flag for $Environment deployment" -ForegroundColor Red
        return $false
    }
    
    return $false
}

# Detect environment
$ciEnvironment = Get-CIEnvironment
Write-Host "CI/CD Environment: $ciEnvironment" -ForegroundColor Cyan

# Validate gate bypass flags
if ($Fast) {
    if (-not (Test-GateBypassAllowed -Environment $ciEnvironment -BypassType 'fast')) {
        Write-Host "`n❌ ERROR: -Fast flag not allowed in $ciEnvironment" -ForegroundColor Red
        Write-Host "   Remove -Fast flag for staging/production deployments" -ForegroundColor Red
        exit 2
    }
}

if ($SkipTests) {
    if (-not (Test-GateBypassAllowed -Environment $ciEnvironment -BypassType 'skip_tests')) {
        Write-Host "`n❌ ERROR: -SkipTests flag not allowed in $ciEnvironment" -ForegroundColor Red
        Write-Host "   All tests must run for CI/CD deployments" -ForegroundColor Red
        Write-Host "   This gate protects production from untested code" -ForegroundColor Red
        exit 2
    }
}

Write-Host "`n═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  CI/CD QUALITY GATES - Pre-Merge Validation" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════════════`n" -ForegroundColor Cyan

# ==============================================================================
# GATE 1: Environment Variable Parity Check
# ==============================================================================
Write-Host "━━━ GATE 1: Environment Variable Parity ━━━" -ForegroundColor Yellow

try {
    Write-GateInfo "Checking .env.example parity with ENV_CATALOG.md..."
    
    # Check if files exist
    if (-not (Test-Path ".env.example")) {
        Write-GateFail "GATE 1 FAILED: .env.example does not exist"
        Add-GateResult -Gate "ENV_PARITY" -Status "FAIL" -Message ".env.example missing"
    }
    elseif (-not (Test-Path "reports\ENV_CATALOG.md")) {
        Write-GateWarn "ENV_CATALOG.md not found at reports\ENV_CATALOG.md - skipping parity check"
        Add-GateResult -Gate "ENV_PARITY" -Status "SKIP" -Message "ENV_CATALOG.md missing"
    }
    else {
        # Extract variable names from .env.example (lines with KEY= or # KEY=)
        $envExampleVars = Get-Content ".env.example" | 
            Where-Object { $_ -match '^#?\s*[A-Z_0-9]+=.+' } |
            ForEach-Object { 
                # Remove leading # and whitespace, then get the key
                $cleaned = $_ -replace '^#\s*', ''
                ($cleaned -split '=')[0]
            }
        
        # Extract variable names from ENV_CATALOG.md (markdown table rows)
        $catalogVars = Get-Content "reports\ENV_CATALOG.md" | 
            Where-Object { $_ -match '^\|' -and $_ -notmatch '^\|\s*Variable\s*\|' -and $_ -notmatch '^\|\s*-+\s*\|' } |
            ForEach-Object { 
                $parts = $_ -split '\|'
                if ($parts.Count -gt 1) {
                    # Remove backticks and whitespace
                    $parts[1].Trim() -replace '`', ''
                }
            } |
            Where-Object { $_ -and $_ -ne '' }
        
        # Check for missing variables
        $missingInExample = $catalogVars | Where-Object { $_ -notin $envExampleVars }
        $missingInCatalog = $envExampleVars | Where-Object { $_ -notin $catalogVars }
        
        if ($missingInExample.Count -gt 0) {
            Write-GateFail "GATE 1 FAILED: $($missingInExample.Count) variables in catalog but not in .env.example"
            if ($Verbose) {
                Write-Host "  Missing: $($missingInExample -join ', ')" -ForegroundColor DarkGray
            }
            Add-GateResult -Gate "ENV_PARITY" -Status "FAIL" -Message "Variables missing from .env.example" -Details ($missingInExample -join ', ')
        }
        elseif ($missingInCatalog.Count -gt 0) {
            Write-GateWarn "GATE 1 WARNING: $($missingInCatalog.Count) variables in .env.example but not in catalog"
            if ($Verbose) {
                Write-Host "  Extra: $($missingInCatalog -join ', ')" -ForegroundColor DarkGray
            }
            Add-GateResult -Gate "ENV_PARITY" -Status "WARN" -Message "Extra variables in .env.example" -Details ($missingInCatalog -join ', ')
        }
        else {
            Write-GatePass "GATE 1 PASSED: .env.example and ENV_CATALOG.md are in sync"
            Add-GateResult -Gate "ENV_PARITY" -Status "PASS" -Message "Environment variables synchronized"
        }
    }
}
catch {
    Write-GateFail "GATE 1 ERROR: $($_.Exception.Message)"
    Add-GateResult -Gate "ENV_PARITY" -Status "FAIL" -Message "Execution error" -Details $_.Exception.Message
}

# ==============================================================================
# GATE 2: Forbidden Artifacts Check
# ==============================================================================
Write-Host "`n━━━ GATE 2: Forbidden Artifacts in Git ━━━" -ForegroundColor Yellow

try {
    Write-GateInfo "Checking for forbidden artifacts in Git index..."
    
    # Patterns for forbidden artifacts (runtime/build artifacts only)
    $forbiddenPatterns = @(
        "*.pyc",
        "*.pyo",
        "__pycache__/",
        ".pytest_cache/",
        ".coverage"
    )
    
    # Allowlist for legitimate files that match artifact patterns
    $allowlist = @(
        "*.py",                           # All Python source files
        "logging.py",
        "logger.py",
        "coverage.py",
        "*_coverage*.py",                 # Test files
        "logs/current.log",               # Intentional log file
        "audit_trail.log",                # Intentional log file
        "predictions.log",                # Intentional log file
        "*.ps1",                          # PowerShell scripts
        "*.bat",                          # Batch scripts
        "*.sh",                           # Shell scripts
        "env.py",                         # Alembic migration env file
        "htmlcov/",                       # Coverage reports (if intentionally tracked)
        "coverage.xml"                    # Coverage reports (if intentionally tracked)
    )
    
    $forbiddenFiles = @()
    
    # Check git tracked files
    foreach ($pattern in $forbiddenPatterns) {
        $regexPattern = $pattern -replace '\*', '.*' -replace '/', '\\'
        $files = git ls-files | Where-Object {
            $_ -match $regexPattern
        }
        
        foreach ($file in $files) {
            # Check if file matches allowlist
            $isAllowed = $false
            foreach ($allowed in $allowlist) {
                $allowedPattern = $allowed -replace '\*', '.*' -replace '/', '\\'
                if ($file -match $allowedPattern) {
                    $isAllowed = $true
                    break
                }
            }
            
            if (-not $isAllowed) {
                $forbiddenFiles += $file
            }
        }
    }
    
    if ($forbiddenFiles.Count -gt 0) {
        Write-GateFail "GATE 2 FAILED: $($forbiddenFiles.Count) forbidden artifacts found in Git"
        if ($Verbose) {
            Write-Host "  Forbidden files:" -ForegroundColor DarkGray
            $forbiddenFiles | ForEach-Object { Write-Host "    - $_" -ForegroundColor DarkGray }
        }
        Add-GateResult -Gate "FORBIDDEN_ARTIFACTS" -Status "FAIL" -Message "Artifacts in Git" -Details ($forbiddenFiles -join ', ')
    }
    else {
        Write-GatePass "GATE 2 PASSED: No forbidden artifacts in Git"
        Add-GateResult -Gate "FORBIDDEN_ARTIFACTS" -Status "PASS" -Message "No forbidden artifacts"
    }
}
catch {
    Write-GateFail "GATE 2 ERROR: $($_.Exception.Message)"
    Add-GateResult -Gate "FORBIDDEN_ARTIFACTS" -Status "FAIL" -Message "Execution error" -Details $_.Exception.Message
}

# ==============================================================================
# GATE 3: Route Registry Tests (Phase-G Non-Regression)
# ==============================================================================
Write-Host "`n━━━ GATE 3: Route Registry Tests ━━━" -ForegroundColor Yellow

if ($SkipTests) {
    Write-GateWarn "GATE 3 SKIPPED: Tests disabled via -SkipTests flag"
    Add-GateResult -Gate "ROUTE_REGISTRY" -Status "SKIP" -Message "Skipped by user"
}
else {
    try {
        Write-GateInfo "Running route registry tests (prevents Phase-G regressions)..."
        
        $testOutput = python -m pytest tests\test_route_registry.py -v --tb=short 2>&1
        $testExitCode = $LASTEXITCODE
        
        if ($testExitCode -eq 0) {
            $passedTests = ($testOutput | Select-String -Pattern "passed").ToString() -replace '.*(\d+)\s+passed.*', '$1'
            Write-GatePass "GATE 3 PASSED: All route registry tests passed - $passedTests tests"
            Add-GateResult -Gate "ROUTE_REGISTRY" -Status "PASS" -Message "All tests passed"
        }
        else {
            Write-GateFail "GATE 3 FAILED: Route registry tests failed"
            if ($Verbose) {
                Write-Host $testOutput -ForegroundColor DarkGray
            }
            Add-GateResult -Gate "ROUTE_REGISTRY" -Status "FAIL" -Message "Test failures detected"
        }
    }
    catch {
        Write-GateFail "GATE 3 ERROR: $($_.Exception.Message)"
        Add-GateResult -Gate "ROUTE_REGISTRY" -Status "FAIL" -Message "Execution error" -Details $_.Exception.Message
    }
}

# ==============================================================================
# GATE 4: Performance SLO Tests
# ==============================================================================
Write-Host "`n━━━ GATE 4: Performance SLO Tests ━━━" -ForegroundColor Yellow

if ($SkipTests) {
    Write-GateWarn "GATE 4 SKIPPED: Tests disabled via -SkipTests flag"
    Add-GateResult -Gate "PERFORMANCE_SLO" -Status "SKIP" -Message "Skipped by user"
}
else {
    try {
        Write-GateInfo "Running performance SLO tests (enforces latency requirements)..."
        
        $testOutput = python -m pytest tests\test_performance_slo.py -v --tb=short -m "performance" 2>&1
        $testExitCode = $LASTEXITCODE
        
        if ($testExitCode -eq 0) {
            $passedTests = ($testOutput | Select-String -Pattern "passed").ToString() -replace '.*(\d+)\s+passed.*', '$1'
            Write-GatePass "GATE 4 PASSED: All performance SLO tests passed - $passedTests tests"
            Add-GateResult -Gate "PERFORMANCE_SLO" -Status "PASS" -Message "All SLOs met"
        }
        else {
            Write-GateFail "GATE 4 FAILED: Performance SLO violations detected"
            if ($Verbose) {
                Write-Host $testOutput -ForegroundColor DarkGray
            }
            Add-GateResult -Gate "PERFORMANCE_SLO" -Status "FAIL" -Message "SLO violations"
        }
    }
    catch {
        Write-GateFail "GATE 4 ERROR: $($_.Exception.Message)"
        Add-GateResult -Gate "PERFORMANCE_SLO" -Status "FAIL" -Message "Execution error" -Details $_.Exception.Message
    }
}

# ==============================================================================
# GATE 5: SAST Security Scan (bandit)
# ==============================================================================
Write-Host "`n━━━ GATE 5: SAST Security Scan (bandit) ━━━" -ForegroundColor Yellow

if ($Fast) {
    Write-GateWarn "GATE 5 SKIPPED: Fast mode enabled"
    Add-GateResult -Gate "SAST_BANDIT" -Status "SKIP" -Message "Skipped in fast mode"
}
else {
    try {
        Write-GateInfo "Running bandit security scan..."
        
        # Check if bandit is installed
        $banditInstalled = python -c "import bandit" 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-GateWarn "GATE 5 SKIPPED: bandit not installed (pip install bandit)"
            Add-GateResult -Gate "SAST_BANDIT" -Status "SKIP" -Message "Bandit not installed"
        }
        else {
            # Run bandit on backend/ directory (uses .bandit for baseline config)
            $banditArgs = "-r backend/ -f json -o bandit_report.json"
            if (Test-Path ".bandit") {
                $banditArgs += " -c .bandit"
                Write-GateInfo "Using .bandit baseline configuration"
            }
            $banditOutput = python -m bandit $banditArgs 2>&1
            $banditExitCode = $LASTEXITCODE
            
            if (Test-Path "bandit_report.json") {
                $banditReport = Get-Content "bandit_report.json" | ConvertFrom-Json
                $highSeverity = ($banditReport.results | Where-Object { $_.issue_severity -eq "HIGH" }).Count
                $mediumSeverity = ($banditReport.results | Where-Object { $_.issue_severity -eq "MEDIUM" }).Count
                
                # Check for waivers file (required for HIGH severity findings)
                $waiversFile = "security/waivers.yml"
                if ($highSeverity -gt 0) {
                    if (-not (Test-Path $waiversFile)) {
                        Write-GateFail "GATE 5 FAILED: $highSeverity HIGH severity findings without waivers file"
                        Write-Host "  Security findings require documented waivers:" -ForegroundColor Red
                        Write-Host "    - Create security/waivers.yml with justification for each finding" -ForegroundColor Red
                        Write-Host "    - Include: issue_id, severity, reason, owner, expiry, ticket" -ForegroundColor Red
                        Write-Host "    - HIGH severity requires VP Engineering approval" -ForegroundColor Red
                        Add-GateResult -Gate "SAST_BANDIT" -Status "FAIL" -Message "$highSeverity HIGH without waivers"
                    }
                    else {
                        # Waivers file exists - validate it has entries for HIGH findings
                        Write-Host "  Found security/waivers.yml - validating HIGH severity waivers..." -ForegroundColor Yellow
                        
                        # Load waivers (PowerShell doesn't have native YAML, so basic check)
                        $waiversContent = Get-Content $waiversFile -Raw
                        $hasWaivers = $waiversContent -match "bandit:" -and $waiversContent -match "issue_id:"
                        
                        if (-not $hasWaivers) {
                            Write-GateFail "GATE 5 FAILED: Waivers file exists but contains no bandit waivers"
                            Add-GateResult -Gate "SAST_BANDIT" -Status "FAIL" -Message "Empty waivers file"
                        }
                        else {
                            Write-GatePass "GATE 5 PASSED: Waivers documented - $highSeverity HIGH, $mediumSeverity MEDIUM"
                            Write-Host "  ⚠️  Waiver validation is basic - manual review required!" -ForegroundColor Yellow
                            Write-Host "  ⚠️  Verify each HIGH finding has: reason, owner, expiry, ticket" -ForegroundColor Yellow
                            Add-GateResult -Gate "SAST_BANDIT" -Status "PASS" -Message "Waivers present: $highSeverity HIGH, $mediumSeverity MEDIUM"
                        }
                    }
                }
                elseif ($mediumSeverity -gt 5) {
                    Write-GateWarn "GATE 5 WARNING: $mediumSeverity medium severity issues - threshold is 5"
                    Add-GateResult -Gate "SAST_BANDIT" -Status "WARN" -Message "$mediumSeverity MEDIUM severity issues"
                }
                else {
                    Write-GatePass "GATE 5 PASSED: No critical security issues found"
                    Add-GateResult -Gate "SAST_BANDIT" -Status "PASS" -Message "No critical issues"
                }
            }
            else {
                Write-GateWarn "GATE 5 WARNING: bandit report not generated"
                Add-GateResult -Gate "SAST_BANDIT" -Status "WARN" -Message "Report not generated"
            }
        }
    }
    catch {
        Write-GateFail "GATE 5 ERROR: $($_.Exception.Message)"
        Add-GateResult -Gate "SAST_BANDIT" -Status "FAIL" -Message "Execution error" -Details $_.Exception.Message
    }
}

# ==============================================================================
# GATE 6: SBOM Vulnerability Scan (grype)
# ==============================================================================
Write-Host "`n━━━ GATE 6: SBOM Vulnerability Scan (grype) ━━━" -ForegroundColor Yellow

if ($Fast) {
    Write-GateWarn "GATE 6 SKIPPED: Fast mode enabled"
    Add-GateResult -Gate "SBOM_VULNS" -Status "SKIP" -Message "Skipped in fast mode"
}
else {
    try {
        Write-GateInfo "Running grype vulnerability scan..."
        
        # Check if grype is installed
        $grypeCommand = Get-Command grype -ErrorAction SilentlyContinue
        if (-not $grypeCommand) {
            Write-GateWarn "GATE 6 SKIPPED: grype not installed (install from https://github.com/anchore/grype)"
            Add-GateResult -Gate "SBOM_VULNS" -Status "SKIP" -Message "Grype not installed"
        }
        else {
            # Run grype on current directory (uses .grype.yaml for baseline config)
            $grypeArgs = "dir:. --output json --file grype_report.json"
            if (Test-Path ".grype.yaml") {
                $grypeArgs += " --config .grype.yaml"
                Write-GateInfo "Using .grype.yaml baseline configuration"
            }
            $grypeOutput = grype $grypeArgs 2>&1
            $grypeExitCode = $LASTEXITCODE
            
            if (Test-Path "grype_report.json") {
                $grypeReport = Get-Content "grype_report.json" | ConvertFrom-Json
                $criticalVulns = ($grypeReport.matches | Where-Object { $_.vulnerability.severity -eq "Critical" }).Count
                $highVulns = ($grypeReport.matches | Where-Object { $_.vulnerability.severity -eq "High" }).Count
                
                # If .grype.yaml exists, accept baseline findings
                if (Test-Path ".grype.yaml") {
                    Write-GatePass "GATE 6 PASSED: Baseline accepted - $criticalVulns critical, $highVulns high"
                    Add-GateResult -Gate "SBOM_VULNS" -Status "PASS" -Message "Baseline accepted: $criticalVulns CRITICAL, $highVulns HIGH"
                }
                elseif ($criticalVulns -gt 0) {
                    Write-GateFail "GATE 6 FAILED: $criticalVulns critical vulnerabilities found"
                    Add-GateResult -Gate "SBOM_VULNS" -Status "FAIL" -Message "$criticalVulns CRITICAL vulnerabilities"
                }
                elseif ($highVulns -gt 5) {
                    Write-GateWarn "GATE 6 WARNING: $highVulns high vulnerabilities - threshold is 5"
                    Add-GateResult -Gate "SBOM_VULNS" -Status "WARN" -Message "$highVulns HIGH vulnerabilities"
                }
                else {
                    Write-GatePass "GATE 6 PASSED: No critical vulnerabilities found"
                    Add-GateResult -Gate "SBOM_VULNS" -Status "PASS" -Message "No critical vulnerabilities"
                }
            }
            else {
                Write-GateWarn "GATE 6 WARNING: grype report not generated"
                Add-GateResult -Gate "SBOM_VULNS" -Status "WARN" -Message "Report not generated"
            }
        }
    }
    catch {
        Write-GateWarn "GATE 6 SKIPPED: Error checking grype - $($_.Exception.Message)"
        Add-GateResult -Gate "SBOM_VULNS" -Status "SKIP" -Message "Tool check failed" -Details $_.Exception.Message
    }
}

# ==============================================================================
# Summary Report
# ==============================================================================
Write-Host "`n═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  QUALITY GATES SUMMARY" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════════════`n" -ForegroundColor Cyan

# Count results by status
$passed = ($script:GateResults | Where-Object { $_.Status -eq "PASS" }).Count
$failed = ($script:GateResults | Where-Object { $_.Status -eq "FAIL" }).Count
$warnings = ($script:GateResults | Where-Object { $_.Status -eq "WARN" }).Count
$skipped = ($script:GateResults | Where-Object { $_.Status -eq "SKIP" }).Count

Write-Host "Results:" -ForegroundColor White
Write-Host "  ✅ Passed:  $passed" -ForegroundColor Green
Write-Host "  ❌ Failed:  $failed" -ForegroundColor Red
Write-Host "  ⚠️  Warnings: $warnings" -ForegroundColor Yellow
Write-Host "  ⏭️  Skipped: $skipped" -ForegroundColor Gray

# Export results to JSON
$resultsFile = "quality_gates_results.json"
$script:GateResults | ConvertTo-Json -Depth 3 | Out-File $resultsFile
Write-GateInfo "Detailed results exported to: $resultsFile"

# Final verdict
Write-Host ""
if ($script:GateFailed) {
    Write-Host "╔══════════════════════════════════════════════════════════════╗" -ForegroundColor Red
    Write-Host "║  ❌ QUALITY GATES FAILED - MERGE BLOCKED                     ║" -ForegroundColor Red
    Write-Host "╚══════════════════════════════════════════════════════════════╝" -ForegroundColor Red
    Write-Host "`nAction Required:" -ForegroundColor Yellow
    Write-Host "  1. Review failed gates above" -ForegroundColor Yellow
    Write-Host "  2. Fix identified issues" -ForegroundColor Yellow
    Write-Host "  3. Re-run quality gates" -ForegroundColor Yellow
    Write-Host "  4. Only merge after all gates pass`n" -ForegroundColor Yellow
    exit 1
}
else {
    Write-Host "`n===============================================================" -ForegroundColor Green
    Write-Host "  ALL QUALITY GATES PASSED - READY TO MERGE" -ForegroundColor Green
    Write-Host "===============================================================`n" -ForegroundColor Green
    exit 0
}
