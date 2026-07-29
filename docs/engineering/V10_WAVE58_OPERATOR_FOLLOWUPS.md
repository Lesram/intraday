# V10 Wave-58 — Operator Follow-Ups

**Date:** 2026-05-03
**Status:** Documentation-only wave; closes V10 with operator-action items.

V10 cycle (waves 50-58) is code-complete. This doc captures the
operator-side actions that are not safe for an autonomous code agent
to execute.

## CRITICAL — Operator action required (deploy gate)

### AA4-1: rebuild paper container

**Why critical:** V10 AA4 found `intra-api-1` is running an OLD image
that lacks waves 32/42/47 (and now 50-57). All V9+V10 fix work is
sitting on disk, NOT live. Container `security.py` is 862 lines vs
host 924+.

**Action:**
```bash
cd /Users/marselkei/VS/intra
docker-compose -f docker-compose.paper.yml build api
docker-compose -f docker-compose.paper.yml up -d api
docker exec intra-api-1 wc -l /app/backend/infra/security.py
# Expected: matches host ./backend/infra/security.py count
```

**Verification (post-rebuild):**
```bash
# AA4-2 blacklist initialized:
docker exec intra-api-1 python -c "from backend.infra import security; print(security._token_blacklist_redis)"
# Expected: <Redis ...>, NOT None.

# AA4-3 settings GET admin:
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $USER_TOKEN" \
  http://localhost:8000/api/v1/settings/organism
# Expected: 403 (was 200 pre-wave-50)
```

## HIGH — Test-user cleanup

V8 AA2, V9 AA3, V10 AA4 created throwaway test users during external
probing. Delete them after deploy verification:

```sql
DELETE FROM users WHERE email IN (
  'audit_aa3_test@example.com',
  'audit_aa4@example.com',
  'audit_aa4_b@example.com'
);
```

Run via:
```bash
docker exec trading_platform_db_paper psql -U trading -d algotrading -c \
  "DELETE FROM users WHERE email LIKE 'audit_%@example.com'; SELECT count(*) FROM users WHERE email LIKE 'audit_%';"
# Expected: count = 0
```

## INFORMATIONAL — Monday post-open re-verify

V10 BB4-F1 deferred verification of wave-43 DD3-2 (LotTracker
incremental fill) until Monday post-open because no fills had landed
since deploy.

**Monday 2026-05-05 ~10:00 ET (after first fills):**

```sql
-- 1. position_lots populated?
docker exec trading_platform_db_paper psql -U trading -d algotrading -c \
  "SELECT count(*), MAX(opened_at) FROM position_lots;"
-- Expected: count > 0, opened_at within last hour

-- 2. No duplicates per order (DD3-2 incremental fix verification)?
docker exec trading_platform_db_paper psql -U trading -d algotrading -c \
  "SELECT order_id, count(*) FROM position_lots GROUP BY order_id HAVING count(*) > 1 LIMIT 10;"
-- Expected: 0 rows

-- 3. realized_trades populated on closes?
docker exec trading_platform_db_paper psql -U trading -d algotrading -c \
  "SELECT count(*), SUM(realized_pnl) FROM realized_trades;"
-- Expected: count > 0; sum approx matches brain cumulative_pnl

-- 4. ORDER_FILLED audit_logs entries (V10 YY-2 wave-52)?
docker exec trading_platform_db_paper psql -U trading -d algotrading -c \
  "SELECT count(*) FROM audit_logs WHERE action = 'order.filled';"
-- Expected: count > 0 (was 0 pre-wave-52)
```

If any of these fail, file a finding for V11.

## V10 cycle summary

**Total findings:** 32 actionable + 2 informational + 1 lint deliverable.

**Closures by wave:**

| Wave | Findings closed | Severity |
|---|---|---|
| 50 | AA4-2/3/4 (AA4-1 = operator action) | 1 Critical (deploy) + 1 High + 1 Medium + 1 Low |
| 51 | WW-1, PP2-1, UU2-A, UU2-C | 3 High + 1 Medium |
| 52 | YY-1, YY-2, YY-5 (3, 4 deferred to V11) | 2 High + 1 Medium |
| 53 | DD4-1, DD4-2, DD4-4 (DD4-3 deferred) | 2 High + 1 Low |
| 54 | VV-3 (VV-1/2/4/5 = frontend follow-up) | 1 High |
| 55 | XX-1, XX-2, BB4-F2 verify (XX-3 deferred) | 2 High |
| 56 | WW-2, WW-3, PP2-2, PP2-3, Z8-1 | 2 Medium + 3 Low |
| 57 | UU2-B lint rule + ratchet | 1 Deliverable |
| 58 | (this doc — operator action items) | — |

**Total V10 closures:** 22 of 32 findings + 1 deliverable.

**V10 deferred:**
- DD4-3 (inverse-ETF flip refactor) — V11 multi-site refactor
- XX-3 (ORM-vs-DB drift / portfolio_history) — V11 migration coordination
- VV-1/2/4/5 (frontend-side) — Frontend follow-up
- YY-3 (Prom labels) — V11 cleanup
- YY-4 (BackgroundTrainer alert) — V11
- BB4-F1 (Mon post-open verify) — operator action

## V11 forward-plan summary

Per V10 OO meta-recommendations:
- **Retain all 13 lenses.**
- **Add lens DD-DEPLOY** — every "fix verified" track first checks
  `docker exec ... wc -l /app/path` matches host SHA. Catches AA4-1-class.
- **Add lens DD-PROD-DATA** — differentiate "fix correct in code" from
  "fix exercised in production data." DD4-1 + DD4-2 would have been
  caught by an empirical-trade-data audit.
- **Yield expectation:** 5-15 findings if V10 fix waves close cleanly.

The cycle is healthy. Per-lens yield trends show DD/PP/UU declining
(converging) and NEW lenses (VV/WW/XX/YY) yielding 17 first-round.
The right metric is "always have ≥1 active fresh lens" — not "are
findings going down?"
