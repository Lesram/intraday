# Force Restart Vite Dev Server
# This script will:
# 1. Kill all node processes running Vite
# 2. Clear Vite cache
# 3. Restart Vite dev server

Write-Host "🔄 Restarting Vite Dev Server..." -ForegroundColor Cyan

# Step 1: Kill all node/vite processes
Write-Host "⏹️  Stopping Vite processes..." -ForegroundColor Yellow
Get-Process -Name "node" -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "*vite*" -or $_.CommandLine -like "*vite*" } | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

# Step 2: Clear Vite cache
Write-Host "🗑️  Clearing Vite cache..." -ForegroundColor Yellow
$viteCachePath = "frontend\node_modules\.vite"
if (Test-Path $viteCachePath) {
    Remove-Item -Path $viteCachePath -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "✅ Vite cache cleared" -ForegroundColor Green
} else {
    Write-Host "ℹ️  No Vite cache found" -ForegroundColor Gray
}

# Step 3: Navigate to frontend directory
Write-Host "📁 Navigating to frontend directory..." -ForegroundColor Yellow
Set-Location -Path "frontend"

# Step 4: Start Vite dev server
Write-Host "🚀 Starting Vite dev server..." -ForegroundColor Green
Write-Host ""
Write-Host "================================" -ForegroundColor Cyan
Write-Host "Vite will start in a moment..." -ForegroundColor Cyan
Write-Host "After it starts, do a HARD REFRESH in your browser:" -ForegroundColor Yellow
Write-Host "  Windows: Ctrl + Shift + R" -ForegroundColor White
Write-Host "  Mac: Cmd + Shift + R" -ForegroundColor White
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""

npm run dev
