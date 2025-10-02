# Enhanced Comprehensive Testing Suite - Layer 5 + K6 + Phase G
# ============================================================
# Integrates all testing components including missing Phase G tests

param(
    [string]$BaseUrl = "http://localhost:8000",
    [string]$OutputFile = $null,
    [switch]$Layer5Only,
    [switch]$K6Only,
    [switch]$PhaseGOnly,
    [switch]$Quick,
    [switch]$Help
)

function Show-Help {
    Write-Host "Enhanced Comprehensive Testing Suite - Complete Integration" -ForegroundColor Cyan
    Write-Host "=========================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "USAGE:" -ForegroundColor Yellow
    Write-Host "  .\run_enhanced_comprehensive_tests.ps1 [OPTIONS]"
    Write-Host ""
    Write-Host "OPTIONS:" -ForegroundColor Yellow
    Write-Host "  -BaseUrl <url>     Base URL for API server (default: http://localhost:8000)"
    Write-Host "  -OutputFile <file> Custom output file for results"
    Write-Host "  -Layer5Only        Run only Layer 5 business workflow tests"
    Write-Host "  -K6Only           Run only K6 performance tests"  
    Write-Host "  -PhaseGOnly       Run only Phase G integration tests"
    Write-Host "  -Quick            Quick validation (reduced test scope)"
    Write-Host "  -Help             Show this help message"
    Write-Host ""
    Write-Host "EXAMPLES:" -ForegroundColor Yellow
    Write-Host "  .\run_enhanced_comprehensive_tests.ps1"
    Write-Host "  .\run_enhanced_comprehensive_tests.ps1 -PhaseGOnly"
    Write-Host "  .\run_enhanced_comprehensive_tests.ps1 -Layer5Only -Quick"
    Write-Host "  .\run_enhanced_comprehensive_tests.ps1 -OutputFile enhanced_results.json"
    Write-Host ""
    Write-Host "TEST CATEGORIES:" -ForegroundColor Green
    Write-Host "  Layer 5:  Business workflow testing (100% coverage validation)"
    Write-Host "  K6:       Performance testing (5 integrated scenarios)"
    Write-Host "  Phase G:  Integration testing (7 categories):"
    Write-Host "    - Health Performance Validation (<50ms P95 target)"
    Write-Host "    - Python Asyncio Load Testing (K6 alternative)"
    Write-Host "    - API Integration Testing (FastAPI/routes)"
    Write-Host "    - Database Persistence Testing"
    Write-Host "    - Real Server Integration Testing"
    Write-Host "    - Paper Trading Integration"
    Write-Host "    - Comprehensive Flow Validation"
}

if ($Help) {
    Show-Help
    exit 0
}

Write-Host "ENHANCED COMPREHENSIVE TESTING SUITE" -ForegroundColor Cyan
Write-Host "====================================" -ForegroundColor Cyan
Write-Host "Layer 5: Business Workflow Testing" -ForegroundColor Green
Write-Host "K6:      Performance Testing (5 scenarios)" -ForegroundColor Green
Write-Host "Phase G: Integration Testing (7 categories)" -ForegroundColor Green
Write-Host "Target:  $BaseUrl" -ForegroundColor Yellow
Write-Host ""

# Check if server is running
Write-Host "Checking server health..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "$BaseUrl/health" -TimeoutSec 5 -ErrorAction Stop
    if ($response.StatusCode -eq 200) {
        Write-Host "✅ Server healthy at $BaseUrl" -ForegroundColor Green
    } else {
        Write-Host "⚠️  Server responded with status $($response.StatusCode)" -ForegroundColor Yellow
    }
} catch {
    Write-Host "❌ Server not accessible at $BaseUrl" -ForegroundColor Red
    Write-Host "   Please ensure the platform is running before testing" -ForegroundColor Yellow
    Write-Host "   You can start it with: python main.py" -ForegroundColor Yellow
    exit 1
}

# Set up environment
$ErrorActionPreference = "Stop"
$originalPath = Get-Location
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$workspaceDir = Split-Path -Parent (Split-Path -Parent $scriptDir)

