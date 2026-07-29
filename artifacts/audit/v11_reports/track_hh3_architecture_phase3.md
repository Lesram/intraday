# Track HH3 v11 — Architecture Phase 3

**Repo:** `/Users/marselkei/VS/intra`
**Branch:** `main` @ `3778344` (prompt referenced `rc-1.5-curated @ 3778344`; the local checkout reports `main` @ `3778344` — same SHA, branch label drift only)
**Mode:** read-only, AST + grep
**Quality bar:** 1-3 findings

---

## Section findings

### 1. `_live_tick_inner` residual size — REGRESSION vs. plan

| Snapshot | LOC | Notes |
|---|---|---|
| Pre-V8 (HH baseline) | 2,510 | the original god-method |
| Post-wave-29 expectation | < 2,510 | stage 0a extracted |
| Post-wave-40 expectation | smaller still | stages 1, 1.1, 1.2 extracted |
| **Current (3778344)** | **2,706** | **+196 LOC vs. baseline** |

`_live_tick_inner` lives at `backend/organism/live_engine.py:1772-4478`. Two stage helpers exist (`_stage_expire_cooldowns` 43 LOC at L1670, `_stage_check_entry_blockers` 50 LOC at L1720) and are correctly called at L1793/L1861. **Yet the body has GROWN by ~200 LOC since the V7 baseline of 2,510**, even after 2 stage extractions removed roughly 90 LOC of inline code. Net new inline logic added since wave-29: ~280 LOC. Sources visible in the file: M2-C EOD shadow scan + EODMomentumScanner integration, M3 inverse-ETF translation, mean-reversion build, V9 PP-5 scanner-failure tracking, V9 DD3-4 EOD pending-entry cancel, V10/V11 telemetry breadcrumbs.

`live_engine.py` total LOC is now 6,942 (V7 baseline: 6,401 → +541). The HH R-1 acceptance criterion "live_engine.py total LOC reduces by ≥ 1,500" is moving in the wrong direction.

### 2. New god-classes since V10 — none, but the existing ones got bigger

Functions > 150 LOC, full backend (filtered for non-test):

| LOC | Location | Status vs. V8/V10 |
|---|---|---|
| 2,706 | `live_engine.py:1772 _live_tick_inner` | **GREW from 2,510 (pre-V8) and ~2,200 (V10 expectation)** |
| 563 | `routes/indicators.py:159 calculate_indicator` | wave-63 partial split shipped; still > 500 |
| 541 | `live_engine.py:5347 _reconcile_fills` | **NEW** finding — was not on V8/V10 HH list, now the 3rd-largest function |
| 503 | `research/optuna_meta_research_engine.py:248 run_backtest_panel_detailed` | research code, low priority |
| 489 | `live_engine.py:922 initialize` | grew from 374 (V7) |
| 477 | `routes/orders.py:327 validate_order_pre_trade` | HH2-N-2, untouched |
| 441 | `kelly_sizer.py:175 size_positions` | HH2-N-3, +17 LOC vs. V8 baseline 424 |
| 407 | `api/lifespan.py:15 startup` | not previously flagged |
| 369 | `live_engine.py:373 __init__` | grew from 374-line baseline (effectively unchanged) |
| 360 | `ml_features.py:117 compute_ml_features` | not previously flagged |
| 334 | `integrations/alpaca_stream.py:437 _process_trade_update` | not previously flagged |

**44 functions over 150 LOC** in non-test backend. The V8 HH2 watchlist (calculate_indicator, validate_order_pre_trade, size_positions) is intact; **the most material change since V10 is that `_reconcile_fills` (541 LOC) and `live_engine.initialize` (489 LOC) deserve to be added to the watchlist** — both inside the same already-stressed module.

### 3. Import-graph coupling — unchanged

`live_engine.py` import count: **35** (V8 reported 35). No regression, no improvement. Module still pulls from organism/data/api/integrations/ml/services tiers.

### 4. Circular imports — clean

