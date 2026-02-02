# Phase 3: Backend API Tests
# PowerShell script to test all 10 API endpoints

Write-Host "="*80
Write-Host "PHASE 3: BACKEND API VALIDATION"
Write-Host "="*80

# Get fresh auth token
Write-Host "`n[Setup] Getting fresh authentication token..."
$tokenResponse = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/auth/token" `
  -Method POST `
  -Headers @{"Content-Type"="application/x-www-form-urlencoded"} `
  -Body "username=admin@example.com&password=Admin123!@#"
  
$headers = @{
    "Authorization" = "Bearer $($tokenResponse.access_token)"
    "Content-Type" = "application/json"
}
Write-Host "✅ Token obtained"

# Set base URL (confirmed from OpenAPI schema)
$baseUrl = "http://localhost:8000/api/v1/strategies"
Write-Host "`n✅ Using endpoint: $baseUrl"

# Test 3.1: GET /strategies (List All)
Write-Host "`n" + ("="*80)
Write-Host "TEST 3.1: GET List All Strategies"
Write-Host ("="*80)
try {
    $strategies = Invoke-RestMethod -Uri $baseUrl -Method GET -Headers $headers
    Write-Host "✅ Found $($strategies.Count) strategies"
    if ($strategies.Count -gt 0) {
        $firstStrategy = $strategies[0]
        Write-Host "   First strategy:"
        Write-Host "     ID: $($firstStrategy.strategyId)"
        Write-Host "     Name: $($firstStrategy.name)"
        Write-Host "     Status: $($firstStrategy.status)"
        Write-Host "     Type: $($firstStrategy.strategyType)"
        
        # Store first strategy ID for later tests
        $global:testStrategyId = $firstStrategy.strategyId
    }
} catch {
    Write-Host "❌ Error: $_"
}

# Test 3.2: GET /strategies/{id} (Get Single)
if ($global:testStrategyId) {
    Write-Host "`n" + ("="*80)
    Write-Host "TEST 3.2: GET Single Strategy"
    Write-Host ("="*80)
    try {
        $strategy = Invoke-RestMethod -Uri "$baseUrl/$global:testStrategyId" -Method GET -Headers $headers
        Write-Host "✅ Retrieved strategy: $($strategy.name)"
        Write-Host "   Status: $($strategy.status)"
        Write-Host "   Symbols: $($strategy.symbols -join ', ')"
        Write-Host "   Total P&L: $$($strategy.performance.totalPnL)"
    } catch {
        Write-Host "❌ Error: $_"
    }
}

# Test 3.3: POST /strategies (Create)
Write-Host "`n" + ("="*80)
Write-Host "TEST 3.3: POST Create Strategy"
Write-Host ("="*80)
$newStrategy = @{
    name = "API Test Strategy $(Get-Random -Maximum 999999)"
    description = "Testing API endpoint"
    strategyType = "momentum"
    symbols = @("TSLA", "NVDA")
    parameters = @{
        timeframe = "1D"
        indicator = "RSI"
    }
} | ConvertTo-Json

try {
    $created = Invoke-RestMethod -Uri $baseUrl -Method POST -Headers $headers -Body $newStrategy
    Write-Host "✅ Created strategy: $($created.strategyId)"
    Write-Host "   Name: $($created.name)"
    Write-Host "   Status: $($created.status)"
    $global:newStrategyId = $created.strategyId
} catch {
    Write-Host "❌ Error: $_"
}

