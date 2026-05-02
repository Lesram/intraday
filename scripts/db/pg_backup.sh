#!/usr/bin/env bash
# V4 N-H-3 (2026-05-02): PostgreSQL backup for paper-trading DB.
#
# Audit Track N found: only the brain JSON is backed up. The Postgres
# DB carrying orders, fills, position_lots, realized_trades, outbox,
# and idempotency keys had NO automated backup. This script does a
# pg_dump to ./backups/postgres/ with a timestamp; rotation keeps the
# 14 most recent.
#
# Recommended cron (host crontab, NOT in container):
#   30 22 * * * cd /Users/marselkei/VS/intra && bash scripts/db/pg_backup.sh >> backups/postgres/cron.log 2>&1
#
# Usage:
#   bash scripts/db/pg_backup.sh           # run once
#   PG_BACKUP_KEEP=30 bash scripts/db/pg_backup.sh   # change retention
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BACKUP_DIR="${REPO_ROOT}/backups/postgres"
KEEP="${PG_BACKUP_KEEP:-14}"
DB_CONTAINER="${PG_BACKUP_CONTAINER:-trading_platform_db_paper}"
DB_NAME="${PG_BACKUP_DB:-algotrading}"
DB_USER="${PG_BACKUP_USER:-trading}"

mkdir -p "${BACKUP_DIR}"

TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="${BACKUP_DIR}/pg-${DB_NAME}-${TS}.sql.gz"

echo "[$(date -u +%FT%TZ)] starting pg_dump → ${OUT}"

if ! docker ps --format '{{.Names}}' | grep -qx "${DB_CONTAINER}"; then
    echo "ERROR: db container ${DB_CONTAINER} not running" >&2
    exit 1
fi

docker exec "${DB_CONTAINER}" pg_dump \
    -U "${DB_USER}" -d "${DB_NAME}" --no-owner --no-acl \
    | gzip -9 > "${OUT}"

# Retention
ls -1t "${BACKUP_DIR}"/pg-*.sql.gz 2>/dev/null | tail -n +$((KEEP+1)) | xargs -r rm -f

SIZE="$(du -h "${OUT}" | cut -f1)"
COUNT="$(ls -1 "${BACKUP_DIR}"/pg-*.sql.gz 2>/dev/null | wc -l | tr -d ' ')"
echo "[$(date -u +%FT%TZ)] pg_dump complete: ${SIZE} (${COUNT} backups retained)"
