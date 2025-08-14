#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   bash scripts/autocommit.sh "chore: auto-commit" main
#   bash scripts/autocommit.sh               # uses default message, pushes to current upstream

MSG=${1:-"chore: auto-commit"}
BRANCH=${2:-""}

# Stage all changes (tracked + untracked; excludes ignored files)
git add -A

# If nothing staged, exit quietly
if git diff --cached --quiet; then
  echo "No changes to commit."
  exit 0
fi

# Commit
git commit -m "$MSG"

# Optionally rebase and push to the specified branch; otherwise push to default upstream
if [[ -n "$BRANCH" ]]; then
  git pull --rebase origin "$BRANCH" || true
  git push origin HEAD:"$BRANCH"
else
  git push
fi
