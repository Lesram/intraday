# Complete Ngrok Setup - All-in-One Script
# This script will guide you through the entire setup process

Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "         NGROK SETUP FOR AI AGENT TESTING                      " -ForegroundColor Cyan
Write-Host "         Complete Setup Script                                 " -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Check Ngrok installation
Write-Host "Step 1: Checking Ngrok Installation..." -ForegroundColor Yellow
Write-Host "=======================================" -ForegroundColor Yellow
try {
    $null = Get-Command ngrok -ErrorAction Stop
    Write-Host "[OK] Ngrok is installed" -ForegroundColor Green
    Write-Host "     Note: If ngrok command fails, restart this terminal" -ForegroundColor Gray
} catch {
    Write-Host "[ERROR] Ngrok not found in PATH" -ForegroundColor Red
    Write-Host "        Please restart your terminal to load the updated PATH" -ForegroundColor Yellow
    Write-Host "        Then run this script again" -ForegroundColor Yellow
    exit 1
}
Write-Host ""

# Step 2: Check backend
Write-Host "Step 2: Checking Backend..." -ForegroundColor Yellow
Write-Host "===========================" -ForegroundColor Yellow
try {
    $backendResponse = Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
    Write-Host "[OK] Backend is running on port 8000" -ForegroundColor Green
    $backendRunning = $true
} catch {
    try {
        # Try alternative health check endpoint
        $backendResponse = Invoke-WebRequest -Uri "http://localhost:8000/docs" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        Write-Host "[OK] Backend is running on port 8000" -ForegroundColor Green
        $backendRunning = $true
    } catch {
        Write-Host "[WARNING] Backend is NOT running on port 8000" -ForegroundColor Yellow
        Write-Host "          You need to start it with:" -ForegroundColor Gray
        Write-Host "          python main.py" -ForegroundColor White
        Write-Host "          OR: docker-compose up -d" -ForegroundColor White
        $backendRunning = $false
    }
}
Write-Host ""

# Step 3: Check frontend
Write-Host "Step 3: Checking Frontend..." -ForegroundColor Yellow
Write-Host "=============================" -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://localhost:5173" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
    Write-Host "[OK] Frontend is running on port 5173" -ForegroundColor Green
    $frontendRunning = $true
} catch {
    Write-Host "[WARNING] Frontend is NOT running on port 5173" -ForegroundColor Yellow
    Write-Host "          You need to start it with:" -ForegroundColor Gray
    Write-Host "          cd frontend" -ForegroundColor White
    Write-Host "          npm run dev" -ForegroundColor White
    $frontendRunning = $false
}
Write-Host ""

# Summary
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "SETUP SUMMARY" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "Ngrok:    " -NoNewline
if ($true) { Write-Host "[READY]" -ForegroundColor Green } else { Write-Host "[NOT READY]" -ForegroundColor Red }
Write-Host "Backend:  " -NoNewline  
if ($backendRunning) { Write-Host "[RUNNING]" -ForegroundColor Green } else { Write-Host "[NOT RUNNING]" -ForegroundColor Red }
Write-Host "Frontend: " -NoNewline
if ($frontendRunning) { Write-Host "[RUNNING]" -ForegroundColor Green } else { Write-Host "[NOT RUNNING]" -ForegroundColor Red }
Write-Host ""

# Decide next steps
if (-not $frontendRunning) {
    Write-Host "SETUP REQUIRED" -ForegroundColor Yellow
    Write-Host "==============" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Start Frontend (in new terminal):" -ForegroundColor Yellow
    Write-Host "   cd frontend" -ForegroundColor White
    Write-Host "   npm run dev" -ForegroundColor White
    Write-Host ""
    Write-Host "Then run this script again to continue setup" -ForegroundColor Cyan
    Write-Host ""
    exit 0
}

if (-not $backendRunning) {
    Write-Host ""
    Write-Host "[INFO] Backend check failed (may be running but auth-protected)" -ForegroundColor Yellow
    $continueAnyway = Read-Host "Backend appears offline. Continue anyway? (y/n)"
    if ($continueAnyway -ne "y") {
        Write-Host ""
        Write-Host "Please start backend with:" -ForegroundColor Yellow
        Write-Host "   python main.py" -ForegroundColor White
        Write-Host "   OR: docker-compose up -d" -ForegroundColor White
        Write-Host ""
        exit 0
    }
    Write-Host "[INFO] Continuing with tunnel setup..." -ForegroundColor Cyan
}

