#!/usr/bin/env bash
set -euo pipefail
# Prevent accidental edits to secrets or production env files without explicit intent.
if git diff --name-only --cached -- .env .env.* 2>/dev/null | grep -q .; then
  echo "Refusing to continue: staged secret/env changes detected. Use a dedicated secrets task." >&2
  exit 2
fi
exit 0
