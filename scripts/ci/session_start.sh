#!/usr/bin/env bash
set -euo pipefail
mkdir -p artifacts
python3 scripts/ci/detect_changed_paths.py --mode session-start > artifacts/changed-paths.json || true
