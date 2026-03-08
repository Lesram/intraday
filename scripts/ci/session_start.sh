#!/usr/bin/env bash
set -euo pipefail
mkdir -p artifacts
python3 scripts/ci/detect_changed_paths.py --mode session-start > artifacts/changed-paths.json || true
python3 scripts/runtime/write_runtime_snapshot.py || true
