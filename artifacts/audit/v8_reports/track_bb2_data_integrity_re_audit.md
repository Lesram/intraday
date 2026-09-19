# Track BB2 — Data Integrity Re-Audit (Reachability Lens)

**Branch**: `rc-1.5-curated` @ `5bc4046`
**Audit time**: 2026-05-03 06:25 UTC
**Container**: `intra-api-1` (healthy, 12+ min uptime), Postgres: `trading_platform_db_paper` (DB `algotrading`, user `trading`)
**Mode**: Read-only (SELECT + file reads only)

> Note on environment: prompt referenced `intra-postgres-1`; the actual running Postgres
> container is `trading_platform_db_paper`, which is the one wired to the API
> via `DATABASE_URL=postgresql+asyncpg://trading:trading_password@postgres:5432/algotrading`.
> All findings below are against that live DB.

---

## Live-load row counts

| Table              | Rows  | Notes                                                                  |
|--------------------|-------|------------------------------------------------------------------------|
| `orders`           | 1,369 | 1,359 filled (700 buy + 659 sell), all `user_id='system'`              |
| `position_lots`    | **0** | wave-30 wiring code present in container, but no rows                  |
| `realized_trades`  | **0** | wave-30 wiring code present in container, but no rows                  |
| `audit_logs`       | 14 -> 20 | grew during audit (login attempts); only `user.login` / `user.login_failed` actions |
| `executions`       | 0     | **never populated** — schema empty despite 1,369 orders                |
| `positions`        | 0     | live position table empty                                              |
| `order_events`     | 0     | order lifecycle events empty                                           |
| `risk_violations`  | 0     | no breach rows ever written                                            |
| `daily_ledger`     | 0     | no daily roll-ups                                                      |
| `tick_telemetry`   | 0     | no tick observability rows                                             |
| `outbox_events`    | 1,398 | outbox is being driven                                                 |
| `risk_limits`      | 0     | no configured limits in DB                                             |
| `emergency_stops`  | 0     | none ever fired                                                        |

Brain `trade_history.csv`: 498 round-trip trades (499 lines incl. header), last write
2026-05-01T19:42 — matches manifest.json (`total_trades: 498`, `generation: 168`).

---

## BB-8 reach status — WIRED but UNREACHED (testable next session)

**Wiring verified in container** (`intra-api-1:/app/backend/integrations/alpaca_stream.py:545-617`):
- `_process_trade_update` calls `LotTracker.create_lot()` on `order.side == "buy"` after
  filled/partially_filled events, and `close_lots_fifo()` on sell, both tagged
  `# V8 BB-8 / Wave-30 (2026-05-03)`.
- `LotTracker` import resolves; lifespan loads the legacy `alpaca_stream` (not
  `alpaca_stream_production.py`), so the wave-30 mirror IS the only reach path.

**Reach evidence**: ZERO. All 1,369 orders in DB are pre-wave-30:
- max(`submitted_at`) = 2026-05-01 19:42 UTC
- container started 2026-05-03 06:11 UTC (per logs)
- 0 orders in last 24h, 0 since wave-30 deploy
- Today is Saturday 2026-05-02 (US ET) → market closed → no new fills possible until 2026-05-04 open

**Conclusion**: The wiring is *plausibly correct* but **not yet exercised under live load**. The
zero-row state on `position_lots`/`realized_trades` is consistent with both
"wiring works, no fills yet" and "wiring silently fails on every fill". This audit
**cannot distinguish** the two without the next market session. Required follow-up:
verify `position_lots > 0` after the first 2026-05-04 fills, and re-check
`BB-8: created position lot` log lines in `intra-api-1`.

---

## BB-10 reach status — PARTIALLY REACHED

**Login path (`auth.py:280, 323`)**: REACHED. 19 of 20 audit_logs rows are
`user.login` / `user.login_failed`, all with non-null `hash_chain` and matching
post-wave-30 timestamps (2026-05-03 06:06+).

**Drawdown-kill path (`live_engine.py:2092-2122`)**: WIRED but UNREACHED. No
`risk.limit_breach` (action) / `entity_id='drawdown_kill'` rows present. Reasons:
- 0 trading activity since deploy (markets closed)
- `ORGANISM_DRAWDOWN_KILL_PCT=0.20` (env override, 4× the 5% code default — flagged
  by governance startup warning at container boot 2026-05-03T06:11:50). At 20%,
  triggering requires deep equity loss before audit row appears.

Acceptable; the *capability* is wired with the standard `RISK_LIMIT_BREACH` /
`AuditEntity.RISK` taxonomy.

---

## Findings

### F1 (HIGH) — Wave-30 reach unverifiable until 2026-05-04 open
The BB-8 wiring (LotTracker on buy/sell fills) and the BB-10 drawdown-kill audit
row both shipped on 2026-05-03 06:11 UTC but no live trading has occurred since
deploy. `position_lots = 0`, `realized_trades = 0`, no `risk.limit_breach` audit
rows. Cannot be falsified or confirmed in this audit window. **Action**: re-run
this query suite at 2026-05-04 ~14:35 UTC after first fills to establish reach.