`importlib.import_module()` walk over every non-test module in `backend/`: **0 circular import errors**. Confirms the module boundary still resolves at import time.

### 5. Layer violations — present, narrow scope

`backend/api/routes/` → `backend/organism/`:

| File:line | Import |
|---|---|
| `api/routes/settings.py:130` | `from backend.organism.live_engine import LIVE_LOOKBACK, LIVE_TIMEFRAME, MAX_OPEN_POSITIONS, RETRAIN_INTERVAL, MIN_BARS, USE_STREAMING` |
| `api/routes/settings.py:206` | `from backend.organism.live_engine import LONG_ONLY` |
| `api/routes/settings.py:262` | `from backend.organism.live_engine import RETRAIN_INTERVAL` |

Routes layer reaching into organism module-level constants (governance settings GET/PUT). Wider sweep across `backend/api/` shows the same pattern only via deferred function-local imports in `routes_setup.py` (router wiring) and `lifespan.py` (composition root) — both legitimate. The `routes/settings.py` case is the lone runtime-path violation. Constants should live in `backend/organism/config.py` (or similar) and be imported by both sides.

### 6. Recommended next 3 stages for HH R-1

Per `docs/architecture/HH_R1_PIPELINE_SPLIT_PLAN.md` (wave sequence table) + verified inline LOC:

| Rank | Stage | Inline LOC (current) | Risk | Why |
|---|---|---|---|---|
| 1 | **Stage 1.3** EOD entry block + flatten orchestration | ~115 (1863-1913 entry block + 2706-2766 flatten) | MEDIUM | Two separated blocks but share `_eod_flatten_triggered` flag; pure self-state, no fan-in to other stages between them |
| 2 | **Stage 0b** stream health check + recovery | ~25 | LOW | Plan still flags as LOW; quickest win to keep momentum |
| 3 | **Stage 1.5** market scanner pass | ~45 (1915-1968) | MEDIUM | State writes only to `self._scanner_*` and `self._universe`; PP-5 failure tracking already self-contained |

Stage 4 (daily-roll + max-loss + drawdown-kill) and Stage 5 (exits, ~600 LOC) remain HIGH risk and should not be the next pick.

### 7. Stage 1.3 EOD orchestration extraction — analysis

