#!/bin/bash
# `make paper-watchdog` — 2026-07-23 ops work order Task 3.
# One-shot: if the Docker daemon is up but intra-api-1 is NOT running, bring the
# stack up. Complements `restart: unless-stopped` (which cannot help while the
# daemon itself is down — that case is the login LaunchAgent's job).
# Optionally install as an hourly LaunchAgent (com.intra.paper.watchdog.plist).
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO" || exit 1
LOG="$REPO/logs/paper_watchdog.log"
export PATH="/opt/homebrew/bin:/usr/local/bin:/Applications/Docker.app/Contents/Resources/bin:/usr/bin:/bin"
mkdir -p "$REPO/logs"
log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) [watchdog] $*" >>"$LOG"; }

if ! docker info >/dev/null 2>&1; then
    # Daemon down — not our job (the login LaunchAgent starts Docker Desktop).
    log "docker daemon down — no action"
    exit 0
fi

if docker ps --format '{{.Names}}' | grep -q '^intra-api-1$'; then
    exit 0  # healthy, nothing to do
fi

log "intra-api-1 not running but docker daemon is up — bringing stack up"
if docker compose version >/dev/null 2>&1; then DC="docker compose"; else DC="docker-compose"; fi
if $DC -f docker-compose.paper.yml up -d >>"$LOG" 2>&1; then
    log "compose up -d OK"
else
    log "ERROR: compose up -d failed"
    exit 1
fi
