# Track TT3 v11 — Performance Phase 3

**Branch:** `rc-1.5-curated` @ `3778344` (working-tree dirty: only `monitoring/memory_monitoring.json`)
**Run window:** 2026-05-03 ~11:30 PT (Saturday, market closed)
**Scope:** Read-only profiling, EXPLAIN ANALYZE, verify TT-2/TT-4/TT-5 hardening still holds.

---

## 1. Live tick latency since rebuild — DATA UNAVAILABLE

Container `intra-api-1` was rebuilt at `2026-05-03T18:30:11Z`, ~6 min before this audit. Market is **closed** (Saturday). Result:

* `docker logs intra-api-1 --since 2h | grep -E "tick.*duration|Tick complete"` → **0 lines**.
* Prometheus `organism_tick_duration_seconds_count` = **0.0** at `localhost:8000/metrics`.
* Last-24h log volume = **433 lines** total (almost all startup banners).

**No latency samples to compare against V10 baseline (p50=2.6s, p95=7.5s, p99=13.0s).** Re-run on Monday after market open will populate the histogram.

## 2. Watchdog timeouts (TT-2)

`docker logs intra-api-1 --since 24h | grep -E "TT-2.*watchdog FIRED" | wc -l` → **0**.

TT-2 implementation verified at `backend/organism/live_engine.py:1583-1662`. Watchdog wraps `_live_tick_inner()` in `asyncio.wait_for(timeout=30.0s)`, increments `self._tick_watchdog_timeouts`, logs `TT-2: tick watchdog FIRED`, dispatches `AlertCategory.SYSTEM_ERROR / WARNING`, returns degraded `LiveTickResult`. No fires since deploy.

## 3. cProfile of synthetic tick — N/A

The live engine is too tightly coupled (Alpaca client, brain restore, sessionmaker, streaming provider, prometheus globals) to construct a synthetic tick in isolation in the timeframe. Used import-time profile as a proxy for static cost: 1.107s import dominated by xgboost (0.72s) — startup-only, irrelevant to per-tick perf. **Recommend a tick-fixture in `tests/test_live_engine.py` for V12** to enable repeatable cProfile runs.

## 4. SQL query latency audit (EXPLAIN ANALYZE)

Tables: `orders` 1,332 live rows / 6.2 MB total / 2.3 MB heap; `outbox_events` 1,398; `tick_telemetry` 0; everything else <340 rows. Tiny dataset.

| Query | Plan | Wall time |
|---|---|---|
| Latest-10 filled orders by `submitted_at` | Index Scan Backward on `ix_orders_submitted_at` | **0.07 ms** |
| Per-symbol last sell exit (`symbol='AAPL' AND side='sell' AND status='filled' AND attributes->>'source'='organism'`) | Bitmap Index Scan `ix_orders_symbol_status` + filter | **0.17 ms** |
| Reconstruct-trades on startup (`status='filled' AND attributes->>'source'='organism' ORDER BY submitted_at`) | **Seq Scan + Sort** | **1.86 ms** |
| Same query rewritten with `attributes @> '{"source":"organism"}'` | **Bitmap Heap Scan via `ix_orders_attributes_gin`** | 2.4 ms |

Index inventory on `orders` (15 indexes total) and per-index scan counts:
* `ix_orders_symbol_status` — 526,144 scans (hot path)
* `idx_orders_broker_order_id` — 32,579
* `pk_orders` — 2,503
* `ix_orders_submitted_at` — 1,109
* `ix_orders_attributes_gin` — **0** ← unused

DB connection pool: **6 connections** (1 active / 5 idle), well under 20-conn ceiling. No leak.

## 5. TT-4 async rate-limit verify — PASS

