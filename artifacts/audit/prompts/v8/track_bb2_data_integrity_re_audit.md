# Track BB2 v8 — Data Integrity Re-Audit (with Reachability Lens)

V7 BB found 10 issues; wave-30 wired BB-8 (LotTracker → position_lots) and BB-10 (audit_logs from drawdown-kill + login). **BB2 verifies under live load that rows actually land**, not just that the code path exists.

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `79b38fb`. Container `intra-api-1` running on `:8000`. Postgres on `intra-postgres-1` (DB `algotrading`, user `trading`).

## Method

### 1. BB-8 verification: position_lots populates under live trades

The wave-30 wiring added `LotTracker.create_lot()` inside `_process_trade_update`. Verify:

```
# Snapshot position_lots count.
docker exec intra-postgres-1 psql -U trading -d algotrading -t -c \
  "SELECT count(*) FROM position_lots;"

# Inspect last 10 rows + dates to confirm fresh writes (not stale).
docker exec intra-postgres-1 psql -U trading -d algotrading -c \
  "SELECT symbol, side, qty, price, opened_at FROM position_lots
   ORDER BY opened_at DESC LIMIT 10;"

# Cross-check with brain trade count.
cat organism_brain/manifest.json | jq '.total_trades'
```

Expected: position_lots row count > 0 and recent rows from today (or last trading day). If row count = 0 OR all rows pre-date wave-30 deploy → BB-8 wired but not reached.

### 2. BB-8 verification: realized_trades populates on closes

```
docker exec intra-postgres-1 psql -U trading -d algotrading -c \
  "SELECT count(*) FROM realized_trades;"
docker exec intra-postgres-1 psql -U trading -d algotrading -c \
  "SELECT symbol, qty, realized_pnl, closed_at FROM realized_trades
   ORDER BY closed_at DESC LIMIT 10;"
```

If position_lots has rows but realized_trades is empty → close_lots_fifo not invoked on sell-side fills. The wave-30 wiring may have only covered buys.

### 3. BB-10 verification: audit_logs populates from drawdown-kill

The wave-30 wiring added `fire_audit_log_threadsafe()` at the drawdown-kill site in live_engine.py. Verify (no need to wait for a real drawdown — search by action type):

```
docker exec intra-postgres-1 psql -U trading -d algotrading -c \
  "SELECT count(*), MAX(created_at) FROM audit_logs;"
docker exec intra-postgres-1 psql -U trading -d algotrading -c \
  "SELECT action, count(*), MAX(created_at) FROM audit_logs
   GROUP BY action ORDER BY count(*) DESC LIMIT 20;"
```

Expected: USER_LOGIN / USER_LOGIN_FAILED rows present (wave-30 confirmed). If DRAWDOWN_KILL / DAILY_MAX_LOSS_HALT actions are absent → either no kill has fired since deploy (acceptable) OR the wiring didn't take effect (suspicious).

### 4. Hash-chain integrity

ComplianceAuditService writes a hash-chain. Verify:

```
docker exec intra-postgres-1 psql -U trading -d algotrading -c "
  WITH chain AS (
    SELECT id, prev_hash, current_hash,
           LAG(current_hash) OVER (ORDER BY id) AS expected_prev
    FROM audit_logs
  )
  SELECT count(*) AS broken FROM chain
  WHERE expected_prev IS NOT NULL AND prev_hash != expected_prev;"
```

Expected: 0. Any non-zero is a Critical integrity finding.

### 5. trade_history.csv vs DB consistency

```
# Tail trade_history.csv and cross-reference recent symbols to broker_orders.
tail -20 organism_brain/trade_history.csv
docker exec intra-postgres-1 psql -U trading -d algotrading -c \
  "SELECT symbol, side, qty, status, submitted_at FROM broker_orders
   ORDER BY submitted_at DESC LIMIT 20;"
```

Mismatch (CSV has trades not in DB or vice versa) = data drift finding.

### 6. Brain backup integrity

V7 noted brain-backup IS working but verify backup file rotation:

```
ls -lh organism_brain/backups/ | tail -10
# Check most recent backup is < 24h old + sizes look sensible.
```

Stale or zero-byte backup = High finding.

### 7. CHECK constraints + NULLs

V7 BB-1 added CHECK constraints. Verify enforcement:

```
docker exec intra-postgres-1 psql -U trading -d algotrading -c "
  SELECT conname, conrelid::regclass, pg_get_constraintdef(oid)
  FROM pg_constraint
  WHERE contype = 'c' AND connamespace = 'public'::regnamespace
  ORDER BY conrelid::regclass::text, conname;"
```

Compare against V7 BB-1 closure list. Missing constraint = closure regressed.

### 8. NULL-leak scan on critical columns

```
docker exec intra-postgres-1 psql -U trading -d algotrading -c \
  "SELECT
     'broker_orders.qty' AS col, count(*) FILTER (WHERE qty IS NULL) AS nulls FROM broker_orders
   UNION ALL SELECT
     'audit_logs.action', count(*) FILTER (WHERE action IS NULL) FROM audit_logs
   UNION ALL SELECT
     'position_lots.symbol', count(*) FILTER (WHERE symbol IS NULL) FROM position_lots;"
```

Any non-zero on a NOT-NULL-expected column → schema drift finding.

## Output

`artifacts/audit/v8_reports/track_bb2_data_integrity_re_audit.md` with:
- Live-load row counts (position_lots, realized_trades, audit_logs)
- BB-8 reach status (rows landed?)
- BB-10 reach status (rows landed?)
- Hash-chain integrity result
- CSV/DB consistency
- Backup freshness
- CHECK constraint coverage delta vs V7
- NULL-leak scan
- "Reachability gaps confirmed: N. New data integrity issues: N." + TL;DR

Quality bar: 2-4 findings. The track confirms wave-30 wiring is REACHED (not just WIRED). End with one-paragraph summary.
