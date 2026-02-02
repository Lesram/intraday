# LocalTunnel Setup Script (No Account Required)
# Alternative to ngrok that doesn't require authentication

Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "         LOCALTUNNEL SETUP FOR AI AGENT TESTING                " -ForegroundColor Cyan
Write-Host "         (No Account Required)                                 " -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""

# Check if localtunnel is installed
Write-Host "Step 1: Checking LocalTunnel..." -ForegroundColor Yellow
Write-Host "================================" -ForegroundColor Yellow

try {
    $ltCheck = npm list -g localtunnel 2>&1
    if ($ltCheck -match "localtunnel@") {
        Write-Host "[OK] LocalTunnel is installed" -ForegroundColor Green
    } else {
        throw "Not installed"
    }
} catch {
    Write-Host "[INFO] LocalTunnel not installed. Installing now..." -ForegroundColor Yellow
    npm install -g localtunnel
    Write-Host "[OK] LocalTunnel installed" -ForegroundColor Green
}
Write-Host ""

# Check frontend
Write-Host "Step 2: Checking Frontend..." -ForegroundColor Yellow
Write-Host "=============================" -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://localhost:5173" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
    Write-Host "[OK] Frontend is running on port 5173" -ForegroundColor Green
    $frontendRunning = $true
} catch {
    Write-Host "[WARNING] Frontend is NOT running on port 5173" -ForegroundColor Yellow
    Write-Host "          Start it with: cd frontend; npm run dev" -ForegroundColor Gray
    $frontendRunning = $false
}
Write-Host ""

# Check backend
Write-Host "Step 3: Checking Backend..." -ForegroundColor Yellow
Write-Host "===========================" -ForegroundColor Yellow
$backendPort = netstat -ano | findstr ":8000.*LISTENING"
if ($backendPort) {
    Write-Host "[OK] Backend appears to be running on port 8000" -ForegroundColor Green
    $backendRunning = $true
} else {
    Write-Host "[WARNING] Backend may not be running on port 8000" -ForegroundColor Yellow
    $backendRunning = $false
}
Write-Host ""

if (-not $frontendRunning) {
    Write-Host "[ERROR] Frontend must be running. Please start it first:" -ForegroundColor Red
    Write-Host "   cd frontend" -ForegroundColor White
    Write-Host "   npm run dev" -ForegroundColor White
    Write-Host ""
    exit 1
}

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "STARTING LOCALTUNNEL TUNNELS" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "This will open 2 new terminal windows with public URLs" -ForegroundColor White
Write-Host "The URLs will look like: https://xxxx-xxx.loca.lt" -ForegroundColor Gray
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
Write-Host '     LOCALTUNNEL FRONTEND (Port 5173)                         ' -ForegroundColor Cyan
Write-Host '================================================================' -ForegroundColor Cyan
Write-Host ''
Write-Host 'COPY THE HTTPS URL THAT APPEARS BELOW' -ForegroundColor Yellow
Write-Host 'It will look like: https://xxxx-xxx.loca.lt' -ForegroundColor Gray
Write-Host ''
Write-Host 'Keep this window open during testing!' -ForegroundColor Yellow
Write-Host ''
Write-Host '================================================================' -ForegroundColor Cyan
Write-Host ''
npx localtunnel --port 5173
"@

Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendScript

Start-Sleep -Seconds 3

# Start backend tunnel
Write-Host "Opening backend tunnel window..." -ForegroundColor Cyan
$backendScript = @"
Write-Host '================================================================' -ForegroundColor Cyan
Write-Host '      LOCALTUNNEL BACKEND (Port 8000)                         ' -ForegroundColor Cyan
Write-Host '================================================================' -ForegroundColor Cyan
Write-Host ''
Write-Host 'COPY THE HTTPS URL THAT APPEARS BELOW' -ForegroundColor Yellow
Write-Host 'It will look like: https://yyyy-yyy.loca.lt' -ForegroundColor Gray
Write-Host ''
Write-Host 'Keep this window open during testing!' -ForegroundColor Yellow
Write-Host ''
Write-Host '================================================================' -ForegroundColor Cyan
Write-Host ''
npx localtunnel --port 8000
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
Write-Host "   (They will look like: https://xxxx.loca.lt)" -ForegroundColor Gray
Write-Host ""
Write-Host "2. Update frontend config with backend URL:" -ForegroundColor White
Write-Host "   .\update_frontend_for_ngrok.ps1 -BackendUrl 'https://YOUR-BACKEND.loca.lt'" -ForegroundColor Cyan
Write-Host ""
Write-Host "3. Restart your frontend:" -ForegroundColor White
Write-Host "   - Stop it (Ctrl+C in frontend terminal)" -ForegroundColor Gray
Write-Host "   - Start again: cd frontend; npm run dev" -ForegroundColor Gray
Write-Host ""
Write-Host "4. Test in your browser:" -ForegroundColor White
Write-Host "   - Open: https://YOUR-FRONTEND.loca.lt" -ForegroundColor Gray
Write-Host "   - May show password prompt - just click through" -ForegroundColor Gray
Write-Host "   - Login and verify everything works" -ForegroundColor Gray
Write-Host ""
Write-Host "5. Share frontend URL with AI agent for testing!" -ForegroundColor White
Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""