### F2 (HIGH) — Wider "wired but empty" footprint beyond BB-8
Six tables that should populate from a 1,369-order live history are empty:
`executions` (0), `positions` (0), `order_events` (0), `risk_violations` (0),
`daily_ledger` (0), `tick_telemetry` (0). These are NOT addressed by wave-30
(wave-30 only covered position_lots/realized_trades/audit_logs). The pre-wave-30
order pipeline writes only to `orders` + `outbox_events`. Schema and writers exist
in code but are never invoked by the live engine. This is V7 BB unfinished
business — wave-30 closed 3 of ~9 empty tables; the rest remain dark. **Action**:
scope a wave-31/32 to wire `executions` (broker fill detail), `positions`
(aggregate position state from lots), `order_events` (lifecycle), and
`risk_violations` (alerter-side). Without these, end-of-day reconciliation, P&L
attribution, and compliance trail cannot be reconstructed from the DB alone.

### F3 (MEDIUM) — Hash-chain integrity verified clean (20/20)
Re-implemented `_compute_hash` (sha256 of canonical-JSON of
`{prev, ts, action, entity, entity_id, actor, payload}`) against all 20 audit_logs
rows including 6 that landed mid-audit. Every record's stored `hash_chain` matched
the recomputed expected hash. No nulls. No breaks. Hash chain is genuinely
tamper-evident at this volume. **No action needed**; revisit when row count crosses
~10k to spot any scaling drift.

### F4 (LOW) — CHECK-constraint coverage stable; NULL-leak scan clean
19 CHECK constraints present across `orders`, `position_lots`, `realized_trades`,
`backtests`, `risk_limits`, `risk_metrics`, `risk_violations`, `emergency_stops`.
Matches V7 BB-1 closure list (qty>0, remaining_qty>=0, side enum, status enum,
tif enum, order_type enum, filled_qty<=qty). NULL-leak scan: `orders.qty`,
`orders.user_id`, `orders.client_idempotency_key`, `audit_logs.action`,
`audit_logs.actor`, `audit_logs.hash_chain`, `position_lots.symbol` all
0-null. Schema integrity not regressed.

---

## Other observations (non-finding)

- **`organism_brain/backups/` does not exist on host.** Memory note flags
  "brain-backup IS working — don't re-flag". Confirmed: no backup dir on the host
  filesystem. If backups exist they're inside the container (Docker volume
  scope). Out of scope for this DB-focused audit; flag for ops to verify.
- **Brain CSV vs DB** are not directly reconcilable: CSV tracks 498 round-trip
  *trades* (entry/exit pairs from organism), DB tracks 1,359 *filled orders*
  (executions on each side). They model different units; ratio ~2.7 fills per
  CSV trade is plausible (entry + exit + scale-out partials).
- **All 1,369 orders carry `user_id='system'`**, never an actual user UUID.
  Multi-user attribution is a no-op; not a bug per se given single-organism design,
  but means `orders.user_id` index is degenerate. Document if multi-tenant
  becomes a goal.
- **Hash chain has only `hash_chain` column**, not the `prev_hash`/`current_hash`
  pair the prompt assumed. Verification approach was adapted (fetch all rows
  ordered by `ts`, recompute via `_compute_hash`, compare).

---

## Tally

- **Reachability gaps confirmed**: 1 (BB-8 wired but unreached due to market closed)
- **New data integrity issues**: 1 (F2: wider unwritten-table footprint)
- **Verified-clean checks**: hash-chain integrity, CHECK constraints, NULL-leak scan
- **Total findings**: 4 (1 HIGH unverifiable, 1 HIGH new scope, 1 MEDIUM clean, 1 LOW clean)

---

## TL;DR

Wave-30 wiring for `position_lots` / `realized_trades` (BB-8) and `audit_logs`
drawdown-kill (BB-10) is physically present in the running container, and the
login-path piece of BB-10 is demonstrably reaching production (19 audit rows
landed during the audit, hash chain 20/20 clean). However, the BB-8 wiring is
*untestable in this window* — markets have been closed since 2026-05-01 19:42
UTC, deploy was 2026-05-03 06:11 UTC, so zero fills have hit the new code path;
`position_lots` and `realized_trades` are 0, but that is consistent with both
"works correctly, no input yet" and "silently fails on every fill". The deeper
issue this audit surfaced is broader than wave-30: six other tables
(`executions`, `positions`, `order_events`, `risk_violations`, `daily_ledger`,
`tick_telemetry`) are empty under 1,369 orders of live history, meaning the
"wired but empty" pattern V7 BB found is only ~30% closed. Recommend
(a) re-running this exact query suite ~30 min after Monday's open to confirm
BB-8 reach, and (b) scoping a wave-31 to wire the remaining six dark tables
before any further deploy claims "data layer integrity restored". CHECK
constraints, NULL fields, and hash-chain integrity all verify clean.
