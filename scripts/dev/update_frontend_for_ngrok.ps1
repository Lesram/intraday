# Update Frontend Configuration for Ngrok Backend
param(
    [Parameter(Mandatory=$true)]
    [string]$BackendUrl
)

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  UPDATE FRONTEND FOR NGROK BACKEND" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# Validate URL format
if ($BackendUrl -notmatch '^https?://') {
    Write-Host "❌ Error: Backend URL must start with http:// or https://" -ForegroundColor Red
    Write-Host "   Example: https://abc123.ngrok.io" -ForegroundColor Yellow
    exit 1
}

# Remove trailing slash
$BackendUrl = $BackendUrl.TrimEnd('/')

Write-Host "Backend URL: $BackendUrl" -ForegroundColor Green
Write-Host ""

# Check if frontend env file exists
$envPath = "frontend\.env.local"
$envDevPath = "frontend\.env.development.local"

# Create/update .env.local for frontend
Write-Host "📝 Creating frontend environment file..." -ForegroundColor Yellow

$envContent = @"
# Ngrok Backend URL for Testing
# Generated: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")

VITE_API_BASE_URL=$BackendUrl/api/v1
VITE_WS_URL=$BackendUrl

# Original local URLs (commented out)
# VITE_API_BASE_URL=http://localhost:8000/api/v1
# VITE_WS_URL=http://localhost:8000
"@

Set-Content -Path $envPath -Value $envContent -Force

Write-Host "✅ Created: $envPath" -ForegroundColor Green
Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "Configuration Updated!" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "NEXT STEPS:" -ForegroundColor Yellow
Write-Host "1. Restart your frontend development server:" -ForegroundColor White
Write-Host "   cd frontend" -ForegroundColor Gray
Write-Host "   npm run dev" -ForegroundColor Gray
Write-Host ""
Write-Host "2. Your frontend will now use the ngrok backend URL" -ForegroundColor White
Write-Host ""
Write-Host "3. Share these URLs with the AI agent:" -ForegroundColor White
Write-Host "   Frontend: [Your ngrok frontend URL]" -ForegroundColor Gray
Write-Host "   Backend:  $BackendUrl" -ForegroundColor Gray
Write-Host ""
Write-Host "4. Login credentials for AI agent:" -ForegroundColor White
Write-Host "   Email:    [Your admin email]" -ForegroundColor Gray
Write-Host "   Password: [Your password]" -ForegroundColor Gray
Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
