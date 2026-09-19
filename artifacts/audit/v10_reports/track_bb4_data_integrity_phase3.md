# Track BB4 v10 — Data Integrity Phase 3

Repo: `/Users/marselkei/VS/intra`. Branch: `rc-1.5-curated` @ `c048103`.
DB container: `trading_platform_db_paper` (DB `algotrading`, user `trading`).
API container: `intra-api-1` (built `2026-05-03 06:10`).
Brain manifest saved at `2026-05-03T06:11:45Z` — total_trades 498, cumulative_pnl -634.92.
Today (per env metadata) is 2026-05-02; last trading day was Fri 2026-05-01.

Read-only audit (SELECT only, no mutations). Quality bar: 1-3 findings.

---

## 1. Reach snapshot

| Table             | Rows  | Most-recent ts                         |
|-------------------|-------|----------------------------------------|
| `orders`          | 1369  | 2026-05-01 19:42:07Z (filled)          |
| `audit_logs`      | 219   | 2026-05-03 16:57:27Z (login events)    |
| `position_lots`   | **0** | —                                      |
| `realized_trades` | **0** | —                                      |
| `executions`      | **0** | —                                      |
| `order_events`    | **0** | —                                      |
| `risk_violations` | **0** | —                                      |
| `daily_ledger`    | **0** | —                                      |
| `tick_telemetry`  | **0** | —                                      |

Order status mix: `filled=1359`, `cancelled=5`, `accepted=4`, `expired=1`. Of the 1359 fills, 700 buy / 659 sell. **Zero filled orders since `2026-05-01 19:42Z`.**

## 2. position_lots / realized_trades — wave-30 BB-8 wiring is present, not yet exercised

`docker exec ... ls -l /app/backend/integrations/alpaca_stream.py` → mtime `2026-05-03 06:02:35Z`. The wave-30 BB-8 patch (visible at `alpaca_stream.py:545-610`) IS in the running container — `LotTracker.create_lot` / `close_lots_fifo` are invoked from the live stream's order-update handler whenever a fill arrives with `internal_status in ("filled","partially_filled")` and a numeric `filled_qty` + `avg_fill_price`.

`alpaca_stream_production.py` (the legacy carrier of the same logic) is NOT loaded by the lifespan; only the wave-30-patched `alpaca_stream` is started (`backend/api/lifespan.py:304-309`). LotTracker logic itself (`backend/services/lot_tracker_service.py:33-209`) is sound: row-locked FIFO via `SELECT … FOR UPDATE`, atomic `flush()`, and balanced `qty/remaining_qty` updates.

But: `SELECT count(*) FROM orders WHERE status='filled' AND created_at >= '2026-05-03 06:06:17';` returns **0** — meaning no fill has reached the patched stream handler since the container was rebuilt. The persistent emptiness of `position_lots` / `realized_trades` is therefore **expected**, not a bug — it will only be falsified after the next live fill (Mon 2026-05-04 open).

Duplicate check on `position_lots` (`GROUP BY order_id HAVING count(*)>1`): 0 rows — vacuously true while empty, but the wave-43 DD3-2 partial-fill duplicate guard cannot be confirmed empirically without live fills.

NULL-leak scan (`qty`, `cost_basis`, `realized_pnl`): all 0 (vacuously, again).

## 3. Other dark tables

`executions`, `order_events`, `risk_violations`, `daily_ledger`, `tick_telemetry` — still 0 rows. None are populated by the wave-43 / wave-30 patches; they are separate writers (BB3-F2 follow-ups). No new evidence here vs V9 BB3 — these remain "intended live but waiting for trigger" or unwired writer paths; this report scope (DD3-2 verification) does not chase them further.

## 4. Brain ↔ DB consistency

- Brain manifest: `total_trades=498`, `cumulative_pnl=-634.92`.
- DB `realized_trades`: 0 rows, no PnL aggregable.
- Reconciliation cannot be performed today; equality `count(realized_trades) ≈ total_trades` and `sum(realized_pnl) ≈ cumulative_pnl` will only become testable once wave-30 starts producing rows.
- `orders.filled` = 1359 against brain `total_trades=498` is consistent with FIFO close pairing (≈2.7 fills per trade, plausible for partial fills + EOD flatten).

## 5. Hash-chain integrity

`ComplianceAuditService.verify_chain_integrity(limit=10000)` →
`{'valid': True, 'records_checked': 220, 'message': 'Chain integrity verified'}`.

All 219 `audit_logs` rows have non-NULL `hash_chain`. Action mix: `user.login=162`, `user.login_failed=57` — purely auth events, no organism-emitted entries (consistent with the BB-10 organism audit-log emit failing or not yet wired into this DB). That is a pre-existing observation, not regressed by wave-43.

## 6. FK integrity / wave-44 EOD-cancel

- `executions LEFT JOIN orders` orphans: 0.
- `executions JOIN orders WHERE status='cancelled'`: 0 (vacuous; both sides empty / cancelled set very small).
- Cancelled orders sample: most recent `cancelled` is `XLK 2026-03-31 16:40Z`; most recent `expired` is `NVDA 2026-04-24 13:28Z`. **No cancellations dated after wave-44 deploy.**
- Reading `live_engine.py:2362-2395` (the EOD-flatten block) shows `_submit_exit_order(... 'eod_flatten')` is invoked for held positions, but `_cancel_pending_entry_orders()` (defined at `live_engine.py:6130`) is NOT called from the EOD branch — only from the drawdown-kill branch (`live_engine.py:2125`). **The wave-44 narrative ("EOD-flatten now cancels pending entries") is not reflected in the deployed `live_engine.py` (mtime `2026-05-03 06:09:25`).** Either the wave-44 patch was scoped to the drawdown path only, or an additional EOD cancel-pending hook is still pending.

