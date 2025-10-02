<![CDATA[# Platform Cleanup Script
# Purpose: Automate Phase 1 & 2 cleanup from audit report
# Safety: Creates archives instead of deleting permanently

param(
    [switch]$DryRun,
    [switch]$SkipBackup
)

$ErrorActionPreference = "Stop"

Write-Host @"

╔════════════════════════════════════════════════════════╗
║                                                        ║
║     🧹 PLATFORM CLEANUP SCRIPT                         ║
║     Pre-Deployment Organization                        ║
║                                                        ║
╚════════════════════════════════════════════════════════╝

"@ -ForegroundColor Cyan

if ($DryRun) {
    Write-Host "🔍 DRY RUN MODE - No files will be modified" -ForegroundColor Yellow
    Write-Host ""
}

# Backup current state (unless skipped)
if (!$SkipBackup -and !$DryRun) {
    Write-Host "💾 Creating backup..." -ForegroundColor Cyan
    $backupName = "platform_backup_$(Get-Date -Format 'yyyyMMdd_HHmmss').zip"
    $itemsToBackup = @(
        "*.py", "*.js", "*.json", "*.md", "*.db", "*.ps1", "*.sh", "*.bat"
    ) | ForEach-Object { Get-ChildItem -Filter $_ -ErrorAction SilentlyContinue }
    
    if ($itemsToBackup.Count -gt 0) {
        Compress-Archive -Path $itemsToBackup -DestinationPath "backups/$backupName" -Force
        Write-Host "✅ Backup created: backups/$backupName" -ForegroundColor Green
    }
}

# Track statistics
$stats = @{
    FilesDeleted = 0
    FilesArchived = 0
    DirectoriesCreated = 0
    SpaceSaved = 0
}

# =============================================================================
# Phase 1: Create Archive Directories
# =============================================================================

Write-Host "`n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Blue
Write-Host "📁 PHASE 1: Creating Archive Structure" -ForegroundColor Blue
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Blue

$archiveDirs = @(
    "archive/validation_tests",
    "archive/debug_scripts",
    "archive/validation_scripts",
    "archive/old_ci_scripts",
    "archive/old_test_scripts",
    "archive/old_backups",
    "archive/reports",
    "docs/testing",
    "docs/deployment",
    "docs/reports/phases",
    "docs/integration",
    "docs/ai"
)

foreach ($dir in $archiveDirs) {
    if (!(Test-Path $dir)) {
        if (!$DryRun) {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
            $stats.DirectoriesCreated++
        }
        Write-Host "  ✅ Created: $dir" -ForegroundColor Green
    } else {
        Write-Host "  ⏭️  Exists: $dir" -ForegroundColor Gray
    }
}

# =============================================================================
# Phase 2: Delete Temporary Files
# =============================================================================

Write-Host "`n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Blue
Write-Host "🗑️  PHASE 2: Deleting Temporary Files" -ForegroundColor Blue
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Blue

# Prerun test results
Write-Host "`n  Prerun test results (*.json)..." -ForegroundColor Yellow
$prerunFiles = Get-ChildItem -Filter "prerun_test_results_*.json" -ErrorAction SilentlyContinue
foreach ($file in $prerunFiles) {
    $stats.SpaceSaved += $file.Length
    if (!$DryRun) {
        Remove-Item $file.FullName -Force
    }
    Write-Host "    🗑️  $($file.Name)" -ForegroundColor Gray
    $stats.FilesDeleted++
}
if ($prerunFiles.Count -eq 0) {
    Write-Host "    (none found)" -ForegroundColor Gray
}

# HTML coverage folders
Write-Host "`n  Old HTML coverage folders..." -ForegroundColor Yellow
$htmlcovDirs = @(
    "htmlcov_governance_final",
    "htmlcov_strategies_comprehensive",
    "htmlcov_strategies_final",
    "htmlcov_strategies_success"
)
foreach ($dir in $htmlcovDirs) {
    if (Test-Path $dir) {
        $dirSize = (Get-ChildItem -Path $dir -Recurse -File | Measure-Object -Property Length -Sum).Sum
        $stats.SpaceSaved += $dirSize
        if (!$DryRun) {
            Remove-Item -Recurse -Force $dir
        }
        $sizeMB = [math]::Round($dirSize / 1MB, 2)
        Write-Host "    🗑️  $dir/ ($sizeMB MB)" -ForegroundColor Gray
        $stats.FilesDeleted++
    }
}

# Redundant artifacts
Write-Host "`n  Redundant artifacts..." -ForegroundColor Yellow
$artifactFiles = @(
    "backend.zip",
    "trading_platform.db.backup"
)
foreach ($file in $artifactFiles) {
    if (Test-Path $file) {
        $fileSize = (Get-Item $file).Length
        $stats.SpaceSaved += $fileSize
        if (!$DryRun) {
            Remove-Item $file -Force
        }
        $sizeMB = [math]::Round($fileSize / 1MB, 2)
        Write-Host "    🗑️  $file ($sizeMB MB)" -ForegroundColor Gray
        $stats.FilesDeleted++
    }
}

# =============================================================================
# Phase 3: Archive Debug Scripts
# =============================================================================

Write-Host "`n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Blue
Write-Host "📦 PHASE 3: Archiving Debug Scripts" -ForegroundColor Blue
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Blue

$debugScripts = @(
    "debug_auth.js",
    "debug_database_config.py",
    "debug_import.py",
    "debug_live_endpoints.py",
    "debug_routes.py"
)

foreach ($script in $debugScripts) {
    if (Test-Path $script) {
        if (!$DryRun) {
            Move-Item $script "archive/debug_scripts/" -Force
        }
        Write-Host "  📦 $script → archive/debug_scripts/" -ForegroundColor Gray
        $stats.FilesArchived++
    }
}

# =============================================================================
# Phase 4: Archive Validation Scripts
# =============================================================================

Write-Host "`n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Blue
Write-Host "📦 PHASE 4: Archiving Validation Scripts" -ForegroundColor Blue
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Blue

$validationScripts = @(
    "analyze_coverage.py",
    "api_access_demo.py",
    "check_db_schema.py",
    "check_server_db.py",
    "create_production_tables.py",
    "create_risk_manager.py",
    "create_test_tables.py",
    "final_smoke_test.py",
    "final_verification.py",
    "fix_database_schema.py",
    "get_api_tokens.py",
    "jwt_auth_guide.py",
    "manual_verification.py",
    "quick_phase_g_test.py",
    "quick_start.py",
    "slo_demo_standalone.py",
    "smoke_test.py",
    "smoke_tests.py",
    "validate_components.py",
    "validate_phase4.py"
)

foreach ($script in $validationScripts) {
    if (Test-Path $script) {
        if (!$DryRun) {
            Move-Item $script "archive/validation_scripts/" -Force
        }
        Write-Host "  📦 $script" -ForegroundColor Gray
        $stats.FilesArchived++
    }
}

# =============================================================================
# Phase 5: Archive Root Test Files
# =============================================================================

Write-Host "`n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Blue
Write-Host "📦 PHASE 5: Archiving Root Test Files" -ForegroundColor Blue
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Blue

$rootTestFiles = Get-ChildItem -Filter "test_*.py" -ErrorAction SilentlyContinue
foreach ($file in $rootTestFiles) {
    if (!$DryRun) {
        Move-Item $file.FullName "archive/validation_tests/" -Force
    }
    Write-Host "  📦 $($file.Name)" -ForegroundColor Gray
    $stats.FilesArchived++
}

# Also move test_phase_g.bat
if (Test-Path "test_phase_g.bat") {
    if (!$DryRun) {
        Move-Item "test_phase_g.bat" "archive/validation_tests/" -Force
    }
    Write-Host "  📦 test_phase_g.bat" -ForegroundColor Gray
    $stats.FilesArchived++
}

# =============================================================================
# Phase 6: Archive Old Reports
# =============================================================================

Write-Host "`n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Blue
Write-Host "📦 PHASE 6: Archiving Old Report Files" -ForegroundColor Blue
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Blue

$reportFiles = @(
    "day5_final_validation_report.json",
    "live_order_flow_report.json",
    "production_readiness_checklist.json",
    "risk_management_validation_report.json",
    "slo_demo_report.json",
    "slo_validation_report.json",
    "summary.json",
    "k6-summary.json",
    "test_results_summary.txt"
)

foreach ($file in $reportFiles) {
    if (Test-Path $file) {
        if (!$DryRun) {
            Move-Item $file "archive/reports/" -Force
        }
        Write-Host "  📦 $file" -ForegroundColor Gray
        $stats.FilesArchived++
    }
}

# =============================================================================
# Phase 7: Archive Old CI Scripts
# =============================================================================

Write-Host "`n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Blue
Write-Host "📦 PHASE 7: Archiving Old CI Scripts" -ForegroundColor Blue
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Blue

$oldCIScripts = @(
    "scripts/ci_batched.ps1",
    "scripts/ci_clean_light.ps1",
    "scripts/ci_light_mode.ps1",
    "scripts/ci_minimal_review.ps1",
    "scripts/ci_no_stall.ps1",
    "scripts/ci_sequential.ps1",
    "scripts/ci_simple_light.ps1",
    "scripts/ci_working.ps1"
)

Write-Host "  Keeping: scripts/ci_full.ps1, scripts/ci_minimal.ps1" -ForegroundColor Green
foreach ($script in $oldCIScripts) {
    if (Test-Path $script) {
        if (!$DryRun) {
            Move-Item $script "archive/old_ci_scripts/" -Force
        }
        Write-Host "  📦 $(Split-Path $script -Leaf)" -ForegroundColor Gray
        $stats.FilesArchived++
    }
}

# =============================================================================
# Phase 8: Archive Old Database Backups
# =============================================================================

Write-Host "`n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Blue
Write-Host "📦 PHASE 8: Archiving Old Database Backups" -ForegroundColor Blue
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Blue

$oldBackups = @(
    "backups/verification_backup_20250930_125509.db",
    "backups/verification_backup_20250930_125502.db",
    "backups/verification_backup_20250930_125442.db"
)

Write-Host "  Keeping: Most recent 2 backups" -ForegroundColor Green
foreach ($backup in $oldBackups) {
    if (Test-Path $backup) {
        if (!$DryRun) {
            Move-Item $backup "archive/old_backups/" -Force
        }
        Write-Host "  📦 $(Split-Path $backup -Leaf)" -ForegroundColor Gray
        $stats.FilesArchived++
    }
}

# =============================================================================
# Phase 9: Move Log Files to logs/
# =============================================================================

Write-Host "`n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Blue
Write-Host "📦 PHASE 9: Organizing Log Files" -ForegroundColor Blue
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Blue

$logFiles = @(
    "audit_trail.log",
    "predictions.log"
)

foreach ($log in $logFiles) {
    if (Test-Path $log) {
        if (!$DryRun) {
            if (!(Test-Path "logs")) {
                New-Item -ItemType Directory -Path "logs" -Force | Out-Null
            }
            Move-Item $log "logs/" -Force
        }
        Write-Host "  📦 $log → logs/" -ForegroundColor Gray
        $stats.FilesArchived++
    }
}

# =============================================================================
# Phase 10: Create Archive READMEs
# =============================================================================

Write-Host "`n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Blue
Write-Host "📝 PHASE 10: Creating Archive Documentation" -ForegroundColor Blue
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Blue

if (!$DryRun) {
    # Debug scripts README
    @"
# Debug Scripts Archive

These scripts were used during development for debugging and troubleshooting.
They are no longer needed for production deployment.

**Archived:** $(Get-Date -Format 'yyyy-MM-dd')

## Files:
- debug_auth.js - Authentication debugging
- debug_database_config.py - Database configuration testing
- debug_import.py - Import resolution testing
- debug_live_endpoints.py - Live endpoint testing
- debug_routes.py - Route debugging

**Note:** These are kept for historical reference but should not be needed.
"@ | Out-File "archive/debug_scripts/README.md" -Encoding UTF8

    # Validation scripts README
    @"
# Validation Scripts Archive

These scripts were one-off validation and smoke test scripts used during development.
They have been replaced by the comprehensive testing framework in scripts/testing/.

**Archived:** $(Get-Date -Format 'yyyy-MM-dd')

## Replacement:
Use the production test suite instead:
``````powershell
.\quick_validation.ps1                                    # Quick validation
.\venv\Scripts\python.exe scripts\testing\burn_in_framework.py  # Full validation
``````

**Note:** These are kept for historical reference only.
"@ | Out-File "archive/validation_scripts/README.md" -Encoding UTF8

    Write-Host "  ✅ Created archive READMEs" -ForegroundColor Green
}

# =============================================================================
# Summary Report
# =============================================================================

Write-Host "`n" -NoNewline
Write-Host "╔════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║                                                        ║" -ForegroundColor Green
Write-Host "║               ✅ CLEANUP COMPLETE                       ║" -ForegroundColor Green
Write-Host "║                                                        ║" -ForegroundColor Green
Write-Host "╚════════════════════════════════════════════════════════╝" -ForegroundColor Green

Write-Host "`n📊 Statistics:" -ForegroundColor Cyan
Write-Host "   Directories Created: $($stats.DirectoriesCreated)" -ForegroundColor White
Write-Host "   Files Deleted:       $($stats.FilesDeleted)" -ForegroundColor White
Write-Host "   Files Archived:      $($stats.FilesArchived)" -ForegroundColor White
Write-Host "   Space Saved:         $([math]::Round($stats.SpaceSaved / 1MB, 2)) MB" -ForegroundColor White

if ($DryRun) {
    Write-Host "`n⚠️  This was a DRY RUN - no files were actually modified" -ForegroundColor Yellow
    Write-Host "   Run without -DryRun to perform actual cleanup" -ForegroundColor Yellow
} else {
    Write-Host "`n🎯 Next Steps:" -ForegroundColor Cyan
    Write-Host "   1. Review changes: git status" -ForegroundColor White
    Write-Host "   2. Test platform: .\quick_validation.ps1" -ForegroundColor White
    Write-Host "   3. Commit cleanup: git add . && git commit -m 'chore: platform cleanup'" -ForegroundColor White
    Write-Host "   4. Review audit report: COMPREHENSIVE_PLATFORM_AUDIT_REPORT.md" -ForegroundColor White
}

Write-Host ""