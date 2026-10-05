# V10 Day-1 Post-Deploy Verification Report
**Date:** 2026-05-04  
**Wave Cycle:** V10 (waves 50-59)  
**Deployment Target:** rc-1.5-curated  
**Operator:** paste local results into each `Result:` line below

---

## 1. Branch & Commit

| Field | Value |
|---|---|
| Target branch | `rc-1.5-curated` |
| **Fallback note** | `rc-1.5-curated` was **not found** on origin; verification ran on **`main`** |
| HEAD SHA | `32a3474736bf7f5b3fa2a4308d626b7c3fe75755` |
| Commit message | `Merge pull request #3 from Lesram/control-plane-operationalize` |

---

## 2. V10 Test Suite Results (CI-side run)

**Command executed:**
```
./venv/bin/python -m pytest \
  tests/test_wave50_fixes.py tests/test_wave51_fixes.py \
  tests/test_wave52_fixes.py tests/test_wave53_fixes.py \
  tests/test_wave54_fixes.py tests/test_wave55_fixes.py \
  tests/test_wave56_fixes.py tests/test_wave57_fixes.py \
  tests/test_reachability_v8.py tests/test_organism_live_engine.py \
  -q --timeout=30
```

**Files present / absent:**

| Test file | Present? |
|---|---|
| tests/test_wave50_fixes.py | ❌ ABSENT |
| tests/test_wave51_fixes.py | ❌ ABSENT |
| tests/test_wave52_fixes.py | ❌ ABSENT |
| tests/test_wave53_fixes.py | ❌ ABSENT |
| tests/test_wave54_fixes.py | ❌ ABSENT |
| tests/test_wave55_fixes.py | ❌ ABSENT |
| tests/test_wave56_fixes.py | ❌ ABSENT |
| tests/test_wave57_fixes.py | ❌ ABSENT |
| tests/test_reachability_v8.py | ❌ ABSENT |
| tests/test_organism_live_engine.py | ✅ present |

**Pytest output (tests/test_organism_live_engine.py only):**

```
tests/test_wave50_fixes.py  — NOT FOUND (skipped)
tests/test_wave51_fixes.py  — NOT FOUND (skipped)
tests/test_wave52_fixes.py  — NOT FOUND (skipped)
tests/test_wave53_fixes.py  — NOT FOUND (skipped)
tests/test_wave54_fixes.py  — NOT FOUND (skipped)
tests/test_wave55_fixes.py  — NOT FOUND (skipped)
tests/test_wave56_fixes.py  — NOT FOUND (skipped)
tests/test_wave57_fixes.py  — NOT FOUND (skipped)
tests/test_reachability_v8.py — NOT FOUND (skipped)

tests/test_organism_live_engine.py::  26 PASSED  (89.44s)

..........................
=============================== warnings summary ===============================
tests/test_organism_live_engine.py::TestOrganismScheduler::test_start_stop
  DeprecationWarning: 'crypt' is deprecated and slated for removal in Python 3.13
26 passed, 1 warning in 89.44s (0:01:29)
```

**Pass / Fail count:**

```
26 passed, 0 failed  (9 wave-specific files absent from main HEAD 32a3474)
```

> **Note:** Wave-specific test files (test_wave50_fixes.py … test_wave57_fixes.py) and
> test_reachability_v8.py were not committed to `main` at HEAD 32a3474. Either they live
> on the unmerged `rc-1.5-curated` branch, or they are yet to be added. The operator
> should re-run the full suite once those files are present, or after checking out the
> correct branch.

---

## 3. Live Environment Checks

Run `artifacts/audit/v10_day1_verify.sh` from the project root. Paste each section's
output into the corresponding `Result:` field below.

---

### a) Container vs Source-SHA Drift

**Command:**
```bash
docker exec intra-api-1 wc -l \
  /app/backend/infra/security.py \
  /app/backend/api/lifespan.py \
  /app/backend/organism/brain_persistence.py | tail -5
wc -l \
  backend/infra/security.py \
  backend/api/lifespan.py \
  backend/organism/brain_persistence.py | tail -5
```
**Expected:** container totals **equal** host totals (image matches deployed source)

