# V9 Track TT — Performance / Latency

Branch: `rc-1.5-curated` @ `ccba97f`
Date: 2026-05-02
Scope: tick latency, query plans, memory growth, async hot paths.
Method: log forensics on `logs/application.log` (16,560 organism ticks, 2026-04-20 → 2026-05-02), AST scan, EXPLAIN ANALYZE on running paper DB, container snapshot. **No code changes.**

---

## Summary tables

### Tick duration (real production data, 16,558 ticks; 2 reconnect outliers @ 1987.7s / 1256.9s excluded)

Source: scheduler emits `Organism tick: regime=… signals=… orders=… exits=… <duration>s` at line 341 of `backend/organism/scheduler.py`. Parsed across 30 days of paper traffic.

| pct  | duration |
|------|----------|
| min  | 1.90 s   |
| p50  | 2.60 s   |
| p90  | 4.90 s   |
| p95  | 7.50 s   |
| p99  | 13.00 s  |
| p99.9| 19.30 s  |
| max  | 26.70 s  |
| mean | 3.47 s   |

Budget overruns vs scheduler `tick_interval=10s`:

| threshold | count | % of ticks |
|-----------|-------|------------|
| > 5 s     | 1,581 | 9.55 %     |
| > 8 s     | 729   | 4.40 %     |
| > 10 s    | 444   | **2.68 %** |
| > 15 s    | 87    | 0.53 %     |
| > 20 s    | 14    | 0.08 %     |

**Includes pathological outliers:** two ticks of 1987.7 s and 1256.9 s on 2026-05-01 14:53Z and 15:14Z, co-located with `WebSocket connection closed: 1011 keepalive ping timeout` from `alpaca_market_data_stream`. The tick was blocked on a stalled streaming-provider await during reconnection — see Finding 2.

By regime (excluding 60s+ outliers):

| regime         | n      | p95   | p99   | max   |
|----------------|--------|-------|-------|-------|
| chop           | 15,609 | 7.7 s | 13.3 s| 26.7 s|
| high_vol       | 506    | 5.4 s | 6.6 s | 9.0 s |
| trending_up    | 285    | 4.1 s | 6.4 s | 9.1 s |
| stress         | 111    | 4.6 s | 6.0 s | 6.2 s |
| trending_down  | 46     | 5.6 s | 8.9 s | 8.9 s |

Chop regime drives the p95/p99 tail — chop is when the universe is quiet, signals=0, and the engine still rotates through the full 22-symbol scan + feature compute + telemetry serialisation.

By signal generation:

| bucket       | n       | p95   | p99   | max    |
|--------------|---------|-------|-------|--------|
| signals=0    | 16,294  | 7.5 s | 13.0 s| 26.7 s |
| signals ≥ 1  | 264     | 9.1 s | 15.2 s| 24.5 s |

**Signal-generating ticks are slower** — order placement, telemetry persistence, exit-level updates pile on. This is the path the user actually cares about.

By hour-of-day (UTC, market open is 13:30Z / 14:30Z DST):

| hr  | n     | p50   | p95    | p99    |
|-----|-------|-------|--------|--------|
| 13Z | 1,152 | 2.5 s | 6.5 s  | 11.9 s |
| **14Z** (open) | **2,056** | 3.1 s | **10.2 s** | 14.9 s |
| 15Z | 2,528 | 2.7 s | 8.4 s  | 12.4 s |
| 16Z | 2,720 | 2.6 s | 5.5 s  | 11.0 s |
| 17Z | 2,669 | 2.6 s | 7.5 s  | 15.2 s |
| 18Z | 2,699 | 2.7 s | 5.9 s  | 11.2 s |
| 19Z | 2,686 | 2.6 s | 7.3 s  | 13.6 s |

**Market open is the worst window** — p95 hits 10.2s, exactly the scheduler interval. This is when fresh signals are generated and trades fire.

### Query plans (paper DB, EXPLAIN ANALYZE)

