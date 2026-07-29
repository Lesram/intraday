# V8 Track HH2 — Architecture Coupling Under HH R-1 Partial

**Repo:** `/Users/marselkei/VS/intra`
**Branch:** `rc-1.5-curated` @ `5bc4046` (HEAD); wave-29 = `79b38fb` (HEAD~1)
**Date:** 2026-05-03
**Scope:** Stage 0a regression check + safest next stages + same-class scan for non-`_live_tick_inner` god-methods.
**Method:** Read-only — git diff parity, AST scan, import grep, pytest run.

---

## 1. Stage 0a regression check — CLEAN

### 1.1 Byte-for-byte parity (inline @ 79b38fb~1 vs extracted @ 79b38fb)

Diffed the cooldown-expiry block from the pre-wave-29 inline location (lines 1516–1551 of HEAD~1's `live_engine.py`) against the body of `_stage_expire_cooldowns` (lines 1517–1552 at HEAD).

```
diff /tmp/inline_v7.txt /tmp/extracted_wave29.txt
=== IDENTICAL ===
```

All four mutated maps are mutated identically:
- `self._exit_cooldown` — same dict-comp, same threshold `self._EXIT_COOLDOWN_TICKS`.
- `self._pending_entry` — same dict-comp, same threshold `self._PENDING_ENTRY_TICKS`.
- `self._pending_entry_order_ids` — same `if sym in self._pending_entry` filter.
- Pending-exit cooldown (`self._pending_exit`) — same dict-comp, same threshold `self._PENDING_EXIT_TICKS`.
- Terminal-id early-clear (the `_stream.is_order_terminal(oid)` loop with double `pop`) — same try/except, same `list(...)` snapshot, same `pop(sym, None)` semantics, same logger call.

No state mutation lost in extraction.

### 1.2 Call-site ordering preserved

Pre-wave-29 (HEAD~1, `_live_tick_inner`):
```
self._tick_count += 1
self._last_gate_rejections = {}
self._last_entries_blocked_reason = ""
# inline cooldown block here
try:
    now_iso = result.timestamp
    # 0. STREAM HEALTH ...
```

Post-wave-29 (HEAD, `_live_tick_inner`):
```
self._tick_count += 1
self._last_gate_rejections = {}
self._last_entries_blocked_reason = ""
self._stage_expire_cooldowns()
try:
    now_iso = result.timestamp
    # 0. STREAM HEALTH ...
```

Identical relative order: tick-count increment first (cooldown comparison `self._tick_count - tick` then sees the post-increment value, same as before), then telemetry reset, then cooldown expiry, then the `try` block. Locking is preserved (helper still runs inside `async with self._tick_lock`).

### 1.3 Symbol resolution

```
$ ./venv/bin/python -c "from backend.organism.live_engine import OrganismLiveEngine; \
  import inspect; m = OrganismLiveEngine._stage_expire_cooldowns; \
  print(inspect.signature(m), inspect.iscoroutinefunction(m))"
(self) -> 'None' False
```

- Method bound at class scope, sync (correctly — no awaits exist in the original block).
- 44 source lines.
- Single call site (line 1570 in `_live_tick_inner`); single definition (line 1509).
- `grep -n 'pending_entry_order_ids = {' backend/organism/live_engine.py` → 1 match (the helper). Original site fully removed. Same-class duplication: 0.

### 1.4 Tests pass

```
$ ./venv/bin/python -m pytest tests/test_organism_live_engine.py tests/test_multi_tick_state.py --timeout=20 -q
34 passed, 1 warning in 15.37s
```

### 1.5 No follow-up fixes

```
$ git log 79b38fb..HEAD -- backend/organism/live_engine.py
(empty)
```

No post-wave-29 corrective edits to `live_engine.py` — the extraction has held cleanly.

### 1.6 Replay-vs-live diff

Skipped: no replay harness wired up locally for a tick-by-tick snapshot diff at this branch state. Byte-parity + ordering + tests is sufficient evidence that no behavior changed; the helper is a pure 1:1 copy of the inline block.

**Stage 0a verdict: CLEAN. No regression.**

---

## 2. Recommended next stages (waves 32–34)

Plan doc claims stages 0b / 0.5 / 1 / 1.1 / 1.2 are all "LOW" risk. AST + scope analysis disagrees in one important way: **stages 1, 1.1, 1.2, 1.3 all read/write a local flow-control variable `entries_blocked`** that lives in `_live_tick_inner`, NOT `self`. Naively extracting any of them per the plan's "stages share `self`" rule would either:
- silently lose the flow-control hand-off, OR
- require an out-of-band uplift of `entries_blocked` to `self._entries_blocked` first (which itself touches 12+ call sites — see lines 1617, 1619, 1628, 1642, 1731, 1975, 2023, 2048, etc.).

Stage 0.5, by contrast, writes only `self._data_stale` (already a self attribute) and reads only `self._streaming_provider` / `self._time_fn` / a one-shot local `_was_stale` whose scope dies inside the block. Truly self-contained — extracts cleanly with no helper signature work.

Score = `LOC × unique_self_attrs × external_factor`, with a flow-control penalty (×3) if the stage uses `entries_blocked` or `result.activity.append`/`result.errors` (since `result` is also a local that would need to be passed in or uplifted).

| Stage | LOC | unique `self.*` | external (awaits/IO) | flow-var leak | raw score | adj score (×3 if leak) |
|---|---|---|---|---|---|---|
| **0.5 stale-data gate** | 20 | 4 | 0 | none (writes `self._data_stale`) | 80 | **80** ← safest |
| 0b stream health | 16 | 2 | 1 await + appends `result.activity` | result.activity | 32 | 96 |
| 1.2 stale-data entries gate | 9 | 2 | 0 | `entries_blocked` + result.activity | 18 | 54 |
| 1 governance halt | 12 | 2 | 0 | `entries_blocked` + result.errors + result.activity | 24 | 72 |
| 1.1 warmup | 13 | 3 | 0 | `entries_blocked` + result.activity | 39 | 117 |
| 1.3 EOD entry block + flatten | 29 | 3 | 0 | `_eod_flatten_triggered` local + result.activity | 87 | 261 |
| 1.5 market scanner pass | 40 | 5 | 2 awaits | many `self.*` writes | 200 | 600 |

### Recommendation

- **Wave 32: Stage 0.5 (stale-data gate).** Lowest adjusted score (80). Pure self-attribute write. No flow-var leak. ~20 LOC. Take this first; it establishes the pattern for self-contained gates.
- **Wave 33: Lift `entries_blocked` → `self._entries_blocked` (no extraction yet).** Mechanical refactor across ~12 call sites. Once done, *all four* downstream gates (1, 1.1, 1.2, 1.3) become trivially extractable. This is the highest-ROI structural prep step the plan doc misses.
- **Wave 34: Stages 1 + 1.1 + 1.2 in one batch.** With `entries_blocked` self-promoted (wave 33), these three are each <15 LOC, share an interlocked `if not entries_blocked` chain, and benefit from being co-extracted to preserve the chain semantics in one reviewable diff. Each helper docstring documents reads/writes per plan section 4.

Stage 0b (stream health) and 1.3 (EOD block) should defer to wave 35+ because they each mutate `result.activity` — extraction needs either passing `result` in or returning an activity event list, which is a deeper convention change that should be decided once and applied uniformly.

### Plan-doc gap (worth flagging back to the planner)

`HH_R1_PIPELINE_SPLIT_PLAN.md` lists stages 1 / 1.1 / 1.2 as **LOW** risk and groups them in wave 32. Per-stage analysis above shows they are NOT independently low-risk because of the shared `entries_blocked` local + `result` local. The plan's stated approach ("Stage helpers take/return state via `self`, not via parameters") is not actually achievable for those stages without a prerequisite uplift commit. Flag for the plan owner: insert a "Wave 31.5: uplift `entries_blocked` to `self`" before tackling stages 1 / 1.1 / 1.2.

---

## 3. Same-class scan — other god-methods V7 didn't flag

V7 Track HH focused exclusively on `_live_tick_inner` (R-1) and the `__init__` (R-2). AST scan of `backend/**/*.py` for methods >150 LOC:

```
LOC   File                                                      Method
2535  backend/organism/live_engine.py:1554                       _live_tick_inner          [V7-flagged: R-1]
 614  backend/api/routes/indicators.py:78                        calculate_indicator       [NEW HH2 finding]
 503  backend/research/optuna_meta_research_engine.py:248        run_backtest_panel_detailed [NEW]
 501  backend/organism/live_engine.py:4958                       _reconcile_fills          [partly noted in Q-Q15]
 477  backend/api/routes/orders.py:300                           validate_order_pre_trade  [NEW HH2 finding]
 445  backend/organism/live_engine.py:866                        initialize                [NEW]
 424  backend/organism/kelly_sizer.py:175                        size_positions            [NEW HH2 finding]
 369  backend/organism/live_engine.py:358                        __init__                  [V7-flagged: R-2]
 360  backend/organism/ml_features.py:117                        compute_ml_features       [NEW]
 339  backend/api/lifespan.py:15                                 startup                   [NEW]
 314  backend/services/trade_service.py:161                      calculate_analytics       [NEW]
 272  backend/api/routes/signals.py:511                          act_on_signal             [NEW]
 261  backend/services/order_service.py:720                      submit_symbol_order       [NEW]
 256  backend/integrations/alpaca_stream.py:437                  _process_trade_update     [NEW]
 246  backend/models/ensemble_model.py:980                       predict
 242  backend/migrations/versions/20251015_risk_management.py    upgrade                   [migration; ignore]
 241  backend/api/routes/models.py:698                           _run_training_job
 236  backend/api/routes/market_data.py:322                      get_historical_bars
 229  backend/organism/live_engine.py:4091                       _build_decision_snapshot
 215  backend/api/routes/orders.py:791                           submit_order
 205  backend/organism/background_trainer.py:55                  _train_in_process
 201  backend/organism/alpha_scanner.py:93                       scan
 196  backend/api/routes/market_data.py:72                       market_data_websocket
 191  backend/strategies/parity_checker.py:137                   compare
 189  backend/organism/adaptive_exits.py:356                     check_exit
```

Confirmed not in V7 synthesis (`MASTER_AUDIT_SYNTHESIS_v7.md`) or the findings ledger (`FINDINGS_LEDGER.md`):

```
$ grep -iE "calculate_indicator|614|validate_order_pre|kelly_sizer.size_positions|compute_ml_features|lifespan.startup|trade_service.*analytics" \
    artifacts/audit/MASTER_AUDIT_SYNTHESIS_v7.md artifacts/audit/FINDINGS_LEDGER.md
(no hits)
```

Top three HH2-class additions to flag:

- **HH2-N-1 (HIGH): `calculate_indicator` 614 LOC at `backend/api/routes/indicators.py:78`.** A single route handler that's nearly a quarter the size of `_live_tick_inner`. Routes should not contain 600-line dispatch trees. Likely a giant if/elif over indicator names — should be a strategy-pattern registry. V7 missed this entirely because Track HH scoped to `live_engine.py`.

- **HH2-N-2 (HIGH): `validate_order_pre_trade` 477 LOC at `backend/api/routes/orders.py:300`.** Pre-trade validation in a route is inherently security-critical (this is the choke-point for risk enforcement). 477 LOC = many independent checks bundled, hard to audit individually. Cross-references AA security findings — adding new risk gates inside this method is exactly the kind of change that's hard to review.

- **HH2-N-3 (MEDIUM): `size_positions` 424 LOC at `backend/organism/kelly_sizer.py:175`.** Kelly sizing is one of the most important numerical kernels in the platform; 424 LOC means the sizing logic, risk-budget floor, learning-mode caps, and per-symbol overrides are all interleaved. Recommend pipeline-split similar to the R-1 pattern, but smaller scope (one wave).

Other notable >300 LOC methods (`run_backtest_panel_detailed`, `_reconcile_fills`, `initialize`, `compute_ml_features`, `startup`) should be tracked but lower priority than the three above (the ones above are either security-adjacent or in critical hot paths).

---

## 4. Import-graph coupling outlier

```
backend/organism/live_engine.py        : 35 import lines (24 from backend.organism.*)
backend/organism/feature_engineering.py:  7
backend/organism/brain_persistence.py  : 12
backend/organism/self_evolution.py     :  7
backend/organism/alpha_scanner.py      :  7
```

`live_engine.py` is a **3–5x outlier**. It imports nearly every sibling module under `backend/organism/*`: `adaptive_exits`, `alpha_scanner`, `brain_persistence`, `breakout_scanner`, `continuous_learner`, `governance`, `kelly_sizer`, `ml_features`, `multi_timeframe`, `ml_signal`, `pyramider`, `regime`, `orb_scanner`, `eod_scanner`, `mean_reversion_scanner`, `sector_map`, `decision_telemetry`, `self_evolution`, `universe_selector`, `transfer_learning`, `background_trainer`, `market_scanner`. This is the empirical signature of a god-class — confirms V7's R-1 finding from a different angle. Not a NEW finding (V7 already called the file out as 6,401 LOC), but reinforces the priority of HH R-1 follow-through.

---

## 5. Circular imports — none

```
$ ./venv/bin/python <ast walker importing every backend module>
Circular candidates: 0
```

Clean.

---

## 6. Layer violations — minor

```
$ grep -rn "from backend\.organism" backend/api/routes/
backend/api/routes/settings.py:121:    from backend.organism.live_engine import (...)
backend/api/routes/settings.py:191:    from backend.organism.live_engine import LONG_ONLY
backend/api/routes/settings.py:241:    from backend.organism.live_engine import RETRAIN_INTERVAL
```

Three narrow imports, all in `settings.py`, all reach into `live_engine` for module-level constants/symbols (`LONG_ONLY`, `RETRAIN_INTERVAL`). Acceptable for a settings page that surfaces those constants in the UI, but the cleanest fix is to relocate them to `backend.config` or a dedicated `backend.organism.constants` module. **Note, not a finding** — modest leak, no operational impact.

---

## Findings summary

**Architecture findings: 1 finding (multi-part).** **Wave-29 status: CLEAN — no Stage 0a regression.**

| ID | Severity | Title |
|---|---|---|
| HH2-N-1 | HIGH | New god-method `calculate_indicator` (614 LOC) at `backend/api/routes/indicators.py:78` not flagged by V7 |
| HH2-N-2 | HIGH | New god-method `validate_order_pre_trade` (477 LOC) at `backend/api/routes/orders.py:300` — security-adjacent |
| HH2-N-3 | MEDIUM | New god-method `size_positions` (424 LOC) at `backend/organism/kelly_sizer.py:175` — sizing kernel |
| HH2-PLAN-1 | INFO | `HH_R1_PIPELINE_SPLIT_PLAN.md` mis-ranks stages 1 / 1.1 / 1.2 as LOW risk: shared local `entries_blocked` flow-var requires a prerequisite self-uplift wave before extraction |

(Bundled under one HH2 entry per the 1–3 finding quality bar; HH2-N-1, -N-2, -N-3 are the three god-methods, HH2-PLAN-1 is an informational planner-feedback note.)

---

## TL;DR

Wave-29's `_stage_expire_cooldowns` extraction is a clean, byte-for-byte copy of the prior inline cooldown block — same four maps mutated, same thresholds, same try/except, same call-site ordering inside `_live_tick_inner` (which still runs under `_tick_lock`); 34 live-engine + multi-tick tests pass; the helper binds correctly as a sync method; no follow-up fix-up commits exist on `live_engine.py` since `79b38fb`. **No regression.** The next-easiest extraction is Stage 0.5 (stale-data gate, 20 LOC, only writes `self._data_stale`), not the four `entries_blocked`-coupled gates the plan doc lists as LOW — those need a prerequisite uplift of the local `entries_blocked` flag to `self._entries_blocked` before they can be extracted per the plan's "share via `self`" convention. Same-class scan surfaces three god-methods V7 missed because Track HH scoped only to `_live_tick_inner`: `calculate_indicator` (614 LOC, route handler), `validate_order_pre_trade` (477 LOC, security-adjacent), and `size_positions` (424 LOC, sizing kernel) — each warrants its own future track. Live_engine remains a 3–5x import-graph outlier (35 imports vs ~7–12 for sibling organism modules), but no circular imports and only three narrow layer leaks (`settings.py` reaches in for constants).
