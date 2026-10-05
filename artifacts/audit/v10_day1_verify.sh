#!/usr/bin/env bash
# V10 Day-1 Post-Deploy Verification Script
# Branch: main (rc-1.5-curated not found; fell back to main)
# HEAD: 32a3474736bf7f5b3fa2a4308d626b7c3fe75755
# Generated: 2026-05-04  ~60 min after market open
# Usage: bash v10_day1_verify.sh   (read-only, no mutations)

set -euo pipefail

PASS=0
FAIL=0
ERRORS=()

ok()   { echo "[PASS] $1"; PASS=$((PASS+1)); }
fail() { echo "[FAIL] $1"; FAIL=$((FAIL+1)); ERRORS+=("$1"); }

section() { echo ""; echo "════════════════════════════════════════════"; echo "  $1"; echo "════════════════════════════════════════════"; }

# ─────────────────────────────────────────────────────────────────────────────
section "a) Container vs Source-SHA Drift Check"
echo "Container line counts:"
docker exec intra-api-1 wc -l \
  /app/backend/infra/security.py \
  /app/backend/api/lifespan.py \
  /app/backend/organism/brain_persistence.py 2>/dev/null | tail -5

echo "Host line counts:"
wc -l \
  backend/infra/security.py \
  backend/api/lifespan.py \
  backend/organism/brain_persistence.py 2>/dev/null | tail -5

# Compare totals
CONTAINER_TOTAL=$(docker exec intra-api-1 wc -l \
  /app/backend/infra/security.py \
  /app/backend/api/lifespan.py \
  /app/backend/organism/brain_persistence.py 2>/dev/null | awk '/total/{print $1}')
HOST_TOTAL=$(wc -l \
  backend/infra/security.py \
  backend/api/lifespan.py \
  backend/organism/brain_persistence.py 2>/dev/null | awk '/total/{print $1}')

if [[ "$CONTAINER_TOTAL" == "$HOST_TOTAL" ]]; then
  ok "a) SHA drift: container($CONTAINER_TOTAL) == host($HOST_TOTAL)"
else
  fail "a) SHA drift: container($CONTAINER_TOTAL) != host($HOST_TOTAL) — image may be stale"
fi

# ─────────────────────────────────────────────────────────────────────────────
section "b) AA4-2 Token Blacklist Initialized"
BLACKLIST_HIT=$(docker logs intra-api-1 --since 24h 2>&1 | grep -cE 'Token blacklist initialized|AA4-2' || true)
echo "Matches: $BLACKLIST_HIT"
if [[ "$BLACKLIST_HIT" -ge 1 ]]; then
  ok "b) AA4-2 blacklist init logged ($BLACKLIST_HIT match(es))"
else
  fail "b) AA4-2 blacklist init NOT found in last 24h of logs"
fi

# ─────────────────────────────────────────────────────────────────────────────
section "c) AA4-3 Settings GET admin — expect 401"
HTTP_C=$(curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8000/api/v1/settings/organism)
echo "HTTP status: $HTTP_C"
if [[ "$HTTP_C" == "401" ]]; then
  ok "c) AA4-3 unauthenticated GET /settings/organism → 401"
else
  fail "c) AA4-3 expected 401, got $HTTP_C"
fi