| Query | Site | Plan | Cost |
|-------|------|------|------|
| Reconstruct trades on startup | `live_engine.py:1338` | **Seq Scan** on `orders` (1,369 rows), filter on `(status='filled' AND attributes->>'source'='organism')` then sort | 1.22 ms execution; planner estimated `rows=7` actual `rows=1359` (175× cardinality miss) |
| Per-exit fill lookup | `live_engine.py:5592` | Bitmap Index Scan on `ix_orders_symbol_status` → filter on side+JSON → top-N heapsort LIMIT 1 | 0.16 ms |
| `SELECT 1` health checks | `database/*.py` | trivial | <0.1 ms |

DB is **not** the bottleneck. Both queries are sub-millisecond on a 1,369-row `orders` table. **However**, the trade-reconstruction Seq Scan will degrade linearly as `orders` grows — at 100k rows this becomes a multi-hundred-millisecond startup cost. The `attributes->>'source'` predicate cannot use a btree index. (See Finding 3.)

### Container snapshot (`docker stats --no-stream`)

| container | CPU% | Memory | Net I/O | Block I/O | PIDs |
|-----------|------|--------|---------|-----------|------|
| intra-api-1 | 4.33 % | 279.7 MiB / 4 GiB (6.83 %) | 205 MB / 49.5 MB | 68.5 MB / 36.5 MB | 38 |
| trading_platform_db_paper | 1.15 % | 70.86 MiB / 7.65 GiB | 71 MB / 349 MB | 35.7 MB / 7.54 MB | 11 |
| intra-redis-1 | 0.73 % | 11.93 MiB / 7.65 GiB | minimal | minimal | 6 |

API memory at 280 MiB after 2h is nominal; need a longer window to confirm flat slope. **`pg_stat_activity` shows 6 connections (1 active, 5 idle) against a pool of 10–20** — no leak, no saturation.

### Async hot-path scan

- `time.sleep` inside async functions: **AlpacaClient._rate_limit() called from 4 async methods** (`submit_order`, `cancel_order`, `get_account_status`, `get_recent_orders`) at lines 487, 638, 703, 780. `_rate_limit` calls `time.sleep(sleep_time)` (line 893). Comment claims "sync callers only" but the AST shows otherwise. See Finding 4.
- `_fetch_bars` correctly offloads sync data-client calls via `asyncio.to_thread`.
- Universe iteration in `_compute_features_for_universe` uses `asyncio.gather` with a `Semaphore(10)` — no serial fan-out.
- No `concurrent.futures.wait` deadlock risk found.

### Memory bounded-growth review

| Buffer | Trim policy | Verdict |
|--------|-------------|---------|
| `OrganismLiveEngine._equity_curve` | trims to `_MAX_EQUITY_CURVE_LEN = 100_000` (live_engine.py:4141) | bounded |
| `OrganismLiveEngine._entry_timestamps` / `_entry_timestamps_15m` | filtered by 1h / 15min sliding window per tick | bounded |
| `OrganismLiveEngine._symbol_stop_loss_times[sym]` | per-symbol filter to last 30 min on every close | bounded |
| `DecisionTelemetryStore._buffer` | `deque(maxlen=360)` | bounded |
| `regime._history`, `_aggregate_history` | trimmed to `churn_window * 2` | bounded |
| `scheduler._tick_history` | `deque(maxlen=…)` | bounded |
| **`OrganismLiveEngine._all_trades`** | **NEVER trimmed**; appended on every closed trade (line 5311), persisted to brain | **unbounded grower** |
| **`OrganismLiveEngine._epoch_metrics`** | **NEVER trimmed** (declared 577, persisted via brain) | **unbounded grower** |
| **`ContinuousLearner.trade_history`** | **NEVER trimmed** (continuous_learner.py:265) | **unbounded grower** |
| **`ContinuousLearner.state.evaluation_events`** | **NEVER trimmed** (line 368) | **unbounded grower** |
| **`ContinuousLearner.state.model_metrics`** | **NEVER trimmed** (line 382) | **unbounded grower** |
| **`ContinuousLearner.state.generation_accuracies`** | **NEVER trimmed** (line 384) | **unbounded grower** |

Today these are tiny (482 trades, ~160 generations). The growth rate is bounded by trading frequency, but at e.g. 50 trades/day this list is 18k entries/year, and the cost at every brain save is O(n) JSON serialisation + disk write. See Finding 1.

