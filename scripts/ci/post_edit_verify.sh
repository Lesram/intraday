#!/usr/bin/env bash
set -euo pipefail
mkdir -p artifacts
python3 scripts/ci/detect_changed_paths.py --mode post-edit > artifacts/changed-paths.json || true
# Lightweight syntax check only; full tests happen in CI or explicit agent run.
python3 -m py_compile backend/organism/*.py 2>/dev/null || true
