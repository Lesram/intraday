# Track BB4 v10 — Data Integrity Phase 3

V9 BB3 found that 14 of 17 substantive tables were dark. Wave-43 DD3-2 fixed LotTracker partial-fill duplicates (suspected root cause for some). **BB4 verifies the wave-43 fix actually populates `position_lots` under live trades** + drills into remaining dark-table follow-throughs.

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `35a1fe9`. Postgres `trading_platform_db_paper` (DB `algotrading`).

## Method

### 1. position_lots reach verification (THE V9 mystery)

```
docker exec trading_platform_db_paper psql -U trading -d algotrading -c \
  "SELECT count(*) FROM position_lots;"
docker exec trading_platform_db_paper psql -U trading -d algotrading -c \
  "SELECT symbol, side, qty, price, opened_at FROM position_lots
   ORDER BY opened_at DESC LIMIT 10;"
```

Expected (post-wave-43 deploy): row count > 0. If still 0 AND trading happened today, wave-43 fix wasn't deployed OR a deeper bug remains.

### 2. realized_trades reach

```
docker exec trading_platform_db_paper psql -U trading -d algotrading -c \
  "SELECT count(*), SUM(realized_pnl) FROM realized_trades;"
```

Expected: row count > 0; sum approx matches brain `cumulative_pnl`.

### 3. Duplicate detection (the BB3 / DD3-2 worry)

```
docker exec trading_platform_db_paper psql -U trading -d algotrading -c \
  "SELECT order_id, count(*) FROM position_lots GROUP BY order_id HAVING count(*) > 1;"
```

Expected: 0 rows (each broker fill produces exactly 1 lot per partial event, with incremental qty).

### 4. Cross-check vs brain

```
cat organism_brain/manifest.json | jq '{total_trades, cumulative_pnl}'
```

Then:
- `count(realized_trades) ≈ total_trades` (closed positions)
- `sum(realized_pnl) ≈ cumulative_pnl`

### 5. Other dark tables (BB3-F2 follow-up)

For each of: `executions`, `order_events`, `risk_violations`, `daily_ledger`, `tick_telemetry`:
- Row count.
- Most recent timestamp.
- Identify which are "intended live but waiting for trigger" vs "drop schema".

### 6. Hash chain integrity (re-verify)

```
docker exec trading_platform_db_paper psql -U trading -d algotrading -c \
  "SELECT count(*), MAX(ts) FROM audit_logs;"
```

Run the same hash-chain verification as BB3 (use service.audit_service.verify_chain or equivalent). Expected: 0 broken.

### 7. FK integrity (post-wave-44 DD3-4 EOD-cancel changes)

The wave-44 EOD-flatten now cancels pending entries. Verify:
- `orders` table has rows with status='cancelled' from EOD path.
- No orphan `executions` referencing cancelled orders.

### 8. Schema drift since wave-37

```
./venv/bin/python scripts/ci/check_migrations.py
```

Then compare current production schema to HEAD migration's expected state via `alembic current`.

### 9. NULL-leak scan (post-wave-43)

```
docker exec trading_platform_db_paper psql -U trading -d algotrading -c "
  SELECT 'position_lots.qty' AS col, count(*) FILTER (WHERE qty IS NULL) AS nulls
  FROM position_lots
  UNION ALL SELECT
  'position_lots.cost_basis', count(*) FILTER (WHERE cost_basis IS NULL)
  FROM position_lots
  UNION ALL SELECT
  'realized_trades.realized_pnl', count(*) FILTER (WHERE realized_pnl IS NULL)
  FROM realized_trades;"
```

Expected: 0.

### 10. brain backup directory check (PP-1 + PP-2 wave-41 follow-up)

```
docker exec intra-api-1 ls -la /app/organism_brain/backups/ 2>&1 | head -10
```

Expected: directory exists; at least 1 backup since wave-41 deploy.

## Output

`artifacts/audit/v10_reports/track_bb4_data_integrity_phase3.md` with table-by-table reach status, duplicate count, brain↔DB consistency, FK integrity, schema drift, NULL leak, backup status.

Quality bar: 1-3 findings.