---

## Findings

### Finding 1 — Tick budget routinely overrun; market-open ticks at the limit (HIGH)

**Severity:** High — directly wastes the 10s `tick_interval` 2.7 % of the time, and 9.6 % of ticks exceed half the budget.

**Evidence:**
- p95 = 7.5 s, p99 = 13.0 s, max (excluding reconnect) = 26.7 s on 16,558 production ticks.
- 444 ticks (2.68 %) exceeded the scheduler interval; the scheduler wait_for promptly returns and fires the next tick with no idle, so the engine runs back-to-back. Net effect: tick cadence under load is whatever the previous tick took, not 10 s.
- 14:00–15:00Z (market-open hour) p95 = 10.2 s — **at the budget**. This is the window with the most signal generation.
- Signal-generating ticks (signals ≥ 1, n=264): p99 = 15.2 s, max = 24.5 s. The path that actually fires orders is slower than the no-op scanning path.

**Likely culprits (not directly profiled — engine instantiation requires too many real services):**
- 22-symbol concurrent feature compute (`_fetch_bars` + `compute_ml_features` + `add_multi_timeframe_features`) at semaphore=10. Even with thread offload, every tick re-runs feature engineering on a fresh DataFrame slice for all 22 symbols.
- Telemetry serialisation: every tick builds a `DecisionSnapshot` containing alpha/breakout/exit details for every symbol and persists to DB (`_persist_telemetry_to_db` at line 4181).
- ML inference: `MLSignalGenerator.predict_proba` on 79 features per symbol per tick.

**Recommendation (not implemented):**
1. Add an explicit per-stage timer in `_live_tick_inner` (feature_compute_ms, alpha_scan_ms, breakout_scan_ms, ml_inference_ms, exit_check_ms, telemetry_ms) and emit one structured log per tick. **Without this, every future TT track will be guessing.** This is the lens v9 is asking for.
2. Investigate why chop ticks (>97 % of all ticks) take p95=7.7 s when no signals fire — most of the per-symbol work should short-circuit on liquidity gate or low confidence.
3. Consider raising `tick_interval` from 10 s → 15 s as a cheap fix; or shorten work by batching feature recomputation only on bar boundaries (1Min bars → recompute once per minute, not every 10 s).

### Finding 2 — Stream reconnect can stall the tick for 30 minutes; no watchdog timeout on the awaited stream (HIGH)

**Severity:** High — was observed in production this week. A WebSocket keepalive timeout caused a single tick to log 1987.7 s (33 minutes). For 33 minutes the engine processed zero exits.

**Evidence:**
- `application.log` 2026-05-01 14:53:28: `Organism tick: regime=chop signals=0 orders=0 exits=0 1987.7s`.
- Same minute: `WebSocket connection closed: sent 1011 (internal error) keepalive ping timeout` (`alpaca_market_data_stream.py:479`) followed by `Reconnecting in 0.9s (attempt 1/10)`.
- Second outlier 2026-05-01 15:14:47: `regime=high_vol signals=1 orders=1 exits=0 1256.9s` (21 minutes) — and a trade fired during it.
- The scheduler's exception handler runs only for raised exceptions; a long await is not caught, and there is no `asyncio.wait_for` wrapper around the tick body.

**Recommendation (not implemented):**
1. Wrap the tick in `asyncio.wait_for(self.live_tick(), timeout=tick_budget_s)` with a budget like 20–30 s. On timeout, cancel the tick (the next one will retry from current bars) and increment a metric.
2. Audit every `await` inside `_live_tick_inner` for missing timeouts — particularly streaming-provider gets and any broker awaits.

### Finding 3 — JSON predicate `attributes->>'source'='organism'` forces Seq Scan on `orders`; partial expression index missing (MEDIUM)

**Severity:** Medium — currently 1.22 ms because table is 1,369 rows. Will degrade to seconds at production scale; touches startup time and the lifetime of `_reconstruct_trades_from_db`.

