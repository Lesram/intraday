$ErrorActionPreference = "Stop"

# Set JWT secret
$env:SECURITY_JWT_SECRET = "your-super-secret-jwt-key-for-development-only-change-in-production"

Write-Host "Starting server with JWT secret..."

# Start server and capture process info
$serverProcess = Start-Process -FilePath "uvicorn" -ArgumentList "backend.api.main:app", "--host", "0.0.0.0", "--port", "8000" -PassThru -WindowStyle Hidden

# Wait for server to start
Write-Host "Waiting for server startup..."
Start-Sleep 5

# Test basic connectivity
try {
    $health = Invoke-RestMethod -Uri "http://localhost:8000/health" -TimeoutSec 5
    Write-Host "✅ Server is running - Health: $($health.status)"
} catch {
    Write-Host "❌ Server not responding: $($_.Exception.Message)"
    Stop-Process -Id $serverProcess.Id -Force -ErrorAction SilentlyContinue
    exit 1
}

# Create auth token
Write-Host "Creating auth token..."
$token = python -c "
import sys, os
sys.path.append('.')
from backend.infra.security import create_access_token
print(create_access_token('admin', ['admin', 'trader'], 60), end='')
"

if (-not $token) {
    Write-Host "❌ Failed to create token"
    Stop-Process -Id $serverProcess.Id -Force -ErrorAction SilentlyContinue
    exit 1
}

Write-Host "✅ Token created: $($token.Substring(0,20))..."

# Test endpoints
Write-Host "`n=== PHASE G VALIDATION TESTS ==="

# Test 1: Health performance
Write-Host "`n1. Health endpoint performance:"
$times = @()
for ($i = 1; $i -le 5; $i++) {
    $start = Get-Date
    $response = Invoke-RestMethod -Uri "http://localhost:8000/health" -TimeoutSec 2
    $end = Get-Date
    $duration = ($end - $start).TotalMilliseconds
    $times += $duration
    Write-Host "   Request $i`: ${duration}ms"
}
$avgTime = ($times | Measure-Object -Average).Average
$p95Time = $times | Sort-Object | Select-Object -Index ([math]::Floor(0.95 * $times.Count))
Write-Host "   Average: ${avgTime}ms, P95: ${p95Time}ms"
if ($p95Time -lt 50) {
    Write-Host "   ✅ P95 < 50ms target achieved"
} else {
    Write-Host "   ❌ P95 > 50ms target"
}

# Test 2: Positions endpoint
Write-Host "`n2. Positions endpoint (authenticated):"
try {
    $headers = @{ "Authorization" = "Bearer $token" }
    $positions = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/positions" -Headers $headers -TimeoutSec 5
    Write-Host "   ✅ Status: 200, Positions count: $($positions.Count)"
} catch {
    $statusCode = $_.Exception.Response.StatusCode.value__
    Write-Host "   Status: $statusCode - $($_.Exception.Message)"
    if ($statusCode -eq 200) {
        Write-Host "   ✅ Endpoint working"
    } else {
        Write-Host "   ❌ Endpoint issue"
    }
}

# Test 3: Signals endpoint  
Write-Host "`n3. Signals endpoint (authenticated):"
try {
    $headers = @{ "Authorization" = "Bearer $token" }
    $signals = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/signals?symbol=AAPL" -Headers $headers -TimeoutSec 5
    Write-Host "   ✅ Status: 200, Action: $($signals.action)"
} catch {
    $statusCode = $_.Exception.Response.StatusCode.value__
    Write-Host "   Status: $statusCode - $($_.Exception.Message)"
    if ($statusCode -eq 200) {
        Write-Host "   ✅ Endpoint working"
    } else {
        Write-Host "   ❌ Endpoint issue"
    }
}

# Test 4: Authentication protection
Write-Host "`n4. Authentication protection test:"
try {
    $unauth = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/positions" -TimeoutSec 5
    Write-Host "   ❌ Unauthenticated request succeeded (should be 401)"
} catch {
    $statusCode = $_.Exception.Response.StatusCode.value__
    if ($statusCode -eq 401) {
        Write-Host "   ✅ Returns 401 for unauthenticated requests"
    } else {
        Write-Host "   ❌ Returns $statusCode instead of 401"
    }
}

Write-Host "`n=== RUNNING OFFICIAL VALIDATION ==="
try {
    python scripts/validate_checklist.py --api-token $token
    Write-Host "✅ Official validation completed"
} catch {
    Write-Host "❌ Official validation failed: $($_.Exception.Message)"
}

# Cleanup
Write-Host "`nCleaning up..."
Stop-Process -Id $serverProcess.Id -Force -ErrorAction SilentlyContinue
Write-Host "✅ Done"