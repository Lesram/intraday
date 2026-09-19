# Track U v5 — Replay-Live Divergence

The platform supports replay (backtesting) and live trading from a single
codebase. Divergence between the two breaks backtest validity AND obscures
production bugs. V4 R-F-4 caught one bypass site (`live_engine.py:1999`
uses `datetime.now(UTC)` directly instead of `self._now_fn()`); this
track does a systematic sweep.

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `d43dbec`.

## Files in scope

Anything reachable from a tick:
- `backend/organism/scheduler.py`
- `backend/organism/live_engine.py`
- `backend/organism/replay_simulator.py`
- `backend/organism/regime.py`, `kelly_sizer.py`, `adaptive_exits.py`,
  `mean_reversion.py`, `ensemble_models.py`, `ml_features.py`,
  `ml_signal.py`, `signal_generator.py`, `continuous_learner.py`,
  `self_evolution.py`
- `backend/data/alpaca_client.py`, `streaming_data_provider.py`
- `backend/utils/market_hours.py`
- `backend/services/cache.py`

## Method

### Phase 1 — Time-source bypass audit

Find every `datetime.now`, `datetime.utcnow`, `time.time`, `time.monotonic`,
`pd.Timestamp(`, `pd.Timestamp.now` in scope. For each:
- Is it called via `self._now_fn()` / `self._time_fn()` / canonical helper?
- If direct: would replay see the wall clock instead of the replay clock?
- If `time.monotonic()`: replay-mode safe (monotonic intervals usually OK
  but not always — e.g. cooldown timers must align to replay's clock).
- Tag each as: routed-through-now-fn / direct-bypass / canonical-helper-OK

Build a table; this *is* the deliverable for Phase 1.

### Phase 2 — Random / non-deterministic source audit

Find every `random.*`, `numpy.random.*`, `uuid.uuid4()`, hash-based
selection. For each:
- Replay determinism requirement?
- Seed control mechanism? (env var, fixture)
- If non-deterministic by design (e.g. idempotency keys): is replay
  fixturing them?

### Phase 3 — External-state bypass audit

Find every direct read of state that should be parameterized for replay:
- Broker account.equity: replay reads from synthetic equity?
- Quote cache lookup: replay uses synthetic / fixture quotes?
- Streaming staleness check: replay marks all symbols fresh?
- DB queries that must be replay-faked (e.g. orphan-adoption from
  `position_lots` — does replay seed an empty / fixture lot table)?

### Phase 4 — End-to-end trace

Pick ONE bar from a recent live session (use any closed bar from
`organism_brain/trade_history.csv`'s last week). For that bar:

1. **Live path**: trace through `live_tick._live_tick_inner` from start of
   tick to first decision (build the tick state diagram). Note every
   external read.
2. **Replay path**: trace the equivalent path in `replay_simulator.py`'s
   step / on_bar function. Diff the read sites.

Surface every divergence — read sites that exist in live but not in replay
(or vice versa) are bypass candidates.

### Phase 5 — Replay vs live state diff

Run a synthetic replay through `replay_simulator` for one symbol on one
recent bar; capture state at end of tick. Compare against equivalent
fields in `manifest.json` / `learning_state.json` from the same time.
Differences point to either:
- Genuinely path-dependent state (acceptable, document)
- Bypass sites (bug, file as finding)

This phase is exploratory — outcome depends on what the trace surfaces.

### Phase 6 — Audit the `_now_fn` / `_time_fn` injection coverage

`OrganismLiveEngine` accepts `_now_fn` and `_time_fn` constructor params
(replay injection). Build a list of every component that has these injected
and every component that does NOT:
- Components missing injection are guaranteed-bypass sites for replay.
- Components with injection but with internal `datetime.now()` calls are
  bug candidates.

## Output

`artifacts/audit/v5_reports/track_u_replay_live_divergence.md` with:

- Phase 1: time-source inventory table (file:line × call × routed?)
- Phase 2: random-source inventory + seed control verdict
- Phase 3: external-state bypass list
- Phase 4: live-vs-replay trace diff
- Phase 5: state-diff outcome (if performed)
- Phase 6: `_now_fn` injection coverage map
- "Bypass sites: N (exact file:line each)" + TL;DR

## Constraints

Read-only on production. Synthetic replay via `./venv/bin/python` /
`replay_simulator.py` ok. NO changes to live engine.

## Quality bar

Every direct `datetime.now()` / `time.time()` in a tick-reachable file is
a candidate. R-F-4 already found one. Expect 3-7 more. If 0-1: search
wasn't thorough enough.

This track has the highest chance of producing organism-level findings
since divergence is a property of the WHOLE system, not any single module.

End with a one-paragraph summary: bypass sites found, most divergence-
inducing one, recommended fix path.
