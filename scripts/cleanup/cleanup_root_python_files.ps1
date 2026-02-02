# Root-Level Python Files Cleanup Script
# Generated: January 17, 2026
# 
# This script cleans up the 147 root-level Python files
# Run with: .\cleanup_root_python_files.ps1 [-DryRun] [-Force]
#
# Options:
#   -DryRun   Show what would be done without making changes
#   -Force    Skip confirmation prompts

param(
    [switch]$DryRun,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot

Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host "ROOT-LEVEL PYTHON FILES CLEANUP" -ForegroundColor Cyan
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host ""

if ($DryRun) {
    Write-Host "[DRY RUN MODE] No changes will be made" -ForegroundColor Yellow
    Write-Host ""
}

# Create archive directories
$ArchiveDirs = @(
    "archive/phase_tests",
    "archive/validation", 
    "archive/migrations",
    "archive/one_time_scripts"
)

foreach ($dir in $ArchiveDirs) {
    $fullPath = Join-Path $ProjectRoot $dir
    if (-not (Test-Path $fullPath)) {
        if ($DryRun) {
            Write-Host "[DRY RUN] Would create: $dir" -ForegroundColor Gray
        } else {
            New-Item -ItemType Directory -Force -Path $fullPath | Out-Null
            Write-Host "Created: $dir" -ForegroundColor Green
        }
    }
}

# ============================================================================
# FILES TO DELETE (One-time debugging/investigation scripts)
# ============================================================================

$FilesToDelete = @(
    # CHECK_* scripts (28 files)
    "check_actual_error.py",
    "check_all_risk_tables.py",
    "check_alpaca_orders.py",
    "check_alpaca_status.py",
    "check_api_response.py",
    "check_backend_reload.py",
    "check_backtest_user_id.py",
    "check_current_orders.py",
    "check_database_fix.py",
    "check_db_oct7_orders.py",
    "check_emergency_stops.py",
    "check_foreign_keys.py",
    "check_oct7_broker_orders.py",
    "check_oct7_orders_alpaca.py",
    "check_orders_positions.py",
    "check_outbox_events.py",
    "check_outbox.py",
    "check_pg_users.py",
    "check_positions_status.py",
    "check_postgres_users.py",
    "check_risk_tables.py",
    "check_schema.py",
    "check_sell_orders.py",
    "check_status.py",
    "check_strategies.py",
    "check_strategy_fields.py",
    "check_table_columns.py",
    "check_table_indexes.py",
    "check_timestamps.py",
    "check_trades.py",
    "check_users_quick.py",
    "check_users_table.py",
    "check_users.py",
    "check_websocket_status.py",
    
    # ANALYZE_* scripts (2 files)
    "analyze_alpaca_vs_platform.py",
    "analyze_stuck_orders.py",
    
    # DEBUG_* scripts (10 files)
    "debug_500_with_auth.py",
    "debug_auth.py",
    "debug_indicators.py",
    "debug_order_sync.py",
    "debug_performance.py",
    "debug_portfolio.py",
    "debug_remaining.py",
    "debug_websocket.py",
    "debug_websockets.py",
    
    # VERIFY_* scripts (14 files)
    "verify_alpaca_orders.py",
    "verify_api_fields.py",
    "verify_backtest_fix.py",
    "verify_backtests_schema.py",
    "verify_credentials.py",
    "verify_database_sync.py",
    "verify_duplicate_fix.py",
    "verify_fix.py",
    "verify_outbox_fix.py",
    "verify_sqlite_removal.py",
    "verify_strategies_table.py",
    "verify_strategies.py",
    "verify_trade_history_simple.py",
    "verify_websocket_fix.py",
    
    # INVESTIGATE_* scripts (6 files)
    "investigate_all_orders.py",
    "investigate_local_orders.py",
    "investigate_missing_shares.py",
    "investigate_oct7_orders.py",
    "investigate_simple.py",
    "investigate_trade_history.py",
    
    # DIAGNOSE_* scripts (3 files)
    "diagnose_orders.py",
    "diagnose_outbox.py",
    "diagnose_websocket_sync.py",
    
    # AUDIT scripts (4 files)
    "audit_all_user_id_columns.py",
    "audit_database_schema.py",
    "audit_db_schema_sqlalchemy.py",
    "audit_schema.py",
    
    # One-time fix/cleanup scripts (15 files)
    "cancel_old_orders.py",
    "cleanup_orphaned_orders.py",
    "cleanup_test_strategies.py",
    "clear_stuck_events.py",
    "clear_stuck_outbox.py",
    "delete_failed_orders_no_broker_id.py",
    "mark_failed_orders.py",
    "mark_failed_simple.py",
    "populate_realized_trades.py",
    "remove_duplicate_orders.py",
    "resolve_emergency_stops.py",
    "update_oct7_filled_orders.py",
    "fix_stopped_strategies.py",
    "explain_no_broker_id.py",
    
    # Obsolete setup/migration scripts (5 files)
    "add_password_column.py",
    "apply_migration_manual.py",
    "apply_strategies_migration.py",
    "setup_test_positions.py",
    
    # Redundant test files (30+ files)
    "test_analytics_diagnostic.py",
    "test_analytics_endpoint.py",
    "test_auth_diagnostic.py",
    "test_close_position_direct.py",
    "test_create_strategy.py",
    "test_database_config.py",
    "test_db_connection.py",
    "test_direct_db.py",
    "test_endpoint_fix.py",
    "test_estimated_cost_fix.py",
    "test_lifespan.py",
    "test_orders_api.py",
    "test_outbox_fix.py",
    "test_portfolio_api.py",
    "test_portfolio_fix.py",
    "test_position_reconciliation.py",
    "test_risk_api.py",
    "test_simple_strategy_create.py",
    "test_socketio_lifespan.py",
    "test_socketio.py",
    "test_template_options.py",
    "test_trade_history_endpoint.py",
    "test_trade_history_fix.py",
    "test_trades_api.py",
    "test_validation.py",
    "test_websocket_api.py",
    "test_websocket_http.py",
    "test_websocket_updates.py",
    
    # Miscellaneous one-time scripts
    "deep_analysis.py",
    "deploy_guardrails.py",
    "get_strategy_for_perf_update.py",
    "get_strategy_id.py",
    "import_positions.py",
    "list_tables.py",
    "monitor_frontend_connection.py",
    "simple_order_check.py",
    "start_backend.py",
    "validate_burn_in_fixes.py"
)

# ============================================================================
# FILES TO ARCHIVE
# ============================================================================

$FilesToArchive = @{
    # Phase test files -> archive/phase_tests/
    "archive/phase_tests" = @(
        "test_phase_3_1_complete.py",
        "test_phase_3_1_comprehensive.py",
        "test_phase_3_1_frontend_visual.py",
        "test_phase_3_2_backend.py",
        "test_phase_3_2_database.py",
        "test_phase1_day1.py",
        "test_phase1_live.py",
        "test_phase2_repository.py"
    )
    
    # Validation files -> archive/validation/
    "archive/validation" = @(
        "validate_phase2.py",
        "validate_phase3.py"
    )
    
    # Migration files -> archive/migrations/
    "archive/migrations" = @(
        "migrate_backtest_user_id.py",
        "migrate_position_lots_user_id.py",
        "migrate_realized_trades_user_id.py"
    )
    
    # Useful reference scripts -> archive/one_time_scripts/
    "archive/one_time_scripts" = @(
        "reconcile_filled_orders.py"
    )
}

# ============================================================================
# FILES TO MOVE TO tests/
# ============================================================================

$FilesToMoveToTests = @(
    "test_8_strategy_types_api.py",
    "test_alpaca_sync.py",
    "test_analytics_api_full.py",
    "test_api_endpoint_validation.py",
    "test_edge_cases_automated.py",
    "test_order_submission.py",
    "test_order_validation.py",
    "test_phase7_integration.py",
    "test_position_management.py",
    "test_pretrade_validation.py",
    "test_real_data_integration.py",
    "test_strategies_automated_suite.py",
    "test_strategy_templates.py",
    "test_trade_history.py",
    "test_validation_comprehensive.py",
    "automated_backend_tests.py",
    "validate_8_strategy_types.py"
)

# ============================================================================
# FILES TO MOVE TO scripts/
# ============================================================================

$FilesToMoveToScripts = @(
    "reset_admin.py",
    "seed_strategies.py",
    "setup_test_user.py",
    "run_phase_tests.py",
    "decode_token.py"
)

# ============================================================================
# FILES TO KEEP (do not touch)
# ============================================================================

$FilesToKeep = @(
    "main.py",
    "validate_indicators.py"
)

# ============================================================================
# EXECUTION
# ============================================================================

Write-Host ""
Write-Host "PHASE 1: Deleting obsolete files" -ForegroundColor Yellow
Write-Host "-" * 60

$deletedCount = 0
foreach ($file in $FilesToDelete) {
    $fullPath = Join-Path $ProjectRoot $file
    if (Test-Path $fullPath) {
        if ($DryRun) {
            Write-Host "[DRY RUN] Would delete: $file" -ForegroundColor Gray
        } else {
            Remove-Item $fullPath -Force
            Write-Host "Deleted: $file" -ForegroundColor Red
        }
        $deletedCount++
    }
}
Write-Host ""
Write-Host "Files to delete: $deletedCount" -ForegroundColor Cyan

Write-Host ""
Write-Host "PHASE 2: Archiving phase-specific files" -ForegroundColor Yellow
Write-Host "-" * 60

$archivedCount = 0
foreach ($archiveDir in $FilesToArchive.Keys) {
    foreach ($file in $FilesToArchive[$archiveDir]) {
        $sourcePath = Join-Path $ProjectRoot $file
        $destPath = Join-Path $ProjectRoot $archiveDir $file
        if (Test-Path $sourcePath) {
            if ($DryRun) {
                Write-Host "[DRY RUN] Would archive: $file -> $archiveDir/" -ForegroundColor Gray
            } else {
                Move-Item $sourcePath $destPath -Force
                Write-Host "Archived: $file -> $archiveDir/" -ForegroundColor Magenta
            }
            $archivedCount++
        }
    }
}
Write-Host ""
Write-Host "Files to archive: $archivedCount" -ForegroundColor Cyan

Write-Host ""
Write-Host "PHASE 3: Moving test files to tests/" -ForegroundColor Yellow
Write-Host "-" * 60

$movedToTestsCount = 0
$testsDir = Join-Path $ProjectRoot "tests"
foreach ($file in $FilesToMoveToTests) {
    $sourcePath = Join-Path $ProjectRoot $file
    $destPath = Join-Path $testsDir $file
    if (Test-Path $sourcePath) {
        if (Test-Path $destPath) {
            Write-Host "Skipping (already exists): $file" -ForegroundColor Yellow
        } else {
            if ($DryRun) {
                Write-Host "[DRY RUN] Would move: $file -> tests/" -ForegroundColor Gray
            } else {
                Move-Item $sourcePath $destPath -Force
                Write-Host "Moved: $file -> tests/" -ForegroundColor Green
            }
            $movedToTestsCount++
        }
    }
}
Write-Host ""
Write-Host "Files to move to tests/: $movedToTestsCount" -ForegroundColor Cyan

Write-Host ""
Write-Host "PHASE 4: Moving utility files to scripts/" -ForegroundColor Yellow
Write-Host "-" * 60

$movedToScriptsCount = 0
$scriptsDir = Join-Path $ProjectRoot "scripts"
foreach ($file in $FilesToMoveToScripts) {
    $sourcePath = Join-Path $ProjectRoot $file
    $destPath = Join-Path $scriptsDir $file
    if (Test-Path $sourcePath) {
        if (Test-Path $destPath) {
            Write-Host "Skipping (already exists): $file" -ForegroundColor Yellow
        } else {
            if ($DryRun) {
                Write-Host "[DRY RUN] Would move: $file -> scripts/" -ForegroundColor Gray
            } else {
                Move-Item $sourcePath $destPath -Force
                Write-Host "Moved: $file -> scripts/" -ForegroundColor Green
            }
            $movedToScriptsCount++
        }
    }
}
Write-Host ""
Write-Host "Files to move to scripts/: $movedToScriptsCount" -ForegroundColor Cyan

# ============================================================================
# SUMMARY
# ============================================================================

Write-Host ""
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host "CLEANUP SUMMARY" -ForegroundColor Cyan
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host ""
Write-Host "Files deleted:           $deletedCount" -ForegroundColor Red
Write-Host "Files archived:          $archivedCount" -ForegroundColor Magenta
Write-Host "Files moved to tests/:   $movedToTestsCount" -ForegroundColor Green
Write-Host "Files moved to scripts/: $movedToScriptsCount" -ForegroundColor Green
Write-Host ""
Write-Host "Files kept at root:" -ForegroundColor White
foreach ($file in $FilesToKeep) {
    Write-Host "  - $file" -ForegroundColor White
}

if ($DryRun) {
    Write-Host ""
    Write-Host "[DRY RUN] No changes were made. Run without -DryRun to execute." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Done!" -ForegroundColor Green
