# PowerShell Test Preparation Wrapper
# Simplified execution of comprehensive test preparation

param(
    [switch]$RunTests,
    [switch]$QuickCheck,
    [string]$OutputFile = "test_preparation_results.json"
)

Write-Host "🚀 Algorithm Trading Platform - Test Preparation" -ForegroundColor Green
Write-Host "=" * 60

# Ensure we're in the right directory
$ProjectRoot = Split-Path $MyInvocation.MyCommand.Path -Parent
Set-Location $ProjectRoot

Write-Host "📂 Project Directory: $ProjectRoot" -ForegroundColor Cyan

# Check if virtual environment activation is needed
$VenvPath = Join-Path $ProjectRoot "venv\Scripts\Activate.ps1"
if (Test-Path $VenvPath) {
    Write-Host "🐍 Activating virtual environment..." -ForegroundColor Yellow
    & $VenvPath
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Virtual environment activated" -ForegroundColor Green
    } else {
        Write-Host "❌ Failed to activate virtual environment" -ForegroundColor Red
    }
} else {
    Write-Host "⚠️ Virtual environment not found at: $VenvPath" -ForegroundColor Yellow
}

# Run the Python preparation script
Write-Host "`n🔍 Running comprehensive preparation checks..." -ForegroundColor Cyan

if ($QuickCheck) {
    Write-Host "⚡ Quick check mode - basic validation only" -ForegroundColor Yellow
    python -c "
import subprocess, sys
from pathlib import Path

# Quick checks
checks = [
    (['python', '--version'], 'Python Version'),
    (['python', '-m', 'pytest', '--version'], 'Pytest'),
    (['python', '-c', 'import backend; print(\"Backend module OK\")'], 'Backend Import')
]

for cmd, name in checks:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print(f'✅ {name}: {result.stdout.strip().split()[0] if result.stdout else \"OK\"}')
        else:
            print(f'❌ {name}: FAILED')
    except Exception as e:
        print(f'❌ {name}: ERROR - {str(e)[:50]}')
"
} else {
    # Run full comprehensive check
    python test_preparation_script.py
}

# Check if results file was created
if (Test-Path $OutputFile) {
    Write-Host "`n📄 Results saved to: $OutputFile" -ForegroundColor Green
    
    # Show summary from results
    try {
        $Results = Get-Content $OutputFile | ConvertFrom-Json
        Write-Host "`n📊 SUMMARY:" -ForegroundColor Cyan
        Write-Host "⏰ Timestamp: $($Results.timestamp)"
        Write-Host "✅ Checks completed: $($Results.checks.Count)"
        Write-Host "⚠️ Issues found: $($Results.issues_found.Count)"
        Write-Host "💡 Solutions applied: $($Results.solutions_applied.Count)"
        
        if ($Results.recommended_command) {
            Write-Host "`n🎯 READY TO EXECUTE TESTS" -ForegroundColor Green
            if ($RunTests) {
                Write-Host "🚀 Executing tests automatically..." -ForegroundColor Yellow
                Invoke-Expression $Results.recommended_command
            } else {
                Write-Host "`n💡 To run tests, use: .\test_preparation_script.ps1 -RunTests" -ForegroundColor Cyan
            }
        }
    } catch {
        Write-Host "⚠️ Could not parse results file" -ForegroundColor Yellow
    }
}

Write-Host "`n✅ Test preparation completed!" -ForegroundColor Green
Write-Host "=" * 60