`grep -n "self\._rate_limit\(\)\|self\._async_rate_limit\(\)" backend/data/alpaca_client.py`:
* Line 346 (`get_historical_data`): `self._rate_limit()` — sync, OK
* Line 840 (`get_current_price`): `self._rate_limit()` — sync, OK
* Lines 487, 638, 703, 780, 934 (`_api_call_with_retry`): `await self._async_rate_limit()` — async path
* Spec called for "2 sync + 4 async"; actual is **2 sync + 5 async** (the 5th is in `_api_call_with_retry`, the retry wrapper that the 4 callers route through). Same intent, hardened correctly. Comment at line 904 documents the migration.

## 6. TT-5 list-bounds verify — REGRESSION RISK

* `MomentumPyramider._pyramid_count` (`pyramider.py:203,310,330`) — scalar counter, telemetered via `.telemetry()` (DD4-4). No list. PASS.
* `ContinuousLearner.trade_history` (`continuous_learner.py:259-273`) — capped at `_TT5_MAX_HISTORY = 10_000`. PASS.
* `DecisionTelemetryStore` (`decision_telemetry.py:397`) — `deque(maxlen=360)`. PASS.
* `regime._history` / `regime._aggregate_history` (`regime.py:340,538`) — trimmed to `_churn_window * 2`. PASS.
* `scheduler._tick_history` — `deque(maxlen=...)`. PASS.
* `KellySizer._exploration_rejects` (`kelly_sizer.py:238`) — re-initialized each `size_positions()` call. PASS.
* **`live_engine.py:589 self._all_trades: list[TradeRecord] = []`** — **UNBOUNDED.** Appended at `live_engine.py:5623` on every closed trade; restored from brain on startup; iterated by `signal_gen.train`, `_evolve_symbol_fitness`, `recent-trades` API. The TT-5 fix capped `learner.trade_history` but the parallel list in `live_engine` was missed.
* **`self_evolution.py:285 self._evolution_log: list[dict[str, Any]] = []`** — **UNBOUNDED.** Appended on every `evolve()` call (`self_evolution.py:363`). Slow growth (1 entry/evolution step, gen 168 today), but no trim.

Both are minor over a session lifetime — not the ~30k+ equity-curve spike that drove the V10 fix — but they are the only remaining unbounded `.append()` sites in `backend/organism/`.

## 7. Memory growth

| t | RSS |
|---|---|
| t0 (audit start) | 263 MiB |
| t0 + ~5 min | 263.9 MiB |

CPU 4.5–6%. PIDs 38. No drift in the audit window (market closed, ticks idle). Inconclusive for production growth slope; re-sample after a full session for a real signal.

## 8. DB connection pool — PASS

`pg_stat_activity` for `algotrading`: 1 active + 5 idle = 6 total. Below the 10-conn target.

## 9. Async task accumulation — INTROSPECTION-LIMITED

`docker exec intra-api-1 python -c "asyncio.get_event_loop(); print(len(asyncio.all_tasks(loop)))"` → 0 (DeprecationWarning: no current event loop). The uvicorn worker loops are not visible to a fresh subprocess; documenting as expected. Need an in-process introspection endpoint (e.g., `/admin/asyncio_tasks`) to track this — V12 candidate.

## 10. Hot-path optimizations to ship in V12

(Quality bar = 1–3 findings; ranked by expected impact / effort.)

---

## Findings

### F1 — `ix_orders_attributes_gin` is dead weight; 3 hot call sites can't use it
**Severity:** P2 (perf hazard that grows with `orders` table)
**Location:**
* GIN index defined: `\d orders` → `"ix_orders_attributes_gin" gin (attributes)`
* Call sites that bypass it (use `->>`, which a default `gin (jsonb)` index cannot accelerate):
  * `backend/organism/live_engine.py:1428` — startup `_reconstruct_trades_from_db`
  * `backend/organism/live_engine.py:5910` — per-symbol exit fill lookup `_lookup_db_exit_fill_price`
  * `backend/organism/routes.py:563` — REST endpoint

**Evidence:** `idx_scan = 0` for `ix_orders_attributes_gin` (vs 526,144 for `ix_orders_symbol_status`). EXPLAIN of `WHERE attributes->>'source'='organism'` shows **Seq Scan**; rewriting to `WHERE attributes @> '{"source":"organism"}'` produces **Bitmap Index Scan on ix_orders_attributes_gin**. Today wall time is fine (1.9 ms over 1,369 rows) because the table is tiny. At 100× growth (~135k orders), Seq Scan goes O(n) while Bitmap stays O(matched).

