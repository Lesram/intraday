#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Run K6 authorized smoke test for Phase G gate validation
    
.DESCRIPTION
    Executes K6 performance testing against the local trading platform API
    with proper authentication and performance threshold validation.
    
    Requires: K6 installation (https://k6.io/docs/getting-started/installation/)
    
.PARAMETER ApiKey
    Optional STAGING_API_KEY for authentication (uses JWT login if not provided)
    
.PARAMETER BaseUrl
    Base URL for the API (default: http://localhost:8000)
    
.PARAMETER Username
    Username for JWT authentication (default: admin)
    
.PARAMETER Password
    Password for JWT authentication (default: admin123)
    
.EXAMPLE
    .\scripts\run_k6_smoke.ps1
    
.EXAMPLE
    .\scripts\run_k6_smoke.ps1 -ApiKey "your-api-key-here"
    
.EXAMPLE
    .\scripts\run_k6_smoke.ps1 -BaseUrl "http://localhost:8080" -Username "testuser"
#>

param(
    [string]$ApiKey,
    [string]$BaseUrl = "http://localhost:8000",
    [string]$Username = "admin", 
    [string]$Password = "admin123"
)

# Set error handling
$ErrorActionPreference = "Stop"

# Color functions for output
function Write-Success($Message) { 
    Write-Host "✅ $Message" -ForegroundColor Green 
}

function Write-Error($Message) { 
    Write-Host "❌ $Message" -ForegroundColor Red 
}

function Write-Info($Message) { 
    Write-Host "ℹ️  $Message" -ForegroundColor Cyan 
}

function Write-Warning($Message) { 
    Write-Host "⚠️  $Message" -ForegroundColor Yellow 
}

# Check if K6 is installed
Write-Info "Checking K6 installation..."
try {
    $k6Version = & k6 version 2>$null
    Write-Success "K6 found: $($k6Version -split "`n" | Select-Object -First 1)"
} catch {
    Write-Error "K6 is not installed or not in PATH"
    Write-Info "Please install K6 from: https://k6.io/docs/getting-started/installation/"
    Write-Info "For Windows: choco install k6  OR  winget install k6"
    exit 1
}

# Verify API is running
Write-Info "Checking if API is running at $BaseUrl..."
try {
    $healthCheck = Invoke-RestMethod -Uri "$BaseUrl/health" -Method GET -TimeoutSec 5
    if ($healthCheck.status -eq "ok") {
        Write-Success "API is running and healthy"
    } else {
        Write-Warning "API responded but health check returned: $($healthCheck | ConvertTo-Json)"
    }
} catch {
    Write-Error "API is not responding at $BaseUrl"
    Write-Info "Please ensure the backend server is running (e.g., python main.py)"
    exit 1
}

# Prepare environment variables for K6
$env:BASE_URL = $BaseUrl
$env:USERNAME = $Username  
$env:PASSWORD = $Password

if ($ApiKey) {
    $env:STAGING_API_KEY = $ApiKey
    Write-Info "Using provided API key for authentication"
} else {
    Write-Info "Will use JWT login with username: $Username"
}

# Run K6 smoke test
Write-Info "Starting K6 authorized smoke test..."
Write-Info "Configuration:"
Write-Host "  • Base URL: $BaseUrl" -ForegroundColor Gray
Write-Host "  • Auth Method: $(if ($ApiKey) { 'API Key' } else { 'JWT Login' })" -ForegroundColor Gray
Write-Host "  • Test Duration: ~2 minutes" -ForegroundColor Gray
Write-Host "  • Virtual Users: 2-5" -ForegroundColor Gray

try {
    # Run the K6 test
    & k6 run perf/k6_auth_smoke.js
    
    $k6ExitCode = $LASTEXITCODE
    
    if ($k6ExitCode -eq 0) {
        Write-Success "K6 smoke test completed successfully! All performance thresholds met."
        Write-Info "✅ Performance validation: PASS"
    } else {
        Write-Error "K6 smoke test failed with exit code: $k6ExitCode"
        Write-Warning "Check the output above for threshold failures or errors"
        Write-Info "❌ Performance validation: FAIL"
    }
    
} catch {
    Write-Error "Failed to run K6 test: $($_.Exception.Message)"
    exit 1
} finally {
    # Clean up environment variables
    Remove-Item Env:BASE_URL -ErrorAction SilentlyContinue
    Remove-Item Env:USERNAME -ErrorAction SilentlyContinue  
    Remove-Item Env:PASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:STAGING_API_KEY -ErrorAction SilentlyContinue
}

Write-Info "K6 smoke test execution completed."

# Return appropriate exit code
exit $k6ExitCode