#!/usr/bin/env bash
set -euo pipefail

# Ensure logs directory exists
mkdir -p logs
log="logs/current.log"

# Start session header (overwrite for a fresh session)
printf "--- SESSION START %s ---\n" "$(date -Iseconds)" > "$log"

# Usage: bash scripts/capture.sh -- npm run dev
# Run provided command, timestamp each line, redact token-like strings, and tee to log
"${@}" 2>&1 \
  | while IFS= read -r line; do \
      printf "%s %s\n" "$(date '+%Y-%m-%d %H:%M:%S')" "$line" \
        | sed -E 's/sk-[A-Za-z0-9]{10,}/[REDACTED]/g'; \
    done \
  | tee -a "$log"
