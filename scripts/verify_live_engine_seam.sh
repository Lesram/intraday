#!/usr/bin/env bash
# Verify the 2026-06-08 live_engine fill-lookup seam extraction is
# behavior-preserving. Run from repo root on a branch.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
PY="${PY:-./venv/bin/python}"

echo "== 1. Syntax =="
$PY -m py_compile \
  backend/organism/live_engine.py \
  backend/organism/live_engine_fills.py \
  backend/organism/live_engine_state.py \
  backend/organism/live_engine_telemetry.py \
  backend/organism/live_engine_data.py && echo "  compile OK"

echo "== 2. getsource resolves through the mixins (method-level guards) =="
$PY -c "
import inspect
from backend.organism.live_engine import OrganismLiveEngine
for m in ('_lookup_entry_fill_from_db','_lookup_exit_fill_from_db',
          '_reconstruct_trades_from_db','_reconstruct_position_state',
          '_record_phase9_shadow_signals','_record_legacy_orb_shadow_signals',
          '_persist_telemetry_to_db','_fetch_and_compute_features','_fetch_bars'):
    src = inspect.getsource(getattr(OrganismLiveEngine, m))
    assert 'def '+m in src, m
print('  getsource via MRO OK for all extracted methods')
"

echo "== 3. Structural guards that source the whole module / class =="
$PY -m pytest -q \
  tests/test_march31_safe_fix.py \
  tests/test_wave62_fixes.py \
  tests/test_wave41_fixes.py \
  tests/test_audit_patch_queue_b2.py

echo "== 4. Behavioral + file-text guard tests for the moved methods =="
$PY -m pytest -q \
  tests/test_phase3_candidate_shadow_telemetry.py \
  tests/test_audit_patch_queue_b1.py \
  tests/test_wave34_fixes.py

echo "== 5. Data-feeder behavioral tests (monkeypatch _fetch_and_compute_features) =="
$PY -m pytest -q \
  tests/test_safety_invariants.py \
  tests/test_multi_tick_state.py \
  tests/test_organism_engine_scenarios.py

echo "== 6. Broad organism live-engine sweep =="
$PY -m pytest -q tests/ -k "live_engine or organism" || true
echo "ALL CHECKS ATTEMPTED — review output before committing."
