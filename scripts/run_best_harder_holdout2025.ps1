param(
    [Parameter(Mandatory = $false)]
    [string]$ConfigPath = "configs/optuna_best_harder_holdout2025.json",

    [Parameter(Mandatory = $false)]
    [ValidateSet('close','next_open')]
    [string]$ExecutionMode = 'close'
)

$ErrorActionPreference = 'Stop'

# Ensure imports resolve correctly when running from workspace root.
$env:PYTHONPATH = (Resolve-Path .).Path

# Eval-only mode reads the JSON config and skips Optuna.
$env:OPT_EVAL_ONLY = '1'
$env:OPT_EVAL_APPLY_ENV = '1'
$env:OPT_EXECUTION_MODE = $ExecutionMode

$resolvedConfig = Resolve-Path -Path $ConfigPath -ErrorAction Stop
$env:OPT_EVAL_PARAMS_PATH = $resolvedConfig.Path

$venvPython = Join-Path -Path (Resolve-Path .).Path -ChildPath 'venv\Scripts\python.exe'
if (Test-Path -Path $venvPython) {
    & $venvPython scripts/optuna_meta_strategy_optimizer.py
}
else {
    python scripts/optuna_meta_strategy_optimizer.py
}
