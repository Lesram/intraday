$ErrorActionPreference = 'Stop'
$env:PYTHONPATH = (Resolve-Path .).Path

$cmd = @(
    'venv/Scripts/python.exe',
    'scripts/ci/run_organism_live_acceptance.py',
    '--mode', 'LT06',
    '--duration-hours', '24',
    '--interval-seconds', '300'
)

Write-Host "Running LT-06 paper acceptance (24h)..." -ForegroundColor Cyan
& $cmd[0] $cmd[1..($cmd.Length-1)]