## 7. Schema drift / migrations

- `scripts/ci/check_migrations.py` → `[OK] migration tree is linear with single head.` (15 migrations, head `20260503_000001`, base `706e00fe1a28`.)
- `docker exec intra-api-1 alembic current` → `20260503_000001 (head)`.
- DB schema and migration head are aligned; no drift.

## 8. Brain backup directory

`docker exec intra-api-1 ls -la /app/organism_brain/backups/` → **`No such file or directory`**.

The brain root (`/app/organism_brain/`) is well-populated and was rewritten 2026-05-03 06:11Z (manifest, ML joblibs, equity curve, etc.), so the brain itself IS persisting — but the wave-41 PP-1/PP-2 expectation of a `backups/` subdirectory with at least one snapshot is not satisfied. (Memory note already flags this as "brain-backup IS working (don't re-flag)" in `known_issues_paper.md`; recording it here for completeness only — not raised as a finding.)

---

## Findings

### Finding BB4-F1 — wave-43 DD3-2 LotTracker fix is deployed but cannot yet be validated empirically (BLOCKED-ON-MARKET)
**Severity:** Informational / wait-and-see.
**Evidence:** Container `intra-api-1` carries the wave-30 BB-8 patched `alpaca_stream.py` (mtime `2026-05-03 06:02:35Z`, lines 545-610 invoke `LotTracker.create_lot` and `close_lots_fifo` from the order-update handler). `LotTracker` itself is correct (`SELECT … FOR UPDATE` + FIFO, balanced `qty/remaining_qty` accounting). BUT `SELECT count(*) FROM orders WHERE status='filled' AND created_at >= '2026-05-03 06:06Z'` is 0 — the container rebuilt after market close, no live fill has yet exercised the new path. `position_lots=0` and `realized_trades=0` are the *expected* state, not evidence of a remaining bug. The wave-43 partial-fill duplicate guard also cannot be confirmed yet (no rows to dedup). **Action:** retest this query Monday 2026-05-04 ≥30 min after first fills. If `position_lots` is still 0 with non-zero post-deploy fills, escalate.

### Finding BB4-F2 — Wave-44 EOD-flatten does NOT cancel pending entry orders (only drawdown-kill does)
**Severity:** Medium (orphan-fill risk at 15:58 ET).
**Evidence:** `backend/organism/live_engine.py:6130` defines `_cancel_pending_entry_orders()` and it is invoked **only from the drawdown-kill branch** (`live_engine.py:2125`). The EOD-flatten branch (`live_engine.py:2363-2395`, gated on `_eod_flatten_triggered and current_positions`) loops `current_positions` and submits sell exits, but never calls the cancel-pending hook. A pending entry that hasn't filled by 15:58 ET can therefore still fill *after* the flatten loop completes, leaving an unintended overnight long. The audit prompt's premise ("wave-44 EOD-flatten now cancels pending entries") is not currently in code on `rc-1.5-curated@c048103`. **Action:** add `await self._cancel_pending_entry_orders()` either before or after the EOD sell loop (before is safer — kills stale entries first), or scope-clarify the wave-44 changelog if EOD-cancel was intentionally deferred.

### Finding BB4-F3 — Hash chain healthy, but organism never emits to `audit_logs`
**Severity:** Low (no regression, but BB-10 promise unmet).
**Evidence:** All 219 `audit_logs` rows verify (`ComplianceAuditService.verify_chain_integrity → valid:True, records_checked:220`). Action distribution is `user.login=162` / `user.login_failed=57` — i.e. only the FastAPI auth path writes audit rows. No `organism.*` / `drawdown.*` / `position.*` / `eod.*` actions are present, despite `live_engine.py:2106-2123` containing a `BB-10: drawdown-kill audit log dispatch` block. Either no drawdown-kill ever fired in the captured window, or the organism's audit-log dispatch silently warns-and-continues (the `try / except _audit_err: logger.warning` pattern at `live_engine.py:2118` confirms the latter is plausible). **Action:** verify whether organism audit emission is wired through a dispatcher that targets this DB at all; if not, BB-10's compliance-audit promise is not yet observable.

---

## TL;DR

The wave-43 DD3-2 LotTracker fix is **physically present in the running container** (`alpaca_stream.py` mtime 2026-05-03 06:02Z, BB-8 block at lines 545-610), and the LotTracker service itself is logically sound (row-locked FIFO, balanced lot accounting, hash chain healthy). `position_lots=0` and `realized_trades=0` today are **explained by zero post-deploy fills** — last fill was Fri 2026-05-01 19:42Z, container rebuilt 2026-05-03 06:10Z, market closed since — so empirical validation must wait until Monday's open. Two adjacent issues surfaced: (BB4-F2) the wave-44 EOD-flatten does NOT call `_cancel_pending_entry_orders()` — only drawdown-kill does, leaving a 15:58-ET orphan-fill window; and (BB4-F3) the organism never emits to `audit_logs` despite BB-10 wiring, so chain coverage is auth-events only. No FK orphans, no schema drift, no NULL leaks.
