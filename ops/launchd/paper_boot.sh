#!/bin/bash
# Boot the Intra paper-trading stack at login — 2026-07-23 ops work order Task 3.
#
# macOS restart policies in docker-compose (`restart: unless-stopped`) only bring
# a container back while the Docker *daemon* is running. They do NOT survive
# Docker Desktop quitting or a Mac reboot (the 06-27→07-06 and 07-08→07-23
# outages). This script closes that gap: at login it launches Docker Desktop,
# waits for the daemon, then brings the compose stack up (idempotent).
set -u

# Self-locate the repo (this file lives at <repo>/ops/launchd/paper_boot.sh).
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="docker-compose.paper.yml"
LOG="$REPO/logs/paper_boot.log"

# launchd starts us with a minimal PATH — add the usual Docker locations.
export PATH="/opt/homebrew/bin:/usr/local/bin:/Applications/Docker.app/Contents/Resources/bin:/usr/bin:/bin:/usr/sbin:/sbin"

mkdir -p "$REPO/logs"
log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) [paper_boot] $*" >>"$LOG"; }

log "start (repo=$REPO)"

# 1) Launch Docker Desktop (no-op if already running).
open -a Docker 2>>"$LOG" || log "open -a Docker returned non-zero (already running?)"

# 2) Wait up to ~5 min for the daemon to accept connections.
ready=0
for i in $(seq 1 60); do
    if docker info >/dev/null 2>&1; then
        ready=1
        log "docker daemon ready after $((i * 5))s"
        break
    fi
    sleep 5
done
if [ "$ready" -ne 1 ]; then
    log "ERROR: docker daemon not ready after 300s — aborting"
    exit 1
fi

# 3) Choose the compose CLI (plugin preferred, legacy fallback).
if docker compose version >/dev/null 2>&1; then
    DC="docker compose"
else
    DC="docker-compose"
fi

# 4) Bring the stack up (idempotent: no-op if already running).
cd "$REPO" || { log "ERROR: cd $REPO failed"; exit 1; }
if $DC -f "$COMPOSE_FILE" up -d >>"$LOG" 2>&1; then
    log "compose up -d OK ($DC)"
else
    log "ERROR: compose up -d failed ($DC)"
    exit 1
fi
log "done"
