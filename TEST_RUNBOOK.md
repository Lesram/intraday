# Test Matrix Runner - Runbook

This project includes a simple test matrix runner that executes pytest in logical subsets, producing JUnit XML and merged coverage artifacts.

## Quick start (Windows / PowerShell)

- From the repo root (folder containing `algotrading_platform/`):
  - `powershell -ExecutionPolicy Bypass -File algotrading_platform/scripts/run_matrix.ps1`

This wrapper sets `PYTHONPATH` to include `algotrading_platform/` and then runs the Python matrix runner.

## Quick start (Any OS)

- From the `algotrading_platform/` directory:
  - Ensure your venv is activated (optional but recommended)
  - `python scripts/run_matrix.py`

## What it runs

Subsets (skipped if the folder doesn't exist):
- `tests/api`
- `tests/ws`
- `tests/mlops`
- `tests/services`
- `tests/risk`
- `tests/integration`

Each subset run:
- Writes JUnit XML to `algotrading_platform/test_reports/junit/<subset>.xml`
- Merges coverage into `algotrading_platform/test_reports/coverage.xml`
- Writes HTML coverage into `algotrading_platform/test_reports/coverage_html/`

The runner clears pytest `addopts` to avoid repo-specific strict gates during matrix runs.

## Outputs

- JUnit XML directory: `algotrading_platform/test_reports/junit/`
- Coverage XML: `algotrading_platform/test_reports/coverage.xml`
- Coverage HTML: `algotrading_platform/test_reports/coverage_html/index.html`

## Tips

- To run a single subset directly with the same settings, you can mimic the command the runner uses:
  - `python -m pytest tests/api --junitxml algotrading_platform/test_reports/junit/api.xml --cov=backend --cov-report=xml:algotrading_platform/test_reports/coverage.xml --cov-report=html:algotrading_platform/test_reports/coverage_html --cov-append -o addopts=`
- If you have a strict coverage gate in `pytest.ini`, the runner disables it via `-o addopts=` to ensure matrix stability.
- If you need to add another subset, edit `scripts/run_matrix.py` and append to the `SUBSETS` list.
