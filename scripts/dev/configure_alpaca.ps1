# Alpaca .env Configuration Helper
# Run this script to update your .env file with correct Alpaca variable names

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  Alpaca Configuration Helper" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# Check if .env exists
if (-not (Test-Path ".env")) {
    Write-Host "❌ .env file not found!" -ForegroundColor Red
    Write-Host "   Please create a .env file first." -ForegroundColor Yellow
    exit 1
}

# Read current .env
$envContent = Get-Content ".env" -Raw

Write-Host "Current Alpaca configuration:" -ForegroundColor Yellow
Write-Host "-----------------------------"
Get-Content ".env" | Select-String -Pattern "ALPACA|MOCK|PAPER" | ForEach-Object { Write-Host $_ }

Write-Host "`n"
Write-Host "========================================" -ForegroundColor Green
Write-Host "  REQUIRED CHANGES" -ForegroundColor Green
Write-Host "========================================`n" -ForegroundColor Green

Write-Host "Your .env file needs these exact variable names:`n" -ForegroundColor White

Write-Host "  ✓ ALPACA_API_KEY_ID (not ALPACA_API_KEY)" -ForegroundColor Green
Write-Host "  ✓ ALPACA_API_SECRET_KEY (not ALPACA_SECRET_KEY)" -ForegroundColor Green
Write-Host "  ✓ USE_MOCK_BROKER=false" -ForegroundColor Green
Write-Host "  ✓ ALPACA_PAPER=true" -ForegroundColor Green
Write-Host "  ✓ DEFAULT_USER_ID=demo" -ForegroundColor Green

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  STEPS TO FIX" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

Write-Host "1. Go to Alpaca dashboard: https://app.alpaca.markets" -ForegroundColor White
Write-Host "2. Navigate to: Your Account → API Keys" -ForegroundColor White
Write-Host "3. Generate new Paper Trading keys (if needed)" -ForegroundColor White
Write-Host "4. Copy your API Key ID and Secret Key" -ForegroundColor White
Write-Host "5. Update .env file with these lines:`n" -ForegroundColor White

Write-Host "   # Alpaca Configuration" -ForegroundColor DarkGray
Write-Host "   USE_MOCK_BROKER=false" -ForegroundColor Yellow
Write-Host "   ALPACA_PAPER=true" -ForegroundColor Yellow
Write-Host "   ALPACA_API_KEY_ID=YOUR_KEY_ID_HERE" -ForegroundColor Yellow
Write-Host "   ALPACA_API_SECRET_KEY=YOUR_SECRET_KEY_HERE" -ForegroundColor Yellow
Write-Host "   DEFAULT_USER_ID=demo" -ForegroundColor Yellow

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  EXAMPLE CONFIGURATION" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

$example = @"
USE_MOCK_BROKER=false
ALPACA_PAPER=true
ALPACA_API_KEY_ID=PKABCDEF1234567890123456
ALPACA_API_SECRET_KEY=abcdefghijklmnopqrstuvwxyz1234567890ABCD
DEFAULT_USER_ID=demo
"@

Write-Host $example -ForegroundColor Green

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  AFTER UPDATING .env" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

Write-Host "Run these commands to test:" -ForegroundColor White
Write-Host "  1. python test_alpaca_sync.py  # Test connection" -ForegroundColor Yellow
Write-Host "  2. python main.py              # Start server" -ForegroundColor Yellow
Write-Host "  3. Check dashboard             # Verify real data appears`n" -ForegroundColor Yellow

Write-Host "Need help? Check: .env.alpaca_example" -ForegroundColor Cyan
Write-Host ""
