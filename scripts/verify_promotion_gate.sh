#!/usr/bin/env bash
# Verify the 2026-06-08 same-holdout promotion-gate hardening.
# Run from repo root on a branch.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
PY="${PY:-./venv/bin/python}"

echo "== 1. Syntax =="
$PY -m py_compile backend/organism/continuous_learner.py tests/test_rc_1_5_same_holdout_gate.py && echo "  compile OK"

echo "== 2. Same-holdout gate suite (existing + new regression tests) =="
$PY -m pytest -q tests/test_rc_1_5_same_holdout_gate.py

echo "== 3. All acceptance_gate / continuous_learner tests (no regressions) =="
$PY -m pytest -q \
  tests/test_audit_patch_queue_d1.py tests/test_audit_patch_queue_d2.py \
  tests/test_audit_patch_queue_f2.py tests/test_audit_patch_queue_h1.py \
  tests/test_audit_patch_queue_h2.py tests/test_audit_patch_queue_h3.py \
  tests/test_audit_patch_queue_i1.py tests/unit/test_organism.py

echo "== 4. Broad learner / retrain sweep =="
$PY -m pytest -q tests/ -k "continuous_learner or acceptance or retrain or holdout" || true
echo "ALL CHECKS ATTEMPTED — review output before committing."
