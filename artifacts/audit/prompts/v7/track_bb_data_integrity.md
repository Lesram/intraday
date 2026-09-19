# Track BB v7 — Data Integrity & Invariants (NEW SURFACE)

V1 Track G covered reconciliation. V4 Track N covered DB schema parity.
V7 Track BB extends to comprehensive **invariants**: state machine
enforcement, audit trail completeness, compensating transactions,
referential integrity, and immutable history.

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `d44eace`.

## Files in scope

- `backend/infra/schemas.py` — every ORM model
- `backend/migrations/versions/` — every Alembic migration
- `backend/services/*.py` — every state-mutating service
- `backend/organism/live_engine.py` — order/position state machine
- `backend/api/routes/*.py` — every state-mutating route

## Method

### 1. Database constraint inventory

For each table:
- PRIMARY KEY: yes (sanity)
- FOREIGN KEY: where required — actually declared?
- NOT NULL: every field that should never be null
- UNIQUE: every field with uniqueness invariant
- CHECK: any business-rule constraints (e.g. `qty > 0`, `price >= 0`)

Build a matrix:

| Table | Constraint | ORM-declared | DB-has | Verdict |
|---|---|---|---|---|
| orders | client_idempotency_key UNIQUE | ? | ? | ? |
| position_lots | remaining_qty CHECK >= 0 | ? | ? | ? |
| ... |

Same comparison Track N did for types — but for *constraints*. Drift = bug.

### 2. State machine invariants

For each tracked state machine:
- **orders.status**: pending → submitted → accepted → filled / rejected / cancelled / expired. What transitions are valid? Any code path that bypasses? Database-enforced (CHECK / trigger) or app-enforced only?
- **position_lots.status**: open → closed. Any reverse transition possible?
- **outbox.status**: pending → sent / failed. Wave-12b lease bumps `next_attempt_at` but doesn't change status; verify no inconsistent state.

For each: build a state diagram (text/table form) and audit transitions.

### 3. Position vs lot consistency

The platform has two parallel views of "open positions":
- Broker positions (Alpaca account)
- Local lots (`position_lots` table)

Audit: when do they diverge?
- Reconciliation gap
- Broker drift (manual close, partial fill mid-flight)
- Lot creation race (two concurrent buys)

Are there any periodic reconciliation jobs? Are divergences alerted?

### 4. Audit trail completeness

For each high-blast event, verify there's an immutable audit record:
- Order submitted / filled / cancelled
- Position opened / closed
- Drawdown-kill triggered
- Governance halt / unhalt
- ML model promotion / rollback
- Configuration changes (env var changes mid-run)

Build a coverage matrix. An "alert" doesn't suffice; an audit record needs
to be queryable later.

### 5. Compensating transactions

For multi-step business processes, verify compensation:
- Order submission: outbox enqueue + broker call + DB update. If broker
  succeeds but DB write fails — compensation?
- Lot close: outbox + broker + position_lots update + realized_trades
  insert. Atomicity? If the realized_trades insert fails after position_lots
  was decremented — compensation?
- Brain save: 10 file writes. Wave-19 made each atomic per file, but the
  set is not atomic. If write 5 fails after 1-4 succeeded — compensation?

For each: failure mode × compensation × verdict.

### 6. Referential integrity

- For every `order_id`, `lot_id`, `user_id` foreign reference: is the FK declared at the DB level?
- N-H-1 already aligned PositionLot.user_id with DB type but dropped the FK. Is that defensible?
- Any orphaned rows in production right now? `SELECT count(*) FROM position_lots WHERE order_id NOT IN (SELECT id FROM orders);`

### 7. Idempotency keys

- Every order has `client_idempotency_key` (UNIQUE).
- Every outbox event has an idempotency mechanism.
- Are these collision-resistant? Format: `organism_<sym>_<ET-day>_<session>_<tick>` per wave-21 marker.
- Audit: tick collisions in the same minute? Same-second submissions?

### 8. Concurrency invariants

- Two ticks at the same time: V1 G + V4 N audited basic locking. Re-verify.
- Lock ordering: `_tick_lock` + `_cancel_locks` + outbox `FOR UPDATE` — any pair acquired in opposite orders anywhere?
- DB transactions: any nested transactions? `session.begin_nested()`?

### 9. Time-series invariants

- `trade_history.csv` rows are immutable once written.
- `equity_curve.csv` is append-only (post wave-14 cap).
- `manifest.json.saved_at` is monotonic? (Wave-20b X-3 routed through `_now_fn`.)
- Bar timestamps: monotonic per symbol within a session?

### 10. Brain manifest invariants

The manifest declares system state; the on-disk files are the substrate.
For each manifest field, find:
- The on-disk source of truth
- Any divergence path (drift)

Examples: `manifest.generation` vs `learning_state.generation`,
`manifest.total_trades` vs `len(trade_history.csv)`,
`manifest.cumulative_pnl` vs `sum(trade_history.csv.pnl)` (wave-17d
reconciliation log already catches the last one).

## Output

`artifacts/audit/v7_reports/track_bb_data_integrity.md` with:
- Constraint matrix (table × constraint × declared × in DB × verdict)
- State machine diagrams per tracked entity
- Position-vs-lot consistency analysis
- Audit trail coverage matrix
- Compensating-transaction inventory
- Referential integrity verdict
- Idempotency-key collision audit
- Concurrency lock-ordering check
- Time-series + manifest invariants
- "Bugs found: N" + TL;DR

## Constraints

Read-only. `psql` SELECTs ok; do NOT INSERT/UPDATE/DELETE.

## Quality bar

Expect 5-10 findings. Especially:
- A NOT NULL or CHECK constraint missing in DB despite ORM declaring it.
- A state transition that the app permits but DB doesn't enforce.
- An audit gap on a high-blast event.
- A compensating-transaction path with no compensation.

End with a one-paragraph summary.
