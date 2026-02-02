# Restart Backend Server Script
# This ensures a clean restart with all fixes loaded

Write-Host ""
Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host "🔄 RESTARTING BACKEND SERVER" -ForegroundColor Yellow
Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host ""

# Step 1: Stop existing Python processes
Write-Host "1️⃣  Stopping existing backend processes..." -ForegroundColor White
$pythonProcesses = Get-Process python -ErrorAction SilentlyContinue
if ($pythonProcesses) {
    Write-Host "   Found $($pythonProcesses.Count) Python process(es)" -ForegroundColor Gray
    foreach ($proc in $pythonProcesses) {
        Write-Host "   Stopping PID: $($proc.Id)" -ForegroundColor Gray
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 2
    Write-Host "   ✅ All Python processes stopped" -ForegroundColor Green
} else {
    Write-Host "   ℹ️  No Python processes found" -ForegroundColor Gray
}

# Step 2: Clear Python bytecode cache
Write-Host ""
Write-Host "2️⃣  Clearing Python bytecode cache..." -ForegroundColor White
$pycacheCount = 0
Get-ChildItem -Path "backend" -Directory -Recurse -Filter "__pycache__" | ForEach-Object {
    $pycacheCount++
    Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
}
Write-Host "   ✅ Cleared $pycacheCount __pycache__ directories" -ForegroundColor Green

# Step 3: Verify fix is in place
Write-Host ""
Write-Host "3️⃣  Verifying database fix is in place..." -ForegroundColor White
$fixLine = Select-String -Path "backend\infra\outbox_worker.py" -Pattern "attach_broker_result" -Context 0,2
if ($fixLine) {
    Write-Host "   ✅ Fix detected: attach_broker_result() method found" -ForegroundColor Green
} else {
    Write-Host "   ⚠️  Warning: Fix not found in outbox_worker.py" -ForegroundColor Yellow
}

# Step 4: Check for QueuePool (should be removed)
Write-Host ""
Write-Host "4️⃣  Checking async pool fix..." -ForegroundColor White
$queuePool = Select-String -Path "backend\infra\unified_database.py" -Pattern '"poolclass".*QueuePool' -SimpleMatch
if ($queuePool) {
    Write-Host "   ⚠️  Warning: QueuePool still found in unified_database.py" -ForegroundColor Yellow
} else {
    Write-Host "   ✅ Async pool fix confirmed (QueuePool removed)" -ForegroundColor Green
}

# Step 5: Start backend server
Write-Host ""
Write-Host "5️⃣  Starting backend server..." -ForegroundColor White
Write-Host ""
Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host "Backend server starting on http://localhost:8000" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Gray
Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host ""

# Start in new process
python main.py
