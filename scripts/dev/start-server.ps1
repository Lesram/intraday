#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Start Algorithmic Trading Platform Server
.DESCRIPTION
    Starts the FastAPI server with proper configuration and environment variables.
    This script should be run in a separate terminal window.
.EXAMPLE
    .\start-server.ps1
    .\start-server.ps1 -Port 8001 -Development
#>

param(
    [int]$Port = 8000,
    [string]$Host = "0.0.0.0", 
    [switch]$Development,
    [switch]$Reload
)

# Set console title
$Host.UI.RawUI.WindowTitle = "Trading Platform Server - Port $Port"

# Colors for output
$InfoColor = "Cyan"
$SuccessColor = "Green"
$WarningColor = "Yellow"
$ErrorColor = "Red"

Write-Host ""
Write-Host "🚀 ALGORITHMIC TRADING PLATFORM SERVER" -ForegroundColor $SuccessColor
Write-Host "=" * 50 -ForegroundColor $InfoColor
Write-Host "Port: $Port" -ForegroundColor $InfoColor
Write-Host "Host: $Host" -ForegroundColor $InfoColor
Write-Host "Environment: $(if ($Development) { 'Development' } else { 'Production' })" -ForegroundColor $InfoColor
Write-Host "=" * 50 -ForegroundColor $InfoColor

# Ensure virtual environment is activated
if (-not $env:VIRTUAL_ENV) {
    Write-Host "⚠️  Virtual environment not detected. Activating..." -ForegroundColor $WarningColor
    if (Test-Path ".\venv\Scripts\Activate.ps1") {
        & ".\venv\Scripts\Activate.ps1"
        Write-Host "✅ Virtual environment activated" -ForegroundColor $SuccessColor
    } else {
        Write-Host "❌ Virtual environment not found! Please run setup first." -ForegroundColor $ErrorColor
        exit 1
    }
}

# Set required environment variables
Write-Host "🔐 Setting up environment variables..." -ForegroundColor $InfoColor

# Set JWT secret (required for server startup)
if (-not $env:SECURITY_JWT_SECRET) {
    $env:SECURITY_JWT_SECRET = "your-super-secret-jwt-key-change-in-production-minimum-32-chars"
    Write-Host "✅ JWT secret configured" -ForegroundColor $SuccessColor
}

# Set development mode if specified
if ($Development) {
    $env:ENVIRONMENT = "development"
    $Reload = $true
} else {
    $env:ENVIRONMENT = "production"
}

# Database setup - REQUIRED
if (-not $env:DATABASE_URL) {
    Write-Host "" 
    Write-Host "❌ DATABASE_URL environment variable is required but not set!" -ForegroundColor Red
    Write-Host ""
    Write-Host "To start PostgreSQL with Docker:" -ForegroundColor Yellow
    Write-Host "  docker-compose up -d db" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Then set DATABASE_URL:" -ForegroundColor Yellow
    Write-Host "  `$env:DATABASE_URL='postgresql+asyncpg://trading:trading_password@localhost:5432/algotrading'" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Or source your .env file (if configured)" -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

Write-Host "✅ Database URL configured: $($env:DATABASE_URL.Substring(0, [Math]::Min(50, $env:DATABASE_URL.Length)))..." -ForegroundColor $SuccessColor

Write-Host ""
Write-Host "🌐 Server will be available at:" -ForegroundColor $SuccessColor
Write-Host "   API: http://localhost:$Port" -ForegroundColor $InfoColor
Write-Host "   Docs: http://localhost:$Port/docs" -ForegroundColor $InfoColor
Write-Host "   Health: http://localhost:$Port/health" -ForegroundColor $InfoColor
Write-Host ""

# Determine startup method
$UseMainPy = Test-Path ".\main.py"
$HasUvicorn = (Get-Command uvicorn -ErrorAction SilentlyContinue) -ne $null

if ($UseMainPy) {
    Write-Host "🚀 Starting server using main.py..." -ForegroundColor $InfoColor
    Write-Host "Press Ctrl+C to stop the server" -ForegroundColor $WarningColor
    Write-Host ""
    
    try {
        python main.py
    } catch {
        Write-Host "❌ Failed to start server using main.py" -ForegroundColor $ErrorColor
        Write-Host "Error: $_" -ForegroundColor $ErrorColor
        exit 1
    }
} elseif ($HasUvicorn) {
    Write-Host "🚀 Starting server using uvicorn..." -ForegroundColor $InfoColor  
    Write-Host "Press Ctrl+C to stop the server" -ForegroundColor $WarningColor
    Write-Host ""
    
    $UvicornArgs = @(
        "backend.api.main:app",
        "--host", $Host,
        "--port", $Port.ToString()
    )
    
    if ($Reload) {
        $UvicornArgs += "--reload"
    }
    
    try {
        & uvicorn @UvicornArgs
    } catch {
        Write-Host "❌ Failed to start server using uvicorn" -ForegroundColor $ErrorColor
        Write-Host "Error: $_" -ForegroundColor $ErrorColor
        exit 1
    }
} else {
    Write-Host "❌ Neither main.py nor uvicorn found!" -ForegroundColor $ErrorColor
    Write-Host "Please ensure the project is properly set up." -ForegroundColor $ErrorColor
    exit 1
}

Write-Host ""
Write-Host "👋 Server stopped" -ForegroundColor $WarningColor