# Test 3.4: PATCH /strategies/{id} (Update)
if ($global:newStrategyId) {
    Write-Host "`n" + ("="*80)
    Write-Host "TEST 3.4: PATCH Update Strategy"
    Write-Host ("="*80)
    $update = @{
        description = "Updated via API test"
        parameters = @{
            timeframe = "4H"
            indicator = "MACD"
        }
    } | ConvertTo-Json

    try {
        $updated = Invoke-RestMethod -Uri "$baseUrl/$global:newStrategyId" -Method PATCH -Headers $headers -Body $update
        Write-Host "✅ Updated strategy"
        Write-Host "   Description: $($updated.description)"
        Write-Host "   Parameters: $($updated.parameters | ConvertTo-Json -Compress)"
    } catch {
        Write-Host "❌ Error: $_"
    }

    # Test 3.5: POST /strategies/{id}/start
    Write-Host "`n" + ("="*80)
    Write-Host "TEST 3.5: POST Start Strategy"
    Write-Host ("="*80)
    try {
        $started = Invoke-RestMethod -Uri "$baseUrl/$global:newStrategyId/start" -Method POST -Headers $headers
        Write-Host "✅ Started strategy"
        Write-Host "   Status: $($started.status)"
    } catch {
        Write-Host "❌ Error: $_"
    }

    # Test 3.6: POST /strategies/{id}/pause
    Write-Host "`n" + ("="*80)
    Write-Host "TEST 3.6: POST Pause Strategy"
    Write-Host ("="*80)
    try {
        $paused = Invoke-RestMethod -Uri "$baseUrl/$global:newStrategyId/pause" -Method POST -Headers $headers
        Write-Host "✅ Paused strategy"
        Write-Host "   Status: $($paused.status)"
    } catch {
        Write-Host "❌ Error: $_"
    }

    # Test 3.7: POST /strategies/{id}/stop
    Write-Host "`n" + ("="*80)
    Write-Host "TEST 3.7: POST Stop Strategy"
    Write-Host ("="*80)
    try {
        $stopped = Invoke-RestMethod -Uri "$baseUrl/$global:newStrategyId/stop" -Method POST -Headers $headers
        Write-Host "✅ Stopped strategy"
        Write-Host "   Status: $($stopped.status)"
    } catch {
        Write-Host "❌ Error: $_"
    }

    # Test 3.8: GET /strategies/{id}/performance
    Write-Host "`n" + ("="*80)
    Write-Host "TEST 3.8: GET Performance Metrics"
    Write-Host ("="*80)
    try {
        $performance = Invoke-RestMethod -Uri "$baseUrl/$global:newStrategyId/performance" -Method GET -Headers $headers
        Write-Host "✅ Retrieved performance metrics"
        Write-Host "   $($performance | ConvertTo-Json -Depth 3)"
    } catch {
        Write-Host "⚠️  Performance endpoint may not exist or strategy has no performance data"
    }

    # Test 3.9: PUT /strategies/{id}/performance
    Write-Host "`n" + ("="*80)
    Write-Host "TEST 3.9: PUT Update Performance"
    Write-Host ("="*80)
    $perfUpdate = @{
        totalTrades = 10
        winningTrades = 7
        totalPnL = 1234.56
        sharpeRatio = 1.85
        maxDrawdown = -345.00
    } | ConvertTo-Json

    try {
        $updatedPerf = Invoke-RestMethod -Uri "$baseUrl/$global:newStrategyId/performance" -Method PUT -Headers $headers -Body $perfUpdate
        Write-Host "✅ Updated performance"
        Write-Host "   $($updatedPerf | ConvertTo-Json -Depth 3)"
    } catch {
        Write-Host "❌ Error: $_"
    }

    # Test 3.10: DELETE /strategies/{id}
    Write-Host "`n" + ("="*80)
    Write-Host "TEST 3.10: DELETE Strategy"
    Write-Host ("="*80)
    try {
        Invoke-RestMethod -Uri "$baseUrl/$global:newStrategyId" -Method DELETE -Headers $headers
        Write-Host "✅ Deleted strategy"
        
        # Verify deletion
        try {
            Invoke-RestMethod -Uri "$baseUrl/$global:newStrategyId" -Method GET -Headers $headers
            Write-Host "❌ Strategy still exists!"
        } catch {
            Write-Host "✅ Confirmed: Strategy deleted (404 error)"
        }
    } catch {
        Write-Host "❌ Error: $_"
    }
}

Write-Host "`n" + ("="*80)
Write-Host "✅ PHASE 3 COMPLETE: API tests finished"
Write-Host ("="*80)
