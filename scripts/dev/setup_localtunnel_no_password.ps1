# LocalTunnel Setup WITHOUT Password Prompt
# Uses subdomain feature to avoid the tunnel password page

Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "         LOCALTUNNEL SETUP (No Password)                       " -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""

# Generate random subdomain names
$frontendSubdomain = "algotrade-fe-" + (Get-Random -Minimum 1000 -Maximum 9999)
$backendSubdomain = "algotrade-be-" + (Get-Random -Minimum 1000 -Maximum 9999)

Write-Host "Frontend subdomain: $frontendSubdomain" -ForegroundColor Green
Write-Host "Backend subdomain:  $backendSubdomain" -ForegroundColor Green
Write-Host ""

# Check if localtunnel is installed
try {
    $ltCheck = npm list -g localtunnel 2>&1
    if ($ltCheck -match "localtunnel@") {
        Write-Host "[OK] LocalTunnel is installed" -ForegroundColor Green
    } else {
        throw "Not installed"
    }
} catch {
    Write-Host "[INFO] Installing LocalTunnel..." -ForegroundColor Yellow
    npm install -g localtunnel
    Write-Host "[OK] LocalTunnel installed" -ForegroundColor Green
}
Write-Host ""

Write-Host "Starting tunnels..." -ForegroundColor Green
Write-Host ""

# Start frontend tunnel with subdomain
Write-Host "Opening frontend tunnel..." -ForegroundColor Cyan
$frontendScript = @"
Write-Host '================================================================' -ForegroundColor Cyan
Write-Host '     LOCALTUNNEL FRONTEND (Port 5173)                         ' -ForegroundColor Cyan
Write-Host '================================================================' -ForegroundColor Cyan
Write-Host ''
Write-Host 'Your Frontend URL:' -ForegroundColor Yellow
Write-Host 'https://$frontendSubdomain.loca.lt' -ForegroundColor Green
Write-Host ''
Write-Host 'Keep this window open during testing!' -ForegroundColor Yellow
Write-Host ''
Write-Host '================================================================' -ForegroundColor Cyan
Write-Host ''
npx localtunnel --port 5173 --subdomain $frontendSubdomain
"@

Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendScript

Start-Sleep -Seconds 3

# Start backend tunnel with subdomain
Write-Host "Opening backend tunnel..." -ForegroundColor Cyan
$backendScript = @"
Write-Host '================================================================' -ForegroundColor Cyan
Write-Host '      LOCALTUNNEL BACKEND (Port 8000)                         ' -ForegroundColor Cyan
Write-Host '================================================================' -ForegroundColor Cyan
Write-Host ''
Write-Host 'Your Backend URL:' -ForegroundColor Yellow
Write-Host 'https://$backendSubdomain.loca.lt' -ForegroundColor Green
Write-Host ''
Write-Host 'Keep this window open during testing!' -ForegroundColor Yellow
Write-Host ''
Write-Host '================================================================' -ForegroundColor Cyan
Write-Host ''
npx localtunnel --port 8000 --subdomain $backendSubdomain
"@

Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendScript

Start-Sleep -Seconds 2

Write-Host ""
Write-Host "[OK] Tunnels started!" -ForegroundColor Green
Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "YOUR PUBLIC URLS" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Frontend URL (share with AI agent):" -ForegroundColor Yellow
Write-Host "https://$frontendSubdomain.loca.lt" -ForegroundColor Green
Write-Host ""
Write-Host "Backend URL (for config):" -ForegroundColor Yellow  
Write-Host "https://$backendSubdomain.loca.lt" -ForegroundColor Green
Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "NEXT STEPS:" -ForegroundColor Yellow
Write-Host "1. Update frontend config:" -ForegroundColor White
Write-Host "   .\update_frontend_for_ngrok.ps1 -BackendUrl 'https://$backendSubdomain.loca.lt'" -ForegroundColor Cyan
Write-Host ""
Write-Host "2. Restart frontend (Ctrl+C then npm run dev)" -ForegroundColor White
Write-Host ""
Write-Host "3. Test: https://$frontendSubdomain.loca.lt" -ForegroundColor White
Write-Host ""
Write-Host "4. Share frontend URL with AI agent" -ForegroundColor White
Write-Host ""