# ─────────────────────────────────────────────────────────────────────────────
section "d) AA4-4 X-API-Key not 500 — expect 401"
HTTP_D=$(curl -s -o /dev/null -w '%{http_code}\n' -H 'X-API-Key: anything' http://localhost:8000/api/v1/settings/organism)
echo "HTTP status: $HTTP_D"
if [[ "$HTTP_D" == "401" ]]; then
  ok "d) AA4-4 X-API-Key bogus key → 401 (not 500)"
else
  fail "d) AA4-4 expected 401, got $HTTP_D (was 500 pre-wave-50/59)"
fi

# ─────────────────────────────────────────────────────────────────────────────
section "e) BB4-F1 / DD3-2 position_lots Populated Post-Fill"
PL_OUT=$(docker exec trading_platform_db_paper psql -U trading -d algotrading -t -c \
  "SELECT count(*) AS lots, MAX(opened_at) AS last_open FROM position_lots;" 2>&1)
echo "$PL_OUT"
PL_COUNT=$(echo "$PL_OUT" | grep -Eo '^[[:space:]]*[0-9]+' | head -1 | tr -d ' ' || echo "0")
if [[ "$PL_COUNT" -gt 0 ]]; then
  ok "e) position_lots has $PL_COUNT row(s) — fills landed"
else
  fail "e) position_lots count=0 — no fills recorded yet (check if fills landed today)"
fi

# ─────────────────────────────────────────────────────────────────────────────
section "f) DD3-2 No Duplicate position_lots per Order"
DUP_OUT=$(docker exec trading_platform_db_paper psql -U trading -d algotrading -t -c \
  "SELECT order_id, count(*) FROM position_lots GROUP BY order_id HAVING count(*) > 1 LIMIT 10;" 2>&1)
echo "$DUP_OUT"
DUP_COUNT=$(echo "$DUP_OUT" | grep -c '[0-9]' || echo "0")
if [[ "$DUP_COUNT" -eq 0 ]]; then
  ok "f) DD3-2 no duplicate position_lots per order"
else
  fail "f) DD3-2 found $DUP_COUNT duplicate order_id(s) in position_lots"
fi

# ─────────────────────────────────────────────────────────────────────────────
section "g) realized_trades Populated on Closes"
RT_OUT=$(docker exec trading_platform_db_paper psql -U trading -d algotrading -t -c \
  "SELECT count(*) AS trades, ROUND(SUM(realized_pnl)::numeric, 2) AS pnl FROM realized_trades;" 2>&1)
echo "$RT_OUT"
RT_COUNT=$(echo "$RT_OUT" | grep -Eo '^[[:space:]]*[0-9]+' | head -1 | tr -d ' ' || echo "0")
if [[ "$RT_COUNT" -gt 0 ]]; then
  ok "g) realized_trades has $RT_COUNT row(s)"
else
  fail "g) realized_trades count=0 — no closed positions recorded"
fi

# ─────────────────────────────────────────────────────────────────────────────
section "h) YY-2 ORDER_FILLED audit_logs Entries"
AL_OUT=$(docker exec trading_platform_db_paper psql -U trading -d algotrading -t -c \
  "SELECT count(*) FROM audit_logs WHERE action='order.filled';" 2>&1)
echo "$AL_OUT"
AL_COUNT=$(echo "$AL_OUT" | grep -Eo '^[[:space:]]*[0-9]+' | head -1 | tr -d ' ' || echo "0")
if [[ "$AL_COUNT" -gt 0 ]]; then
  ok "h) YY-2 audit_logs has $AL_COUNT order.filled entries"
else
  fail "h) YY-2 audit_logs order.filled count=0 (was zero pre-wave-52)"
fi

# ─────────────────────────────────────────────────────────────────────────────
section "i) WW-1 Backups Directory Populated"
BACKUP_COUNT=$(docker exec intra-api-1 ls -1 /app/organism_brain/backups/ 2>/dev/null | wc -l || echo "0")
echo "Backup file count: $BACKUP_COUNT"
if [[ "$BACKUP_COUNT" -ge 1 ]]; then
  ok "i) WW-1 backups/ has $BACKUP_COUNT file(s)"
else
  fail "i) WW-1 backups/ is empty (essential save mints hourly post-wave-51)"
fi

# ─────────────────────────────────────────────────────────────────────────────
section "j) Brain Coherence Post-Rebuild"
MANIFEST_OUT=$(cat organism_brain/manifest.json | jq '{generation, total_trades, total_runs, ml_is_trained, best_sharpe}' 2>&1)
echo "$MANIFEST_OUT"

GENERATION=$(echo "$MANIFEST_OUT"   | jq '.generation'   2>/dev/null || echo "0")
TOTAL_TRADES=$(echo "$MANIFEST_OUT" | jq '.total_trades' 2>/dev/null || echo "0")
ML_TRAINED=$(echo "$MANIFEST_OUT"   | jq '.ml_is_trained' 2>/dev/null || echo "false")

BRAIN_OK=1
[[ "$GENERATION"   -ge 168   ]] || { BRAIN_OK=0; echo "  ! generation=$GENERATION < 168"; }
[[ "$TOTAL_TRADES" -ge 498   ]] || { BRAIN_OK=0; echo "  ! total_trades=$TOTAL_TRADES < 498"; }
[[ "$ML_TRAINED"   == "true" ]] || { BRAIN_OK=0; echo "  ! ml_is_trained=$ML_TRAINED (expected true)"; }

if [[ "$BRAIN_OK" -eq 1 ]]; then
  ok "j) brain coherent: gen=$GENERATION trades=$TOTAL_TRADES ml=$ML_TRAINED"
else
  fail "j) brain coherence check failed (see above)"
fi

# ─────────────────────────────────────────────────────────────────────────────
section "SUMMARY"
echo ""
echo "  PASSED : $PASS / $((PASS+FAIL))"
echo "  FAILED : $FAIL / $((PASS+FAIL))"

if [[ "${#ERRORS[@]}" -gt 0 ]]; then
  echo ""
  echo "  Failing checks:"
  for e in "${ERRORS[@]}"; do echo "    - $e"; done
fi

echo ""
if [[ "$FAIL" -eq 0 ]]; then
  echo "  VERDICT: ALL GREEN ✓ — rc-1.5-curated → main merge is safe."
  exit 0
else
  echo "  VERDICT: ISSUES FOUND — review failures above before merging."
  exit 1
fi
