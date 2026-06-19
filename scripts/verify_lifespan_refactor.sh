#!/usr/bin/env bash
# Verify the 2026-06-08 lifespan decomposition is behavior-preserving.
# Run from repo root on a branch:  bash scripts/verify_lifespan_refactor.sh
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
PY="${PY:-./venv/bin/python}"

echo "== 1. Syntax =="
$PY -m py_compile backend/api/lifespan.py && echo "  compile OK"

echo "== 2. Structural regression guards (must pass unchanged) =="
$PY -m pytest -q \
  tests/test_reachability_v8.py \
  tests/test_wave41_fixes.py \
  tests/test_wave50_fixes.py \
  tests/test_wave51_fixes.py

echo "== 3. Behavioral lifespan + boot tests =="
$PY -m pytest -q \
  tests/test_accounting_pipeline.py \
  -k "sync_orders or lifespan or startup or shutdown" || true
# Broader sweep — any test that imports the lifespan module:
$PY -m pytest -q tests/ -k "lifespan or startup or shutdown or boot" || true

echo "== 4. App still constructs (import + factory) =="
ALLOW_NO_DB=1 PYTEST_CURRENT_TEST=1 $PY -c "
from backend.api.factory import create_app
app = create_app()
import backend.api.lifespan as L
assert callable(L.startup) and callable(L.shutdown) and callable(L._sync_orders)
steps=[n for n in dir(L) if n.startswith('_step_')]
shuts=[n for n in dir(L) if n.startswith('_shut_')]
print(f'  app OK; {len(steps)} startup steps, {len(shuts)} shutdown steps')
"
echo "ALL CHECKS ATTEMPTED — review output above before committing."
