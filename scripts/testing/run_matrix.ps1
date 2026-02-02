Param(
	[Parameter(ValueFromRemainingArguments = $true)]
	[string[]]$Args
)

# Simple PowerShell wrapper to run the Python matrix with stable defaults.
# Usage examples:
#   ./scripts/run_matrix.ps1 api
#   ./scripts/run_matrix.ps1 --with-coverage integration

$env:PYTHONFAULTHANDLER = "1"

# Support --with-coverage flag to set env var for Python script, if present.
if ($Args.Length -gt 0 -and $Args[0] -eq "--with-coverage") {
	$env:WITH_COV = "1"
}

python "$(Split-Path -Parent $PSCommandPath)\run_matrix.py" @Args
