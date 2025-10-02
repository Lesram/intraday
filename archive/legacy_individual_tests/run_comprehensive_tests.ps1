# Comprehensive Testing Suite - Layer 5 + K6 Performance
# =========================================================
# Combines business workflow testing with performance testing

param(
    [string]$BaseUrl = "http://localhost:8000",
    [string]$OutputFile = $null,
    [switch]$Layer5Only,
    [switch]$K6Only,
    [switch]$Quick,
    [switch]$Help
)

function Show-Help {
    Write-Host "Comprehensive Testing Suite - Layer 5 + K6 Performance" -ForegroundColor Cyan
    Write-Host "=========================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "USAGE:" -ForegroundColor Yellow
    Write-Host "  .\run_comprehensive_tests.ps1 [OPTIONS]"
    Write-Host ""
    Write-Host "OPTIONS:" -ForegroundColor Yellow
    Write-Host "  -BaseUrl <url>     Base URL for API server (default: http://localhost:8000)"
    Write-Host "  -OutputFile <file> Custom output file for results"
    Write-Host "  -Layer5Only        Run only Layer 5 business workflow tests"
    Write-Host "  -K6Only           Run only K6 performance tests"  
    Write-Host "  -Quick            Quick validation (reduced test scope)"
    Write-Host "  -Help             Show this help message"
    Write-Host ""
    Write-Host "EXAMPLES:" -ForegroundColor Yellow
    Write-Host "  .\run_comprehensive_tests.ps1"
    Write-Host "  .\run_comprehensive_tests.ps1 -Layer5Only"
    Write-Host "  .\run_comprehensive_tests.ps1 -K6Only -BaseUrl http://staging.example.com"
    Write-Host "  .\run_comprehensive_tests.ps1 -Quick -OutputFile quick_test_results.json"
    Write-Host ""
    Write-Host "DESCRIPTION:" -ForegroundColor Green
    Write-Host "  Layer 5: Business workflow testing with 100% coverage validation"
    Write-Host "  K6:      Performance testing across 5 integrated scenarios"
    Write-Host "  Result:  Comprehensive platform validation report"
}

if ($Help) {
    Show-Help
    exit 0
}

Write-Host "COMPREHENSIVE TESTING SUITE" -ForegroundColor Cyan
Write-Host "===========================" -ForegroundColor Cyan
Write-Host "Layer 5: Business Workflow Testing" -ForegroundColor Green
Write-Host "K6:      Performance Testing (5 scenarios)" -ForegroundColor Green
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
    
    # Ensure Python environment is configured
    Write-Host "Configuring Python environment..." -ForegroundColor Yellow
    
    # Check for requirements
    if (-not (Test-Path "requirements.txt")) {
        Write-Host "❌ requirements.txt not found" -ForegroundColor Red
        exit 1
    }
    
    # Build Python command arguments
    $pythonArgs = @(
        "scripts\testing\test_comprehensive_suite.py",
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
    } else {
        Write-Host "Mode: Comprehensive Testing (Layer 5 + K6)" -ForegroundColor Cyan
    }
    
    Write-Host ""
    Write-Host "Starting comprehensive testing suite..." -ForegroundColor Green
    Write-Host "=======================================" -ForegroundColor Green
    
    # Run the comprehensive test suite
    $startTime = Get-Date
    
    & python @pythonArgs
    $exitCode = $LASTEXITCODE
    
    $endTime = Get-Date
    $duration = $endTime - $startTime
    
    Write-Host ""
    Write-Host "=======================================" -ForegroundColor Green
    Write-Host "Testing completed in $($duration.TotalSeconds.ToString('F1')) seconds" -ForegroundColor Green
    
    if ($exitCode -eq 0) {
        Write-Host "✅ COMPREHENSIVE TESTING: SUCCESS" -ForegroundColor Green
        Write-Host "   Platform validation completed successfully!" -ForegroundColor Green
        
        if (-not ($Layer5Only -or $K6Only)) {
            Write-Host ""
            Write-Host "VALIDATION SUMMARY:" -ForegroundColor Cyan
            Write-Host "  ✅ Business Workflows: Layer 5 testing passed" -ForegroundColor Green  
            Write-Host "  ✅ Performance: K6 testing passed" -ForegroundColor Green
            Write-Host "  🎉 Platform ready for production deployment!" -ForegroundColor Green
        }
    } else {
        Write-Host "❌ COMPREHENSIVE TESTING: ISSUES DETECTED" -ForegroundColor Red
        Write-Host "   Please review the test results above" -ForegroundColor Yellow
        Write-Host "   Address any failures before deployment" -ForegroundColor Yellow
    }
    
    # Results location
    $resultsDir = Join-Path $workspaceDir "test_results"
    if (Test-Path $resultsDir) {
        Write-Host ""
        Write-Host "Test results saved to: $resultsDir" -ForegroundColor Cyan
        
        $latestResult = Get-ChildItem $resultsDir -Filter "comprehensive_test_results_*.json" | 
                       Sort-Object LastWriteTime -Descending | 
                       Select-Object -First 1
        
        if ($latestResult) {
            Write-Host "Latest result file: $($latestResult.Name)" -ForegroundColor Cyan
        }
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