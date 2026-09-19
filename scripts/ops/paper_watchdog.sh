#!/bin/bash
# Bounded known-container recovery; no compose recreation or parameter changes.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO" || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:/Applications/Docker.app/Contents/Resources/bin:/usr/bin:/bin"
exec "$REPO/venv/bin/python" -B "$REPO/scripts/ops/paper_watchdog.py" --recover "$@"