**Evidence:**
- `EXPLAIN ANALYZE` of the trade-reconstruction query returns `Seq Scan on orders … Filter: (status='filled' AND attributes->>'source'='organism')` with `cost=0.00..314.29` and **planner row estimate 7 vs actual 1359** (175× off — planner has no statistics on JSON expressions).
- Same predicate appears in `_lookup_exit_fill_from_db` (line 5598). That query rescues with `ix_orders_symbol_status` + post-filter, so it stays fast for now.
- `ix_orders_symbol_status` and `ix_orders_submitted_at` are the only indexes on `orders` (`backend/infra/schemas.py:172-174`). No GIN on `attributes`, no expression index, no partial index.

**Recommendation (not implemented):** Add a partial expression index in a new migration:
```sql
CREATE INDEX ix_orders_organism_filled_submitted
ON orders (submitted_at)
WHERE status = 'filled' AND attributes->>'source' = 'organism';
```
This makes the startup reconstruction O(log n) and stable as the table grows. (Do not touch the migration without coordination — flagged here for the engineering loop.)

### Finding 4 — Async methods in AlpacaClient call sync `time.sleep()` rate-limiter, blocking the event loop (LOW for tick-hot-path; HIGH for the API surface) (MEDIUM)

**Severity:** Medium — these methods are not on the live-tick hot path (organism uses `order_service.broker.cancel_order`), but they are reachable from the API/watchlists/replay paths and from background reconciliation. Each call can block up to `min_request_interval` (typically ~333 ms for 3 req/s) on the shared event loop.

**Evidence (from AST scan of `backend/data/alpaca_client.py`):**
```
ASYNC fn `submit_order` calls sync self._rate_limit() at line 487
ASYNC fn `cancel_order` calls sync self._rate_limit() at line 638
ASYNC fn `get_account_status` calls sync self._rate_limit() at line 703
ASYNC fn `get_recent_orders` calls sync self._rate_limit() at line 780
```
`_rate_limit` body (line 878): `time.sleep(sleep_time)`. Module already provides `_async_rate_limit` (line 897) using `asyncio.sleep` — it's just not wired in.

**Recommendation (not implemented):** Replace the four `self._rate_limit()` calls inside async methods with `await self._async_rate_limit()`. Trivial diff.

### Finding 5 — Several brain-resident lists grow without bound (LOW today, MEDIUM at year-scale) (LOW)

**Severity:** Low for current trade volume (482 trades), would become Medium at year-scale (~12k+ trades).

**Evidence (static review):**
- `OrganismLiveEngine._all_trades` (live_engine.py:574) — appended at line 5311, never trimmed; persisted on every brain save.
- `OrganismLiveEngine._epoch_metrics` (line 577) — never trimmed.
- `ContinuousLearner.trade_history` (line 265) — never trimmed; only `[-20:]` slicing for recent-trade reads (line 300), but full list lives in memory and on disk.
- `ContinuousLearner.state.evaluation_events`, `model_metrics`, `generation_accuracies` (lines 368, 382, 384) — never trimmed.

Compare to other buffers in the codebase that are properly bounded (`_equity_curve` capped at 100k, `DecisionTelemetryStore` deque maxlen=360, regime `_history` capped). The pattern is inconsistent.

**Recommendation (not implemented):** Apply a rotating archive for `_all_trades` (e.g., keep last N=10k in memory, archive older to `trade_history_archive_<date>.csv`). The archive prefix already exists at `brain_persistence.py:66` (`ARCHIVE_PREFIX`), but no rotation logic actually uses it.

---

## TL;DR

**The tick budget is real and routinely violated.** With p95=7.5s and p99=13s on a 10s scheduler interval, 2.7% of production ticks already exceed budget and the market-open hour runs at the budget; signal-generating ticks (the ones that actually trade) are slower still. Two ticks this week stalled for 20–33 minutes during stream reconnect because there is no `asyncio.wait_for` around the tick body. DB queries are not the bottleneck (sub-ms), but the `attributes->>'source'` predicate forces a Seq Scan that will scale poorly. Memory growth is mostly bounded, with a handful of brain-resident lists (`_all_trades`, learner `trade_history`, `evaluation_events`, `model_metrics`) that grow forever — fine today, painful at year-scale. The biggest immediate win is **adding per-stage timers in `_live_tick_inner` and a per-tick `asyncio.wait_for` watchdog** — without those we keep auditing blind.
