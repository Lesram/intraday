# Ngrok Tunnel Setup Script
# This script creates public URLs for your frontend and backend

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "    NGROK TUNNEL SETUP FOR TESTING" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# Check if ngrok is installed
try {
    $ngrokVersion = ngrok version 2>&1
    Write-Host "✅ Ngrok is installed" -ForegroundColor Green
    Write-Host ""
} catch {
    Write-Host "❌ Ngrok not found. Please restart your terminal." -ForegroundColor Red
    Write-Host "   (Path was updated during installation)" -ForegroundColor Yellow
    exit 1
}

# Instructions
Write-Host "IMPORTANT SETUP STEPS:" -ForegroundColor Yellow
Write-Host "======================" -ForegroundColor Yellow
Write-Host ""
Write-Host "1. Make sure your backend is running:" -ForegroundColor White
Write-Host "   docker-compose up" -ForegroundColor Gray
Write-Host ""
Write-Host "2. Make sure your frontend is running:" -ForegroundColor White
Write-Host "   cd frontend && npm run dev" -ForegroundColor Gray
Write-Host ""
Write-Host "3. This script will create two tunnels:" -ForegroundColor White
Write-Host "   - Frontend tunnel (port 5173)" -ForegroundColor Gray
Write-Host "   - Backend tunnel (port 8000)" -ForegroundColor Gray
Write-Host ""

# Ask for confirmation
$continue = Read-Host "Are both services running? (y/n)"
if ($continue -ne "y") {
    Write-Host "Please start your services first, then run this script again." -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "Starting tunnels..." -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "📝 INSTRUCTIONS:" -ForegroundColor Yellow
Write-Host "1. Two terminal windows will open with ngrok tunnels" -ForegroundColor White
Write-Host "2. Look for lines like:" -ForegroundColor White
Write-Host "   Forwarding  https://xxxx-xx-xx.ngrok.io -> http://localhost:5173" -ForegroundColor Gray
Write-Host "3. Copy those HTTPS URLs" -ForegroundColor White
Write-Host "4. You'll need to update frontend config with backend URL" -ForegroundColor White
Write-Host ""

# Start frontend tunnel in new window
Write-Host "🚀 Starting frontend tunnel (port 5173)..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Write-Host '🌐 FRONTEND TUNNEL (Port 5173)' -ForegroundColor Cyan; Write-Host 'Copy the HTTPS URL below:' -ForegroundColor Yellow; Write-Host ''; ngrok http 5173"

Start-Sleep -Seconds 2

# Start backend tunnel in new window  
Write-Host "🚀 Starting backend tunnel (port 8000)..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Write-Host '🔧 BACKEND TUNNEL (Port 8000)' -ForegroundColor Cyan; Write-Host 'Copy the HTTPS URL below:' -ForegroundColor Yellow; Write-Host ''; ngrok http 8000"

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "✅ Tunnels Started!" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "NEXT STEPS:" -ForegroundColor Yellow
Write-Host "1. Check the two new windows that opened" -ForegroundColor White
Write-Host "2. Copy both HTTPS URLs (they look like: https://xxxx.ngrok.io)" -ForegroundColor White
Write-Host "3. Run the update script with those URLs:" -ForegroundColor White
Write-Host "   .\update_frontend_for_ngrok.ps1 -BackendUrl 'https://your-backend.ngrok.io'" -ForegroundColor Gray
Write-Host ""
Write-Host "Keep these terminal windows open while testing!" -ForegroundColor Yellow
Write-Host ""
