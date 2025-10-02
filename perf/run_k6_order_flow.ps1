#!/usr/bin/env pwsh

<#
.SYNOPSIS
    Run K6 Order Flow Performance Test
.DESCRIPTION
    Executes the K6 performance test for the order flow API endpoints with proper authentication
.EXAMPLE
    .\run_k6_order_flow.ps1
.EXAMPLE
    .\run_k6_order_flow.ps1 -VUs 5 -Duration "2m"
#>

param(
    [int]$VUs = 5,
    [string]$Duration = "1m",
    [string]$BaseUrl = "http://localhost:8000",
    [string]$StagingApiKey = "",
    [string]$TestSymbol = "AAPL",
    [int]$OrderQty = 10
)

Write-Host "🚀 Starting K6 Order Flow Performance Test" -ForegroundColor Green
Write-Host "Configuration:" -ForegroundColor Yellow
Write-Host "  - Virtual Users: $VUs" -ForegroundColor Cyan  
Write-Host "  - Duration: $Duration" -ForegroundColor Cyan
Write-Host "  - Base URL: $BaseUrl" -ForegroundColor Cyan
Write-Host "  - Test Symbol: $TestSymbol" -ForegroundColor Cyan
Write-Host "  - Order Quantity: $OrderQty" -ForegroundColor Cyan

# Check if K6 is installed
if (-not (Get-Command "k6" -ErrorAction SilentlyContinue)) {
    Write-Host "❌ K6 is not installed. Please install K6 first:" -ForegroundColor Red
    Write-Host "   Windows: winget install k6" -ForegroundColor Yellow
    Write-Host "   Or download from: https://k6.io/docs/get-started/installation/" -ForegroundColor Yellow
    exit 1
}

# Check if server is running
try {
    $healthCheck = Invoke-RestMethod -Uri "$BaseUrl/health" -Method GET -TimeoutSec 5
    Write-Host "✅ Server is running" -ForegroundColor Green
} catch {
    Write-Host "❌ Server is not responding at $BaseUrl" -ForegroundColor Red
    Write-Host "   Please start the server first: uvicorn backend.api.main:app --host 0.0.0.0 --port 8000" -ForegroundColor Yellow
    exit 1
}

# Set environment variables
$env:BASE_URL = $BaseUrl
$env:TEST_SYMBOL = $TestSymbol
$env:ORDER_QTY = $OrderQty

# Set API key if provided
if ($StagingApiKey) {
    $env:STAGING_API_KEY = $StagingApiKey
    Write-Host "✅ Using provided staging API key" -ForegroundColor Green
} else {
    Write-Host "⚠️  No staging API key provided - will attempt login authentication" -ForegroundColor Yellow
}

# Run K6 test
Write-Host "`n🏃 Running K6 test..." -ForegroundColor Green

$k6Options = "--vus $VUs --duration $Duration"
$k6Command = "k6 run $k6Options perf/k6_order_flow.js"

Write-Host "Command: $k6Command" -ForegroundColor Gray
Write-Host ""

try {
    Invoke-Expression $k6Command
    $exitCode = $LASTEXITCODE
    
    if ($exitCode -eq 0) {
        Write-Host "`n🎉 K6 test completed successfully!" -ForegroundColor Green
    } else {
        Write-Host "`n❌ K6 test failed with exit code $exitCode" -ForegroundColor Red
    }
    
    exit $exitCode
} catch {
    Write-Host "`n❌ Failed to run K6 test: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}