**Fix options (V12):**
1. Cheapest: rewrite the 3 call sites to use `attributes @> '{"source":"organism"}'` (SQLAlchemy: `Order.attributes.contains({"source":"organism"})`). Index becomes hot immediately.
2. Or replace the GIN index with `gin (attributes jsonb_path_ops)` — smaller and faster, still containment-only.
3. Or add a btree expression index `((attributes->>'source'))` if `->>` form must stay.

Carries the V10 TT-3 finding forward — the diagnosis was correct, but the GIN index alone (without rewriting call sites) was insufficient.

### F2 — Two unbounded lists missed by TT-5: `_all_trades` and `_evolution_log`
**Severity:** P3 (slow leak, hits at multi-year horizon)
**Location:**
* `backend/organism/live_engine.py:589` — `self._all_trades: list[TradeRecord] = []`, appended at line 5623, never trimmed.
* `backend/organism/self_evolution.py:285` — `self._evolution_log: list[dict[str, Any]] = []`, appended at line 363, never trimmed.

**Evidence:** TT-5 (Wave-47) capped `ContinuousLearner.trade_history` at `_TT5_MAX_HISTORY = 10_000` in `continuous_learner.py:267`, but the parallel list in `live_engine` and the evolution audit log were left uncapped. Today: `_all_trades` is at ~482 entries (per memory), `_evolution_log` at ~168. Both are iterated by training and self-evolution paths every retrain, so growth shows up as O(n) per-tick cost in those branches once they get large enough.

**Fix (V12):**
* Apply the same `_TT5_MAX_HISTORY = 10_000` cap to `_all_trades` (after every append, slice off the head if over). Mirror the existing pattern in `continuous_learner.record_trade`.
* For `_evolution_log`, cap to e.g. 500 entries — it's purely a diagnostic log.
* One-line trim per append, no algorithm change.

### F3 — Per-tick latency telemetry not yet readable; the `/metrics` histogram is the sole sink
**Severity:** P3 (operability, not perf)
**Location:** `backend/organism/live_engine.py:4426-4430` records `result.duration_s` and pushes to `ORGANISM_TICK_DURATION` histogram — but **no log line emits the per-tick duration**, and the histogram only updates the bucket counts (no exemplars / per-tick line).

**Evidence:** `docker logs --since 2h | grep -E "tick.*duration|Tick complete"` returns nothing even when the engine is running (V10 baseline data must have been pulled from another sink, e.g. the histogram exporter or a slow-tick branch). Today the only perf signal is a bucketed histogram that loses sub-second resolution and timestamps.

**Fix (V12):**
* Add a `logger.info(...)` slow-tick line at `live_engine.py:4426` whenever `result.duration_s > <threshold, e.g. 5.0>` (production noise stays low; outliers become greppable).
* Optionally emit a structured per-tick latency event every N=60 ticks for percentile calc from logs.

This is what the prompt's step 1 grep was reaching for — the line doesn't exist yet.

---

## Status summary

| Area | State |
|---|---|
| Tick latency since rebuild | No samples (market closed) |
| TT-2 watchdog | 0 fires; code path verified |
| TT-4 async rate limit | 2 sync + 5 async (matches intent) |
| TT-5 list bounds | 2 regressions found (F2) |
| DB SQL hot paths | 0.07–1.9 ms; all small. GIN index unused (F1) |
| DB connection pool | 6 conns, healthy |
| Memory | 263 → 263.9 MiB over 5 min, no growth in window |
| Async task introspection | Not exposed; needs admin endpoint |

**Carry-forward for V12:** F1 (rewrite 3 attributes-source call sites OR drop the unused GIN index), F2 (cap `_all_trades` + `_evolution_log`), F3 (add slow-tick log line so latency is greppable without Prometheus).

