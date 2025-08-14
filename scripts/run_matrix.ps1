# Cross-platform friendly PowerShell wrapper to run the matrix test runner
# Ensures PYTHONPATH includes the project for backend imports, then runs the Python script.

$ErrorActionPreference = 'Stop'

# Resolve script directory => algotrading_platform/scripts
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir

# Prepend project to PYTHONPATH
$env:PYTHONPATH = if ($env:PYTHONPATH) { "$ProjectDir;$env:PYTHONPATH" } else { "$ProjectDir" }

Write-Host "PYTHONPATH=$env:PYTHONPATH"

# Use current Python in PATH/venv
python "$ScriptDir/run_matrix.py"