try {
    Set-Location $workspaceDir
    
    # Set environment variables for Phase G testing
    $env:SECURITY_JWT_SECRET = "your-super-secret-jwt-key-min-32-chars-long-12345"
    $env:ALPACA_API_KEY_ID = "PK6HHOLVI6KJ2DTESPKR"
    $env:ALPACA_API_SECRET_KEY = "vpuCh1GHrr6NBjIecJdc8dGQRa0f302vSmD8kM7W"
    $env:ALPACA_PAPER = "true"
    $env:USE_MOCK_BROKER = "false"
    
    Write-Host "Configuring Python environment..." -ForegroundColor Yellow
    
    # Check for requirements
    if (-not (Test-Path "requirements.txt")) {
        Write-Host "❌ requirements.txt not found" -ForegroundColor Red
        exit 1
    }
    
    # Build Python command arguments
    $pythonArgs = @(
        "scripts\testing\test_enhanced_comprehensive_suite.py",
        "--base-url", $BaseUrl
    )
    
    if ($OutputFile) {
        $pythonArgs += "--output", $OutputFile
    }
    
    if ($Layer5Only) {
        $pythonArgs += "--layer5-only"
        Write-Host "Mode: Layer 5 Business Workflow Tests Only" -ForegroundColor Cyan
    } elseif ($K6Only) {
        $pythonArgs += "--k6-only"
        Write-Host "Mode: K6 Performance Tests Only" -ForegroundColor Cyan
    } elseif ($PhaseGOnly) {
        $pythonArgs += "--phase-g-only"
        Write-Host "Mode: Phase G Integration Tests Only" -ForegroundColor Cyan
    } else {
        Write-Host "Mode: Enhanced Comprehensive Testing (Layer 5 + K6 + Phase G)" -ForegroundColor Cyan
    }
    
    Write-Host ""
    Write-Host "Starting enhanced comprehensive testing suite..." -ForegroundColor Green
    Write-Host "===============================================" -ForegroundColor Green
    
    # Run the enhanced comprehensive test suite
    $startTime = Get-Date
    
    & python @pythonArgs
    $exitCode = $LASTEXITCODE
    
    $endTime = Get-Date
    $duration = $endTime - $startTime
    
    Write-Host ""
    Write-Host "===============================================" -ForegroundColor Green
    Write-Host "Testing completed in $($duration.TotalSeconds.ToString('F1')) seconds" -ForegroundColor Green
    
    if ($exitCode -eq 0) {
        Write-Host "✅ ENHANCED COMPREHENSIVE TESTING: SUCCESS" -ForegroundColor Green
        Write-Host "   Platform validation completed successfully!" -ForegroundColor Green
        
        if (-not ($Layer5Only -or $K6Only -or $PhaseGOnly)) {
            Write-Host ""
            Write-Host "VALIDATION SUMMARY:" -ForegroundColor Cyan
            Write-Host "  ✅ Layer 5: Business workflows validated (100% coverage)" -ForegroundColor Green
            Write-Host "  ✅ K6: Performance testing passed (5 scenarios)" -ForegroundColor Green
            Write-Host "  ✅ Phase G: Integration testing completed (7 categories)" -ForegroundColor Green
            Write-Host "  🎉 Platform ready for production deployment!" -ForegroundColor Green
        }
    } else {
        Write-Host "❌ ENHANCED COMPREHENSIVE TESTING: ISSUES DETECTED" -ForegroundColor Red
        Write-Host "   Please review the test results above" -ForegroundColor Yellow
        Write-Host "   Address any failures before deployment" -ForegroundColor Yellow
        
        if (-not ($Layer5Only -or $K6Only -or $PhaseGOnly)) {
            Write-Host ""
            Write-Host "DEBUGGING SUGGESTIONS:" -ForegroundColor Yellow
            Write-Host "  🔍 Run individual test categories to isolate issues:"
            Write-Host "     .\run_enhanced_comprehensive_tests.ps1 -Layer5Only"
            Write-Host "     .\run_enhanced_comprehensive_tests.ps1 -K6Only"
            Write-Host "     .\run_enhanced_comprehensive_tests.ps1 -PhaseGOnly"
            Write-Host "  📊 Check test results JSON for detailed error information"
            Write-Host "  🔧 Verify server is running with all required dependencies"
        }
    }
    
    # Results location
    $resultsDir = Join-Path $workspaceDir "test_results"
    if (Test-Path $resultsDir) {
        Write-Host ""
        Write-Host "Test results saved to: $resultsDir" -ForegroundColor Cyan
        
        $latestResult = Get-ChildItem $resultsDir -Filter "enhanced_*test_results_*.json" -ErrorAction SilentlyContinue | 
                       Sort-Object LastWriteTime -Descending | 
                       Select-Object -First 1
        
        if ($latestResult) {
            Write-Host "Latest result file: $($latestResult.Name)" -ForegroundColor Cyan
        }
    }
    
    # Show Phase G specific information
    if ($PhaseGOnly -or (-not ($Layer5Only -or $K6Only))) {
        Write-Host ""
        Write-Host "PHASE G INTEGRATION DETAILS:" -ForegroundColor Cyan
        Write-Host "  📊 Health Performance: P95 response time validation (<50ms)"
        Write-Host "  🚀 Python Load Testing: Asyncio-based K6 alternative"
        Write-Host "  🔌 API Integration: FastAPI app and route validation"
        Write-Host "  💾 Database Persistence: Order service and DB validation"
        Write-Host "  🌐 Real Server Integration: Live endpoint testing"
        Write-Host "  📈 Paper Trading: Alpaca integration validation"
        Write-Host "  🔄 Comprehensive Flow: End-to-end business logic"
    }
    
    exit $exitCode
    
} catch {
    Write-Host ""
    Write-Host "❌ ERROR: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Stack trace: $($_.ScriptStackTrace)" -ForegroundColor Yellow
    exit 1
    
} finally {
    Set-Location $originalPath
}