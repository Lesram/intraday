# Clear Stuck Outbox Events - PowerShell Script
# This script connects to PostgreSQL and clears the 2 stuck orders

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  CLEAR STUCK OUTBOX EVENTS" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# Get database connection string from environment
$dbUrl = $env:DATABASE_URL

if (-not $dbUrl) {
    Write-Host "❌ ERROR: DATABASE_URL environment variable not set" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please set DATABASE_URL first:" -ForegroundColor Yellow
    Write-Host '  $env:DATABASE_URL = "postgresql://user:password@localhost:5432/algotrading"' -ForegroundColor Gray
    exit 1
}

Write-Host "✅ Found DATABASE_URL" -ForegroundColor Green
Write-Host ""

# Parse connection details
if ($dbUrl -match "postgresql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)") {
    $dbUser = $matches[1]
    $dbPassword = $matches[2]
    $dbHost = $matches[3]
    $dbPort = $matches[4]
    $dbName = $matches[5]
    
    Write-Host "Database: $dbName" -ForegroundColor Cyan
    Write-Host "Host: $dbHost" -ForegroundColor Cyan
    Write-Host "Port: $dbPort" -ForegroundColor Cyan
    Write-Host "User: $dbUser" -ForegroundColor Cyan
    Write-Host ""
} else {
    Write-Host "❌ ERROR: Could not parse DATABASE_URL" -ForegroundColor Red
    exit 1
}

# Check if psql is available
$psqlPath = Get-Command psql -ErrorAction SilentlyContinue

if (-not $psqlPath) {
    Write-Host "⚠️  WARNING: psql not found in PATH" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "You can either:" -ForegroundColor Yellow
    Write-Host "  1. Install PostgreSQL client tools and add to PATH" -ForegroundColor Gray
    Write-Host "  2. Use pgAdmin or DBeaver to run: clear_outbox.sql" -ForegroundColor Gray
    Write-Host "  3. Run manually:" -ForegroundColor Gray
    Write-Host "     psql -h $dbHost -U $dbUser -d $dbName -f clear_outbox.sql" -ForegroundColor Gray
    Write-Host ""
    exit 1
}

Write-Host "✅ Found psql: $($psqlPath.Source)" -ForegroundColor Green
Write-Host ""

# Confirm before proceeding
Write-Host "This will DELETE stuck events from outbox_events table" -ForegroundColor Yellow
$confirm = Read-Host "Continue? (y/N)"

if ($confirm -ne "y" -and $confirm -ne "Y") {
    Write-Host "❌ Cancelled" -ForegroundColor Red
    exit 0
}

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  EXECUTING SQL SCRIPT" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# Set password environment variable for psql
$env:PGPASSWORD = $dbPassword

# Run the SQL script
$sqlFile = Join-Path $PSScriptRoot "clear_outbox.sql"

if (-not (Test-Path $sqlFile)) {
    Write-Host "❌ ERROR: clear_outbox.sql not found" -ForegroundColor Red
    exit 1
}

Write-Host "Running SQL script..." -ForegroundColor Cyan
psql -h $dbHost -U $dbUser -d $dbName -f $sqlFile

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "================================================" -ForegroundColor Green
    Write-Host "  ✅ SUCCESS!" -ForegroundColor Green
    Write-Host "================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Stuck events cleared!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Cyan
    Write-Host "  1. Restart backend (Ctrl+C, then uvicorn backend.main:app --reload)" -ForegroundColor Gray
    Write-Host "  2. Monitor logs for 1-2 minutes" -ForegroundColor Gray
    Write-Host "  3. Verify no more error loops" -ForegroundColor Gray
    Write-Host "  4. Proceed with Integration Test" -ForegroundColor Gray
    Write-Host ""
} else {
    Write-Host ""
    Write-Host "❌ ERROR: SQL script failed" -ForegroundColor Red
    Write-Host ""
    Write-Host "You can try manually:" -ForegroundColor Yellow
    Write-Host "  psql -h $dbHost -U $dbUser -d $dbName" -ForegroundColor Gray
    Write-Host "  Then run: \i clear_outbox.sql" -ForegroundColor Gray
    Write-Host ""
    exit 1
}

# Clear password from environment
Remove-Item Env:PGPASSWORD
