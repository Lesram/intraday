<#
.SYNOPSIS
    Comprehensive cleanup script for the algotrading platform root directory.

.DESCRIPTION
    This script:
    - Archives obsolete debug/check/verify scripts
    - Moves valid test files to tests/
    - Deletes temporary and generated files
    - Consolidates the test directory structure
    - Fixes pytest configuration

.PARAMETER DryRun
    Preview changes without making modifications

.PARAMETER Force
    Skip confirmation prompts

.EXAMPLE
    .\cleanup_root_files.ps1 -DryRun
    .\cleanup_root_files.ps1 -Force
#>

param(
    [switch]$DryRun,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$timestamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$archiveDir = "archive\root_scripts_$timestamp"

# Color output functions
function Write-Info { param($Message) Write-Host "[INFO] $Message" -ForegroundColor Cyan }
function Write-Action { param($Message) Write-Host "[ACTION] $Message" -ForegroundColor Yellow }
function Write-Success { param($Message) Write-Host "[SUCCESS] $Message" -ForegroundColor Green }
function Write-Skip { param($Message) Write-Host "[SKIP] $Message" -ForegroundColor DarkGray }

# =============================================================================
# FILE CATEGORIES
# =============================================================================

# Files to DELETE (temporary, generated, one-time)
$deletePatterns = @(
    # Prerun test results
    "prerun_test_results_*.json",
    # Generated files
    "openapi_temp.json",
    "k6-summary.json",
    "comprehensive_test_results.log",
    "edge_case_test_results.*",
    "phase1_test_*.log",
    "phase2_test_*.log",
    "quality_gates_results.json",
    # SQLite databases (migrated to PostgreSQL)
    "staging.db",
    "trading_paper.db",
    "trading_platform.db",
    "test_trading_platform.db",
    "*.db-journal",
    # Token files
    "token.txt",
    # Log files in root
    "*.log",
    # The mysterious "500" file
    "500"
)

# Files to ARCHIVE (one-time scripts with reference value)
$archivePatterns = @(
    # Check scripts
    "check_*.py",
    # Debug scripts  
    "debug_*.py",
    # Verify scripts
    "verify_*.py",
    # Analyze scripts
    "analyze_*.py",
    # Investigate scripts
    "investigate_*.py",
    # Diagnose scripts
    "diagnose_*.py",
    # Audit scripts (except the audit report)
    "audit_*.py",
    # Migration scripts
    "migrate_*.py",
    # Fix scripts
    "fix_*.py",
    # Clear/cleanup scripts
    "clear_*.py",
    "cleanup_*.py",
    # Apply scripts
    "apply_*.py",
    # Reconcile/resolve scripts
    "reconcile_*.py",
    "resolve_*.py",
    # Import/populate scripts
    "import_*.py",
    "populate_*.py",
    # Mark/update scripts
    "mark_*.py",
    "update_*.py",
    # Explain/deep analysis
    "explain_*.py",
    "deep_analysis.py",
    # Cancel/delete scripts
    "cancel_*.py",
    "delete_*.py",
    # Decode/get scripts
    "decode_*.py",
    "get_strategy*.py",
    # List/seed/setup scripts
    "list_*.py",
    "seed_*.py",
    "setup_test_*.py"
)

# Root test files to MOVE to tests/
$moveToTests = @(
    "test_analytics_api_full.py",
    "test_analytics_diagnostic.py",
    "test_analytics_endpoint.py",
    "test_api_endpoint_validation.py",
    "test_edge_cases_automated.py",
    "test_order_submission.py",
    "test_order_validation.py",
    "test_orders_api.py",
    "test_portfolio_api.py",
    "test_position_management.py",
    "test_position_reconciliation.py",
    "test_pretrade_validation.py",
    "test_real_data_integration.py",
    "test_risk_api.py",
    "test_strategies_automated_suite.py",
    "test_trades_api.py",
    "test_websocket_api.py"
)

# Root test files to ARCHIVE (phase-specific, obsolete)
$archiveTests = @(
    "test_phase*.py",
    "test_8_strategy_types_api.py",
    "test_alpaca_sync.py",
    "test_auth_diagnostic.py",
    "test_close_position_direct.py",
    "test_create_strategy.py",
    "test_database_config.py",
    "test_db_connection.py",
    "test_direct_db.py",
    "test_endpoint_fix.py",
    "test_estimated_cost_fix.py",
    "test_lifespan.py",
    "test_login.ps1",
    "test_outbox_fix.py",
    "test_portfolio_fix.py",
    "test_simple_strategy_create.py",
    "test_socketio.py",
    "test_socketio_lifespan.py",
    "test_strategy_templates.py",
    "test_template_options.py",
    "test_trade_history*.py",
    "test_validation*.py",
    "test_websocket_http.py",
    "test_websocket_updates.py",
    "validate_*.py",
    "automated_backend_tests.py",
    "run_phase_tests.py"
)

# Files to KEEP in root
$keepFiles = @(
    "main.py",
    "start_backend.py",
    "deploy*.ps1",
    "deploy*.sh",
    "Makefile",
    "alembic.ini",
    "pytest.ini",
    "pyproject.toml",
    "ruff.toml",
    "requirements*.txt",
    "requirements.lock",
    "logging_config.yaml",
    "Dockerfile*",
    "docker-compose*.yml",
    ".env*",
    "*.md",
    ".gitignore",
    ".pre-commit-config.yaml",
    ".grype.yaml",
    ".bandit",
    "final_trading_strategies_100.json"
)

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

function Get-MatchingFiles {
    param([string[]]$Patterns)
    
    $files = @()
    foreach ($pattern in $Patterns) {
        $matches = Get-ChildItem -Path . -Filter $pattern -File -ErrorAction SilentlyContinue
        $files += $matches
    }
    return $files | Select-Object -Unique
}

function Should-KeepFile {
    param([string]$FileName)
    
    foreach ($pattern in $keepFiles) {
        if ($FileName -like $pattern) {
            return $true
        }
    }
    return $false
}

# =============================================================================
# MAIN EXECUTION
# =============================================================================

Write-Host ""
Write-Host "========================================" -ForegroundColor Magenta
Write-Host "  Algotrading Platform Root Cleanup" -ForegroundColor Magenta
Write-Host "========================================" -ForegroundColor Magenta
Write-Host ""

if ($DryRun) {
    Write-Host "[DRY RUN MODE - No changes will be made]" -ForegroundColor Yellow
    Write-Host ""
}

# Count initial state
$initialCount = (Get-ChildItem -Path . -Filter "*.py" -File | Where-Object { $_.DirectoryName -eq (Get-Location).Path }).Count
Write-Info "Found $initialCount Python files in root directory"
Write-Host ""

# Confirmation
if (-not $DryRun -and -not $Force) {
    $confirm = Read-Host "This will archive/delete/move files. Continue? (y/N)"
    if ($confirm -ne 'y' -and $confirm -ne 'Y') {
        Write-Info "Cancelled."
        exit 0
    }
}

# Create archive directory
if (-not $DryRun) {
    New-Item -ItemType Directory -Path $archiveDir -Force | Out-Null
    Write-Info "Created archive directory: $archiveDir"
}

# =============================================================================
# PHASE 1: DELETE temporary/generated files
# =============================================================================

Write-Host ""
Write-Host "--- Phase 1: Deleting Temporary Files ---" -ForegroundColor Cyan

$deleteFiles = Get-MatchingFiles -Patterns $deletePatterns
$deleteCount = 0

foreach ($file in $deleteFiles) {
    if ($DryRun) {
        Write-Action "Would DELETE: $($file.Name)"
    } else {
        Remove-Item $file.FullName -Force
        Write-Success "Deleted: $($file.Name)"
    }
    $deleteCount++
}

Write-Info "Phase 1 complete: $deleteCount files to delete"

# =============================================================================
# PHASE 2: ARCHIVE obsolete scripts
# =============================================================================

Write-Host ""
Write-Host "--- Phase 2: Archiving Obsolete Scripts ---" -ForegroundColor Cyan

$archiveFiles = Get-MatchingFiles -Patterns $archivePatterns
$archiveCount = 0

foreach ($file in $archiveFiles) {
    if (Should-KeepFile -FileName $file.Name) {
        Write-Skip "Keeping: $($file.Name)"
        continue
    }
    
    if ($DryRun) {
        Write-Action "Would ARCHIVE: $($file.Name)"
    } else {
        Move-Item $file.FullName -Destination $archiveDir -Force
        Write-Success "Archived: $($file.Name)"
    }
    $archiveCount++
}

# Archive obsolete test files
$archiveTestFiles = Get-MatchingFiles -Patterns $archiveTests
foreach ($file in $archiveTestFiles) {
    if ($DryRun) {
        Write-Action "Would ARCHIVE (test): $($file.Name)"
    } else {
        Move-Item $file.FullName -Destination $archiveDir -Force
        Write-Success "Archived (test): $($file.Name)"
    }
    $archiveCount++
}

Write-Info "Phase 2 complete: $archiveCount files archived"

# =============================================================================
# PHASE 3: MOVE valid tests to tests/
# =============================================================================

Write-Host ""
Write-Host "--- Phase 3: Moving Valid Tests ---" -ForegroundColor Cyan

$moveCount = 0

foreach ($testFile in $moveToTests) {
    if (Test-Path $testFile) {
        $destPath = "tests\$testFile"
        
        if (Test-Path $destPath) {
            if ($DryRun) {
                Write-Skip "Would skip (exists in tests/): $testFile"
            } else {
                Move-Item $testFile -Destination $archiveDir -Force
                Write-Info "Moved to archive (exists in tests/): $testFile"
            }
        } else {
            if ($DryRun) {
                Write-Action "Would MOVE to tests/: $testFile"
            } else {
                Move-Item $testFile -Destination "tests\" -Force
                Write-Success "Moved to tests/: $testFile"
            }
        }
        $moveCount++
    }
}

Write-Info "Phase 3 complete: $moveCount test files processed"

# =============================================================================
# PHASE 4: Fix pytest.ini
# =============================================================================

Write-Host ""
Write-Host "--- Phase 4: Fixing pytest.ini ---" -ForegroundColor Cyan

$pytestIni = Get-Content "pytest.ini" -Raw
if ($pytestIni -match 'testpaths = test\b') {
    if ($DryRun) {
        Write-Action "Would update pytest.ini: testpaths = test -> testpaths = tests"
    } else {
        $newContent = $pytestIni -replace 'testpaths = test\b', 'testpaths = tests'
        Set-Content "pytest.ini" -Value $newContent
        Write-Success "Updated pytest.ini: testpaths now points to tests/"
    }
} else {
    Write-Skip "pytest.ini already configured correctly"
}

# =============================================================================
# PHASE 5: Merge test/ into tests/
# =============================================================================

Write-Host ""
Write-Host "--- Phase 5: Merging test/ into tests/ ---" -ForegroundColor Cyan

if (Test-Path "test") {
    $testFiles = Get-ChildItem -Path "test" -Filter "*.py" -File
    foreach ($file in $testFiles) {
        if ($file.Name -eq "__init__.py" -or $file.Name -eq "conftest.py") {
            Write-Skip "Skipping: test/$($file.Name)"
            continue
        }
        
        $destPath = "tests\$($file.Name)"
        if (Test-Path $destPath) {
            Write-Skip "Already exists: tests/$($file.Name)"
        } else {
            if ($DryRun) {
                Write-Action "Would MOVE: test/$($file.Name) -> tests/"
            } else {
                Move-Item $file.FullName -Destination "tests\" -Force
                Write-Success "Moved: test/$($file.Name) -> tests/"
            }
        }
    }
    
    # Move test/module/ if exists
    if (Test-Path "test\module") {
        if (-not (Test-Path "tests\module")) {
            if ($DryRun) {
                Write-Action "Would MOVE: test/module/ -> tests/module/"
            } else {
                Move-Item "test\module" -Destination "tests\" -Force
                Write-Success "Moved: test/module/ -> tests/module/"
            }
        }
    }
}

# =============================================================================
# SUMMARY
# =============================================================================

Write-Host ""
Write-Host "========================================" -ForegroundColor Magenta
Write-Host "  Cleanup Summary" -ForegroundColor Magenta
Write-Host "========================================" -ForegroundColor Magenta
Write-Host ""

$finalCount = (Get-ChildItem -Path . -Filter "*.py" -File | Where-Object { $_.DirectoryName -eq (Get-Location).Path }).Count

if ($DryRun) {
    Write-Host "[DRY RUN] No changes were made" -ForegroundColor Yellow
    Write-Host ""
    Write-Info "Would reduce root Python files from $initialCount to approximately $($initialCount - $deleteCount - $archiveCount - $moveCount)"
} else {
    Write-Success "Cleanup complete!"
    Write-Info "Root Python files: $initialCount -> $finalCount"
    Write-Info "Files deleted: $deleteCount"
    Write-Info "Files archived: $archiveCount (in $archiveDir)"
    Write-Info "Test files moved: $moveCount"
}

Write-Host ""
Write-Host "Remaining files in root:" -ForegroundColor Cyan
Get-ChildItem -Path . -Filter "*.py" -File | Where-Object { $_.DirectoryName -eq (Get-Location).Path } | Select-Object Name | Format-Table -AutoSize