- **Lines:** 1863-1913 (entry block, 51 LOC) + 2712-2766 (flatten orchestration, 55 LOC) = ~106 LOC of inline logic.
- **Shared state:** `_eod_flatten_triggered` (local var that bridges the two blocks across ~800 LOC of intervening code), `self._alpha_breakout_late_blocked`, `self._pending_exit`, `self._pending_entry_order_ids`, `self._exit_cooldown`, `self._tick_count`, `self._is_intraday`, `current_positions`, `result`.
- **Risk: MEDIUM-HIGH (higher than the plan's MEDIUM rating).** The local `_eod_flatten_triggered` flag is set in the entry block and consumed in the flatten block ~800 lines later. To extract cleanly the flag must be uplifted to `self._eod_flatten_triggered` (mirror of the wave-39 `entries_blocked` uplift). After uplift, two helpers can be extracted: `_stage_eod_check_window()` (returns nothing, sets `self._eod_flatten_triggered`) and `_stage_eod_flatten()` (consumes it). Behavioral test must cover: pre-15:45 (no block), 15:45-15:57 (alpha block, no flatten), 15:58-15:59 (flatten triggered), 16:00+ (window passed warning).
- **Recommended:** ship the `_eod_flatten_triggered` self-uplift as a prep wave (mirrors wave-39 prep for stages 1/1.1/1.2). Then extract in the next wave. Estimated effort: 1 hr prep + 2 hr extraction + 1 hr tests.

### 8. Test coverage — live_engine

- Total tests collected: **7,746**.
- Tests that mention `live_engine` (case-insensitive, file or test-id grep): **36**.
- Three dedicated files exist: `tests/test_organism_live_engine.py`, `tests/test_organism_engine_scenarios.py`, `tests/test_multi_tick_state.py`.
- Combined collection of those three files: **64 tests** for a 6,942-LOC module = ~1 test per 108 LOC.
- The plan's `tests/test_live_tick_stages_v8.py` file referenced in the acceptance-criteria section **does not exist**. No per-stage behavioral tests have been written for `_stage_expire_cooldowns` or `_stage_check_entry_blockers`. The plan's acceptance criterion "Each stage has ≥ 1 behavioral test" is unmet for both shipped stages.

---

## Findings (1-3, ranked)

### HH3-N-1 (HIGH) — `_live_tick_inner` is regressing, not refactoring

The headline acceptance criterion of HH R-1 ("`_live_tick_inner` < 200 LOC; `live_engine.py` total -1,500 LOC") is moving in the wrong direction. Two stage helpers were extracted (~93 LOC removed across waves 29 + 40), but ~280 LOC of new inline logic was added in the same window (M2-C EOD shadow, M3 inverse-ETF, MR build, PP-5 tracking, DD3-4 cancel, telemetry). Net: `_live_tick_inner` is now 2,706 LOC (+196 vs. the V7 2,510-LOC baseline that motivated the plan). `live_engine.py` total is 6,942 LOC (+541 vs. V7 6,401). **Recommendation:** add a CI guardrail that fails if `_live_tick_inner` LOC increases between commits unless the commit message contains a token like `[HH-R1-EXEMPT]`. Without a ratchet the plan will keep losing ground.

### HH3-N-2 (MEDIUM) — `_reconcile_fills` (541 LOC) is the new god-method-in-waiting

The V8/V10 HH watchlist is now incomplete. `_reconcile_fills` (`live_engine.py:5347`) at 541 LOC is the 3rd-largest function in the entire backend and the 2nd-largest in `live_engine.py`. It was not flagged by V8 HH2 or V10 HH2 plan-feedback. `initialize` (489 LOC at L922) has also grown into watchlist territory. Both share the same single-state-bag `self` discipline as `_live_tick_inner`, so the same extraction pattern applies. **Recommendation:** add `_reconcile_fills` and `live_engine.initialize` to the HH watchlist. Triage `_reconcile_fills` for its own pipeline-split plan analogous to HH R-1; its scope (broker fill reconciliation + brain save + position-state mirroring) suggests at least 4 sub-stages.

### HH3-N-3 (LOW) — Stage 1.3 prep wave needed before extraction; per-stage tests missing

Two follow-throughs the plan tracks but the codebase doesn't yet honor:
1. The plan rates Stage 1.3 as MEDIUM, but the EOD entry block (L1863) and flatten block (L2706) are separated by ~800 LOC and share a local `_eod_flatten_triggered` flag. Extraction is unsafe until that flag is uplifted to `self._eod_flatten_triggered` (mirror of the wave-39 `entries_blocked` uplift). Recommend a prep-only wave first.
2. The plan's per-stage acceptance criterion "behavioral test in `tests/test_live_tick_stages_v8.py`" is unmet — that file does not exist, and neither shipped stage helper (`_stage_expire_cooldowns`, `_stage_check_entry_blockers`) has a dedicated behavioral test. Future waves should not ship stage extractions without the test.

---

## Side-finding (informational, not counted)

`backend/api/routes/settings.py` (lines 130, 206, 262) imports module-level constants directly from `backend.organism.live_engine` (LIVE_LOOKBACK, LIVE_TIMEFRAME, MAX_OPEN_POSITIONS, RETRAIN_INTERVAL, MIN_BARS, USE_STREAMING, LONG_ONLY). This is the only runtime layer violation routes→organism in the API surface (the others in `routes_setup.py` / `lifespan.py` are composition-root wiring). Low-risk cleanup: move these constants to `backend/organism/config.py` and import from both sides. Out of scope for HH3 quality bar but worth tracking for AA4 / structural follow-up.