Result:
```

```

---

### b) AA4-2 Token Blacklist Initialized

**Command:**
```bash
docker logs intra-api-1 --since 24h 2>&1 | grep -E 'Token blacklist initialized|AA4-2'
```
**Expected:** ≥ 1 match

Result:
```

```

---

### c) AA4-3 Settings GET (unauthenticated) → 401

**Command:**
```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8000/api/v1/settings/organism
```
**Expected:** `401`

Result:
```

```

---

### d) AA4-4 X-API-Key bogus key → 401 (not 500)

**Command:**
```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  -H 'X-API-Key: anything' http://localhost:8000/api/v1/settings/organism
```
**Expected:** `401` (was `500` pre-wave-50/59)

Result:
```

```

---

### e) BB4-F1 / DD3-2 position_lots Populated

**Command:**
```bash
docker exec trading_platform_db_paper psql -U trading -d algotrading -c \
  "SELECT count(*) AS lots, MAX(opened_at) AS last_open FROM position_lots;"
```
**Expected:** `count > 0` if any fills landed today

Result:
```

```

---

### f) DD3-2 No Duplicate position_lots per Order

**Command:**
```bash
docker exec trading_platform_db_paper psql -U trading -d algotrading -c \
  "SELECT order_id, count(*) FROM position_lots GROUP BY order_id HAVING count(*) > 1 LIMIT 10;"
```
**Expected:** `0 rows`

Result:
```

```

---

### g) realized_trades Populated on Closes

**Command:**
```bash
docker exec trading_platform_db_paper psql -U trading -d algotrading -c \
  "SELECT count(*) AS trades, ROUND(SUM(realized_pnl)::numeric, 2) AS pnl FROM realized_trades;"
```
**Expected:** `count > 0`

Result:
```

```

---

### h) YY-2 ORDER_FILLED audit_logs Entries

**Command:**
```bash
docker exec trading_platform_db_paper psql -U trading -d algotrading -c \
  "SELECT count(*) FROM audit_logs WHERE action='order.filled';"
```
**Expected:** `count > 0` once fills happen (was `0` pre-wave-52)

Result:
```

```

---

### i) WW-1 Backups Directory Populated

**Command:**
```bash
docker exec intra-api-1 ls -1 /app/organism_brain/backups/ 2>/dev/null | wc -l
```
**Expected:** `≥ 1` (essential save mints hourly post-wave-51)

Result:
```

```

---

### j) Brain Coherence Post-Rebuild

**Command:**
```bash
cat organism_brain/manifest.json | jq '{generation, total_trades, total_runs, ml_is_trained, best_sharpe}'
```
**Expected:** `generation >= 168`, `total_trades >= 498`, `ml_is_trained = true`

Result:
```

```

---

## 4. Verdict

- [ ] **All green** — all checks (a)-(j) passed
- [ ] **Issues found** — one or more checks failed (details below)

Issues (if any):
```

```

---

## 5. Next Steps

### If all green
1. Confirm wave test files exist on `rc-1.5-curated` and run the full pytest suite there.
2. Perform a final code review of `rc-1.5-curated` → `main` diff.
3. Merge `rc-1.5-curated` → `main` via PR (squash or merge commit per team convention).
4. Tag the release: `git tag v10.0.0-prod 2026-05-04`.
5. Monitor first full trading day logs for regressions.

### If issues found
1. Open a **V11 findings** issue on `lesram/intraday` documenting each failing check.
2. Do **not** merge `rc-1.5-curated` until all blocking checks pass.
3. For DB-state issues (e, f, g, h): inspect `position_lots` and `realized_trades` schemas
   for missing triggers or incomplete DD3-2 migration.
4. For brain coherence (j): re-run `organism rebuild` and verify manifest increments.
5. For container drift (a): rebuild and redeploy the Docker image from `rc-1.5-curated` HEAD.
6. Assign V11 wave ticket numbers to each distinct failure category.

---

*Generated by V10 Day-1 Post-Deploy Verification Agent on 2026-05-04.*  
*Artifacts: `artifacts/audit/v10_day1_verify.sh`, `artifacts/audit/V10_DAY1_VERIFY_REPORT.md`*
