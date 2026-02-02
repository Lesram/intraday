# Phase 2 Deep Cleanup Script
# Generated: October 1, 2025
# Purpose: Remove artifacts, caches, and old logs to free ~330 MB

param(
    [switch]$DryRun = $false
)

$ErrorActionPreference = 'Continue'
$totalFreed = 0

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "Phase 2 Deep Cleanup Starting..." -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

if ($DryRun) {
    Write-Host "DRY RUN MODE - No files will be deleted`n" -ForegroundColor Yellow
}

# Function to calculate directory size
function Get-DirectorySize {
    param([string]$Path)
    if (Test-Path $Path) {
        $size = (Get-ChildItem -Path $Path -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
        return [math]::Round($size / 1MB, 2)
    }
    return 0
}

# Function to safely remove item
function Remove-ItemSafe {
    param(
        [string]$Path,
        [string]$Description,
        [double]$SizeMB
    )
    
    if (Test-Path $Path) {
        Write-Host "  [+] Found: $Description ($SizeMB MB)" -ForegroundColor Yellow
        if (-not $DryRun) {
            try {
                Remove-Item -Path $Path -Recurse -Force -ErrorAction Stop
                Write-Host "  [+] Deleted: $Description" -ForegroundColor Green
                $script:totalFreed += $SizeMB
            }
            catch {
                Write-Host "  [X] Failed to delete: $Description - $($_.Exception.Message)" -ForegroundColor Red
            }
        }
        else {
            Write-Host "  [DRY RUN] Would delete: $Description" -ForegroundColor Cyan
        }
    }
    else {
        Write-Host "  [i] Not found: $Description (already clean)" -ForegroundColor Gray
    }
}

# Step 1: Create backup
Write-Host "[1/8] Creating backup..." -ForegroundColor Cyan
if (-not $DryRun) {
    try {
        $backupName = "phase2_backup_$(Get-Date -Format 'yyyyMMdd_HHmmss').zip"
        $backupPath = Join-Path (Split-Path $PSScriptRoot -Parent) $backupName
        Write-Host "  Creating backup at: $backupPath" -ForegroundColor Yellow
        
        # Backup critical logs and data before deletion
        $tempBackupDir = ".\temp_backup_phase2"
        New-Item -ItemType Directory -Path $tempBackupDir -Force | Out-Null
        
        if (Test-Path "logs\app.log") {
            Copy-Item -Path "logs\app.log" -Destination "$tempBackupDir\app.log" -Force
        }
        if (Test-Path "logs\audit_trail.log") {
            Copy-Item -Path "logs\audit_trail.log" -Destination "$tempBackupDir\audit_trail.log" -Force
        }
        
        Compress-Archive -Path $tempBackupDir -DestinationPath $backupPath -Force
        Remove-Item -Path $tempBackupDir -Recurse -Force
        
        Write-Host "  [+] Backup created successfully" -ForegroundColor Green
    }
    catch {
        Write-Host "  [X] Backup failed: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "  [!] Aborting cleanup for safety" -ForegroundColor Red
        exit 1
    }
}
else {
    Write-Host "  [DRY RUN] Would create backup" -ForegroundColor Cyan
}

Write-Host ""

# Step 2: Delete burn-in test results (176 MB)
Write-Host "[2/8] Deleting burn-in test results..." -ForegroundColor Cyan
$size = Get-DirectorySize "test_results\burn_in"
Remove-ItemSafe -Path "test_results\burn_in" -Description "test_results/burn_in/ (old test results)" -SizeMB $size
Write-Host ""

# Step 3: Archive and clear app.log (131 MB)
Write-Host "[3/8] Archiving and clearing app.log..." -ForegroundColor Cyan
if (Test-Path "logs\app.log") {
    $size = Get-DirectorySize "logs\app.log"
    Write-Host "  [+] Found: app.log ($size MB)" -ForegroundColor Yellow
    
    if (-not $DryRun) {
        try {
            # Create archive directory
            New-Item -ItemType Directory -Path "archive\logs" -Force | Out-Null
            
            # Move to archive with timestamp
            $archiveName = "app.log.$(Get-Date -Format 'yyyyMMdd_HHmmss')"
            Move-Item -Path "logs\app.log" -Destination "archive\logs\$archiveName" -Force
            
            Write-Host "  [+] Archived to: archive\logs\$archiveName" -ForegroundColor Green
            $script:totalFreed += $size
        }
        catch {
            Write-Host "  [X] Failed to archive app.log: $($_.Exception.Message)" -ForegroundColor Red
        }
    }
    else {
        Write-Host "  [DRY RUN] Would archive to: archive\logs\app.log.TIMESTAMP" -ForegroundColor Cyan
    }
}
else {
    Write-Host "  [i] app.log not found" -ForegroundColor Gray
}
Write-Host ""

# Step 4: Delete coverage reports (10+ MB)
Write-Host "[4/8] Deleting coverage reports..." -ForegroundColor Cyan
$size = Get-DirectorySize "htmlcov"
Remove-ItemSafe -Path "htmlcov" -Description "htmlcov/ (coverage HTML)" -SizeMB $size

Get-ChildItem -Path . -Filter "htmlcov_*" -Directory -ErrorAction SilentlyContinue | ForEach-Object {
    $size = Get-DirectorySize $_.FullName
    Remove-ItemSafe -Path $_.FullName -Description $_.Name -SizeMB $size
}
Write-Host ""

# Step 5: Clean Python caches (3 MB)
Write-Host "[5/8] Cleaning Python caches..." -ForegroundColor Cyan

# __pycache__ directories
$pycacheDirs = Get-ChildItem -Path . -Filter __pycache__ -Recurse -Directory -Force -ErrorAction SilentlyContinue
$totalPycacheSize = 0
$pycacheDirs | ForEach-Object {
    $size = Get-DirectorySize $_.FullName
    $totalPycacheSize += $size
}
if ($pycacheDirs.Count -gt 0) {
    Write-Host "  [+] Found: $($pycacheDirs.Count) __pycache__ directories ($totalPycacheSize MB)" -ForegroundColor Yellow
    if (-not $DryRun) {
        $pycacheDirs | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "  [+] Deleted all __pycache__ directories" -ForegroundColor Green
        $script:totalFreed += $totalPycacheSize
    }
    else {
        Write-Host "  [DRY RUN] Would delete $($pycacheDirs.Count) __pycache__ directories" -ForegroundColor Cyan
    }
}
else {
    Write-Host "  [i] No __pycache__ directories found" -ForegroundColor Gray
}

# .pytest_cache
$size = Get-DirectorySize ".pytest_cache"
Remove-ItemSafe -Path ".pytest_cache" -Description ".pytest_cache/" -SizeMB $size

# .coverage file
if (Test-Path ".coverage") {
    $size = [math]::Round((Get-Item ".coverage").Length / 1MB, 2)
    Remove-ItemSafe -Path ".coverage" -Description ".coverage file" -SizeMB $size
}
Write-Host ""

# Step 6: Delete documents directory
Write-Host "[6/8] Deleting documents directory..." -ForegroundColor Cyan
$size = Get-DirectorySize "documents"
Remove-ItemSafe -Path "documents" -Description "documents/ (73 UUID workflow artifacts)" -SizeMB $size
Write-Host ""

# Step 7: Archive audit logs
Write-Host "[7/8] Archiving audit logs..." -ForegroundColor Cyan
if (Test-Path "logs\audit_trail.log") {
    $size = [math]::Round((Get-Item "logs\audit_trail.log").Length / 1MB, 2)
    Write-Host "  [+] Found: audit_trail.log ($size MB)" -ForegroundColor Yellow
    
    if (-not $DryRun) {
        try {
            New-Item -ItemType Directory -Path "archive\logs" -Force | Out-Null
            $archiveName = "audit_trail.log.$(Get-Date -Format 'yyyyMMdd_HHmmss')"
            Move-Item -Path "logs\audit_trail.log" -Destination "archive\logs\$archiveName" -Force
            Write-Host "  [+] Archived to: archive\logs\$archiveName" -ForegroundColor Green
            $script:totalFreed += $size
        }
        catch {
            Write-Host "  [X] Failed to archive audit_trail.log: $($_.Exception.Message)" -ForegroundColor Red
        }
    }
    else {
        Write-Host "  [DRY RUN] Would archive to: archive\logs\audit_trail.log.TIMESTAMP" -ForegroundColor Cyan
    }
}
else {
    Write-Host "  [i] audit_trail.log not found" -ForegroundColor Gray
}
Write-Host ""

# Step 8: Remove empty directories
Write-Host "[8/8] Removing empty directories..." -ForegroundColor Cyan
$emptyDirs = @(
    "architect_review",
    "governance", 
    "custom_optimization",
    "model_optimization",
    "model_serving",
    "data",
    ".benchmarks"
)

foreach ($dir in $emptyDirs) {
    if (Test-Path $dir) {
        $isEmpty = (Get-ChildItem -Path $dir -Recurse -File -ErrorAction SilentlyContinue).Count -eq 0
        if ($isEmpty) {
            Write-Host "  [+] Found empty: $dir" -ForegroundColor Yellow
            if (-not $DryRun) {
                Remove-Item -Path $dir -Recurse -Force -ErrorAction SilentlyContinue
                Write-Host "  [+] Deleted: $dir" -ForegroundColor Green
            }
            else {
                Write-Host "  [DRY RUN] Would delete: $dir" -ForegroundColor Cyan
            }
        }
    }
}
Write-Host ""

# Summary
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Phase 2 Cleanup Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan

if (-not $DryRun) {
    Write-Host "Total space freed: $totalFreed MB" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Yellow
    Write-Host "  1. Run: .\quick_validation.ps1" -ForegroundColor White
    Write-Host "  2. Verify platform functionality" -ForegroundColor White
    Write-Host "  3. Check: 23/23 tests should still pass" -ForegroundColor White
}
else {
    Write-Host "Dry run completed - no files were modified" -ForegroundColor Cyan
    Write-Host "Run without -DryRun to execute cleanup" -ForegroundColor Yellow
}

Write-Host ""