# Both services running - proceed with ngrok
Write-Host "[OK] All services are running!" -ForegroundColor Green
Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "STARTING NGROK TUNNELS" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "This will open 2 new terminal windows:" -ForegroundColor White
Write-Host "  1. Frontend tunnel (port 5173)" -ForegroundColor Gray
Write-Host "  2. Backend tunnel (port 8000)" -ForegroundColor Gray
Write-Host ""
Write-Host "In each window, look for a line like:" -ForegroundColor White
Write-Host "  Forwarding  https://xxxx-xx.ngrok-free.app -> http://localhost:XXXX" -ForegroundColor Gray
Write-Host ""
Write-Host "Copy both HTTPS URLs!" -ForegroundColor Yellow
Write-Host ""

$continue = Read-Host "Ready to start tunnels? (y/n)"
if ($continue -ne "y") {
    Write-Host "Setup cancelled" -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host "Starting tunnels..." -ForegroundColor Green
Write-Host ""

# Start frontend tunnel
Write-Host "Opening frontend tunnel window..." -ForegroundColor Cyan
$frontendScript = @"
Write-Host '================================================================' -ForegroundColor Cyan
Write-Host '     NGROK FRONTEND TUNNEL (Port 5173)                        ' -ForegroundColor Cyan
Write-Host '================================================================' -ForegroundColor Cyan
Write-Host ''
Write-Host 'COPY THE HTTPS URL BELOW:' -ForegroundColor Yellow
Write-Host '   (It will look like: https://xxxx.ngrok-free.app)' -ForegroundColor Gray
Write-Host ''
Write-Host 'Keep this window open during testing!' -ForegroundColor Yellow
Write-Host ''
Write-Host '================================================================' -ForegroundColor Cyan
Write-Host ''
ngrok http 5173 --log=stdout
"@

Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendScript

Start-Sleep -Seconds 3

# Start backend tunnel
Write-Host "Opening backend tunnel window..." -ForegroundColor Cyan
$backendScript = @"
Write-Host '================================================================' -ForegroundColor Cyan
Write-Host '      NGROK BACKEND TUNNEL (Port 8000)                        ' -ForegroundColor Cyan
Write-Host '================================================================' -ForegroundColor Cyan
Write-Host ''
Write-Host 'COPY THE HTTPS URL BELOW:' -ForegroundColor Yellow
Write-Host '   (It will look like: https://yyyy.ngrok-free.app)' -ForegroundColor Gray
Write-Host ''
Write-Host 'Keep this window open during testing!' -ForegroundColor Yellow
Write-Host ''
Write-Host '================================================================' -ForegroundColor Cyan
Write-Host ''
ngrok http 8000 --log=stdout
"@

Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendScript

Write-Host ""
Write-Host "[OK] Tunnel windows opened!" -ForegroundColor Green
Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "NEXT STEPS" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "1. Check the 2 new windows and copy BOTH URLs" -ForegroundColor White
Write-Host ""
Write-Host "2. Update frontend config with backend URL:" -ForegroundColor White
Write-Host "   .\update_frontend_for_ngrok.ps1 -BackendUrl 'https://YOUR-BACKEND.ngrok-free.app'" -ForegroundColor Cyan
Write-Host ""
Write-Host "3. Restart your frontend:" -ForegroundColor White
Write-Host "   - Stop it (Ctrl+C in frontend terminal)" -ForegroundColor Gray
Write-Host "   - Start again: cd frontend; npm run dev" -ForegroundColor Gray
Write-Host ""
Write-Host "4. Test in your browser:" -ForegroundColor White
Write-Host "   - Open: https://YOUR-FRONTEND.ngrok-free.app" -ForegroundColor Gray
Write-Host "   - Click 'Visit Site' on ngrok warning" -ForegroundColor Gray
Write-Host "   - Login and verify everything works" -ForegroundColor Gray
Write-Host ""
Write-Host "5. Share with AI agent:" -ForegroundColor White
Write-Host "   - Frontend URL" -ForegroundColor Gray
Write-Host "   - Login credentials" -ForegroundColor Gray
Write-Host "   - Link to FULL_TESTING_SESSION_OCT10.md" -ForegroundColor Gray
Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Full instructions: See NGROK_SETUP_GUIDE.md" -ForegroundColor Cyan
Write-Host ""
