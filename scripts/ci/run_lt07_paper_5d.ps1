$ErrorActionPreference = 'Stop'
$env:PYTHONPATH = (Resolve-Path .).Path

$cmd = @(
    'venv/Scripts/python.exe',
    'scripts/ci/run_organism_live_acceptance.py',
    '--mode', 'LT07',
    '--duration-hours', '120',
    '--interval-seconds', '300'
)

Write-Host "Running LT-07 paper acceptance (5 days)..." -ForegroundColor Cyan
& $cmd[0] $cmd[1..($cmd.Length-1)]
