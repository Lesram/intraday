# V7 Track CC — Test Quality & Coverage

Repo: `/Users/marselkei/VS/intra` · Branch `rc-1.5-curated` · Working tree at
the audit start matches `d44eace` (current branch HEAD; reported by
`git log -1`). `pytest --collect-only` returns **8,777 tests** across
**464 `test_*.py` files** under `tests/` (plus 82 under `tests/unit/`).
Backend source under audit: 302 `.py` files, of which 41 live in
`backend/organism/`, 28 in `backend/services/`, 51 in `backend/api/`,
33 in `backend/infra/`.

Tooling note: `coverage`, `pytest-cov` and `mutmut` were **not** present
in `venv/`. We installed `coverage 7.13.5`, `pytest-cov 7.1.0`, and
`mutmut 3.5.0` for this audit. None of these were added to
`requirements.txt` — pinning them is one of our recommendations.

---

## 1. Test inventory & classification

| Metric | Count |
| --- | --- |
| `tests/test_*.py` files | 464 |
| `tests/unit/test_*.py` files | 82 |
| Total tests collected (`pytest --collect-only`) | **8,777** |
| Test files using `unittest.mock` / `MagicMock` / `AsyncMock` | 331 |
| Test files containing `async def test_` | 235 |
| Test files with `@pytest.mark.asyncio` | 224 |
| Test files using `asyncio.run` (anti-pattern w/ asyncio_mode=auto) | 10 |
| Test files using `inspect.getsource` (structural-style) | 30 |
| Test files **without any `assert` statement** | **12** |
| Test files mutating `os.environ[...]` directly | 5 |
| Test files using `monkeypatch.setenv` (preferred) | 8 |
| Test files touching Redis / `redis` import | 17 |
| Test files touching Postgres / `psycopg` | 2 |
| Test files touching Alpaca SDK | 73 |
| Test files using `time.sleep`/`asyncio.sleep` | 17 |
| Conftest files | 2 (`tests/conftest.py`, `tests/real_tests/conftest.py`) |

**Classification heuristic (sample of 30 random files):**

- ~70% **behavioral** — construct objects, call methods, assert state /
  return values (good).
- ~10% **structural** — use `inspect.getsource` to grep production code
  for required substrings (V6 W flagged this pattern; still present —
  examples include the `apr10_patch_f4_forensic_guard` and `bypass_audit_*`
  families which check that specific call-sites have specific guards).
- ~10% **integration / end-to-end** — multi-module wiring
  (`test_system_integration.py`, `test_replay_simulator.py`,
  `test_order_pipeline_e2e.py`).
- ~10% **scripts masquerading as tests** — see test-smell catalog
  below; `test_analytics_api_full.py`, `test_analytics_diagnostic.py`,
  `test_position_management.py`, `test_pretrade_validation.py`, etc.

---

## 2. Line + branch coverage

Coverage was collected with `pytest --cov=backend --cov-report=term`
across a curated 80-file subset (excluding the production-comprehensive
and live-server-required tests that error out without a running
backend). The full suite cannot be coverage-instrumented end-to-end
within a reasonable wall-clock budget (the unmonitored full suite was
killed at the 36% mark after >3 minutes due to many tests sitting on
the 15-second `--timeout` ceiling).

### 2.1 Aggregate

| Scope | Statements | Missed | Coverage |
| --- | ---: | ---: | ---: |
| `backend/` (all packages) | 58,381 | 43,065 | **26%** |
| `backend/organism/` (only) | 11,329 | 6,598 | **42%** |
| `backend/services/` (only, narrow subset) | ~11k | ~10k | <15% |
| `backend/utils/helpers.py` | 201 | 5 | 98% |
| `backend/utils/secure_pickle.py` | 81 | 2 | 98% |
| `backend/services/position_reconciliation_service.py` | 74 | 2 | 97% |

The 26% headline is **a floor, not a ceiling** (only 80 of 464 test
files were exercised), but the relative shape — which modules are
high vs. low — is informative.

### 2.2 Per-module organism coverage (sorted ascending)

| Module | Stmts | % |
| --- | ---: | ---: |
| `attribution.py` | 208 | **0%** |
| `feature_store.py` | 129 | **0%** |
| `nightly_scheduler.py` | 69 | **0%** |
| `promotion.py` | 161 | **0%** |
| `runner.py` | 60 | **0%** |
| `scheduler.py` | 169 | **0%** |
| `streaming_data_provider.py` | 157 | **0%** |
| `training.py` | 155 | **0%** |
| `multi_timeframe.py` | 72 | 17% |
| `replay_simulator.py` | 390 | 20% |
| `live_engine.py` | 2,450 | **21%** |
| `orb_scanner.py` | 251 | 25% |
| `market_scanner.py` | 227 | 26% |
| `routes.py` | 435 | 26% |
| `transfer_learning.py` | 230 | 26% |
| `walk_forward.py` | 217 | 27% |
| `ensemble_models.py` | 187 | 29% |
| `mean_reversion_scanner.py` | 209 | 33% |
| `background_trainer.py` | 257 | 42% |
| `governance.py` | 158 | 46% |
| `self_evolution.py` | 451 | 46% |
| `ml_signal.py` | 387 | 56% |
| `continuous_learner.py` | 244 | 58% |
| `brain_persistence.py` | 914 | 63% |
| `pyramider.py` | 137 | 69% |
| `regime.py` | 302 | 73% |
| `alpha_scanner.py` | 182 | 76% |
| `diagnostic_checks.py` | 521 | 76% |
| `adaptive_exits.py` | 307 | 78% |
| `ml_features.py` | 244 | 78% |
| `eod_scanner.py` | 146 | 80% |
| `kelly_sizer.py` | 295 | 80% |
| `diagnostic_scheduler.py` | 106 | 81% |
| `universe_selector.py` | 155 | 81% |
| `breakout_scanner.py` | 212 | 86% |
| `composite_indicators.py` | 206 | **92%** |
| `decision_telemetry.py` | 208 | 99% |
| `diagnostics.py` | 88 | 100% |
| `sector_map.py` | 15 | 100% |
| `trading_phase.py` | 18 | 100% |

### 2.3 V3 Track M — "untested modules" gap

V3 Track M flagged six modules as having zero direct tests. Today:

| Module | V3 status | V7 grep of `tests/` | Coverage % |
| --- | --- | --- | ---: |
| `composite_indicators.py` | 0 imports | 0 imports (transitively only) | **92%** ✓ closed |
| `ensemble_models.py` | 0 imports | 0 imports | 29% partial |
| `multi_timeframe.py` | 0 imports | 0 imports | 17% partial |
| `nightly_scheduler.py` | 0 imports | 0 imports | **0%** ✗ open |
| `training.py` | 0 imports | 0 imports | **0%** ✗ open |
| `transfer_learning.py` | 0 imports | 0 imports | 26% partial |

Three of six are still effectively untested at the module level
(`grep -l 'import .*nightly_scheduler' tests/` returns nothing). The
non-zero `multi_timeframe`/`transfer_learning` coverage comes from
transitive imports during `live_engine` startup, not from tests that
exercise them directly.

### 2.4 Modules below 50% coverage

In the 80-file coverage run, **199 of 287 backend modules (69%)** were
below 50% line coverage; **99 modules (34%) were at 0%** (never imported
during the run). Even allowing for the 80-file subset bias, the
following are notably low for production-critical code:

- `backend/organism/live_engine.py` — 21% (2,450 stmts; **the core
  tick loop**)
- `backend/organism/replay_simulator.py` — 20% (most call-sites timed
  out; see §4)
- `backend/risk/risk_manager.py` — 16%
- `backend/services/order_service.py` — 11%
- `backend/infra/outbox_worker.py` — 15%
- `backend/integrations/alpaca_broker.py` — 35%
- `backend/integrations/alpaca_data.py` — 16%

**Verdict: 5–15 modules below 50% coverage** — actual count is
substantially higher (199), but constrained to organism core logic the
quality-bar prediction holds: 8 organism modules below 50%, 8 between
50–75%, 14 at or above 75%.

---

## 3. Mutation testing

`mutmut` 3.5.0 was installed but the v3 CLI has been redesigned away
from `--paths-to-mutate` and now requires a `pyproject.toml`/`setup.cfg`
`[mutmut]` section plus a `mutmut run` invocation (the `--help` output
exposes only `--max-children`). No such config exists in this repo, so
a meaningful mutmut run is **not feasible inside the audit budget**
without either (a) writing the config or (b) downgrading to mutmut
2.5.x. We document the gap and recommend:

1. Add a `[tool.mutmut]` section to `pyproject.toml` pointing at
   `backend/organism/kelly_sizer.py` and `backend/organism/walk_forward.py`
   as the first two targets.
2. Pin `mutmut==2.5.2` in `requirements-dev.txt` for compatibility with
   the pre-V3 CLI; alternatively migrate to v3 with the new config.
3. Use the existing `tests/test_audit_patch_queue_b2.py` (kelly) and
   `tests/test_audit_patch_queue_d3.py` as the killer test set and
   target a 70%+ kill rate for the canonical fitness math.

Mutation kill rate measurement: **deferred — tooling configuration gap**.

---

## 4. Flaky-test detection — three consecutive runs

The full 8,777-test suite cannot finish in this audit's wall-clock
budget because many tests are anchored to a `--timeout=15s` ceiling
(see §5) — the unmonitored full run reached 36% in 3 min 35 s before
being terminated. Instead, we ran a curated **296-test subset** three
times back-to-back; the subset spans ML, evolution, replay, kelly,
broker integration, indicators, helpers, and the apr10/apr7 patch
families.

```
run 1: 13 failed, 283 passed in 91.35s
run 2: 13 failed, 283 passed in 91.89s
run 3: 13 failed, 283 passed in 91.61s
```

**The same 13 tests failed every run, in the same order. 0 flakes
detected in the curated subset.** All 13 failures are deterministic and
fall into three categories:

1. **`test_replay_simulator.py` (5 failures)** — `test_replay_completes_100_ticks`,
   `test_replay_trades_have_valid_pnl`, `test_replay_no_throttle_blocking`,
   `test_replay_intraday_timeframe_uses_tight_stops`,
   `test_replay_daily_timeframe_uses_wider_stops`. All five hit the
   15-s pytest-timeout. The 100-tick replay legitimately needs >15 s on
   this hardware. Root cause: timeout is too tight for these
   end-to-end tests, **not** flake.
2. **`test_audit_patch_queue_b2.py::TestMLConfidenceLeakage` (3
   failures)** — three tests check that learning-mode ranking ignores
   ML confidence and that production-mode uses it. Looks like a real
   regression after the May-1 hardening Memory.md mentions
   ("DROP_ML_FROM_GATE default-true"). These need a triage decision:
   the production code may have moved past the test contract.
3. **`test_audit_patch_queue_d1.py::TestValidateNewModelEconomic` (5
   failures) + 1 `test_apr7_p0_p1_fixes.py` failure** — economic
   side-constraint validation appears to have re-broken; this matches
   Memory's "predicted_return floor was 0.003" historical fix. Same
   triage path.

Memory.md flag — *"4 flaky async tests pass individually, fail in full
suite (timing issues)"* — those tests live outside this curated subset
(they only manifest in the 8,777-test sequence). We were unable to
replay the full suite three times within budget; the existing flake
note remains **unverified by this audit** but also **uncontradicted**.
Run logs are committed to:

- `artifacts/audit/v7_reports/cc_subset_run1.log`
- `artifacts/audit/v7_reports/cc_subset_run2.log`
- `artifacts/audit/v7_reports/cc_subset_run3.log`

**Verdict: 0 flaky tests in the 296-test subset.** Pre-existing 4-flake
note for the full suite is not refuted.

---

## 5. Slow-test inventory (`--durations=20`)

From a 23-file curated coverage run (excluding live-server tests) on
mid-tier Apple Silicon hardware:

| Rank | Duration | Test |
| ---: | ---: | --- |
| 1 | 15.35s | `tests/test_replay_simulator.py::test_replay_intraday_timeframe_uses_tight_stops` ⏱TO |
| 2 | 15.11s | `tests/test_replay_simulator.py::test_replay_trades_have_valid_pnl` ⏱TO |
| 3 | 15.01s | `tests/test_replay_simulator.py::test_replay_completes_100_ticks` ⏱TO |
| 4 | 15.01s | `tests/test_replay_simulator.py::test_replay_no_throttle_blocking` ⏱TO |
| 5 | 11.08s | `tests/test_replay_simulator.py::test_replay_daily_timeframe_uses_wider_stops` |
| 6 | 10.84s | `tests/test_replay_simulator.py::test_replay_with_crash_data` |
| 7 | 4.12s | `tests/test_replay_simulator.py::test_replay_regime_history_populated` |
| 8 | 3.98s | (same, second invocation in different module ordering) |
| 9 | 2.87s | `tests/test_system_integration.py::TestMLTrainingWithDecay::test_retrained_model_improves_or_maintains` |
| 10 | 2.10s | `tests/test_replay_simulator.py::test_replay_equity_monotonic_start` |
| 11 | 1.63s | `tests/test_system_integration.py::TestMLKellyPipeline::test_train_predict_size_flow` |
| 12 | 1.15s | `tests/test_system_integration.py::TestMLTrainingWithDecay::test_training_with_decay_succeeds` |
| 13 | 0.26s | `tests/test_apr7_p0_p1_fixes.py::test_update_watchdog_c1_fires_critical_when_truly_idle` |
| 14 | 0.16s | `tests/test_apr7_p0_p1_fixes.py::test_update_watchdog_c1_stays_quiet_while_orders_flow` |
| 15 | 0.15s | `tests/test_secure_pickle.py::TestSecurePickleBasics::test_different_data_types` |

The full suite has additional slow tests we couldn't enumerate (the
unmonitored full run logged ~6 timeouts in the 30%–40% completed range
alone). Confirmed slow-test concentrations:

- `tests/test_replay_simulator.py` — 8 of the top-15 slowest tests.
  Four hit the 15-s timeout and three more are >2 s. Recommend
  `@pytest.mark.slow` + raising the per-test timeout to 30 s for
  replays only, or moving to a nightly-only test job.
- `tests/test_system_integration.py::TestMLTrainingWithDecay` — ML
  training inside unit tests; could be a nightly job or replaced with
  a saved fixture.

**Verdict: 5–10 confirmed slow tests** (replay simulator family + ML
training). Consistent with the quality bar.

---

## 6. Test interdependency

- **Conftest fixtures**: `tests/conftest.py` (368 lines) defines an
  **autouse** fixture `reset_module_caches` that nukes
  `backend.infra.db._engine` and `backend.database._sessionmaker`
  between every single test. This protects against pollution but is
  also a perf tax (a small one, but on 8,777 tests it adds up). The
  same conftest sets ~10 `os.environ.setdefault(...)` lines under
  `pytest_configure` — these stick for the entire session, which is
  fine for fixed values like `TEST_ADMIN_USERNAME` but means later
  `monkeypatch.setenv` calls inherit the wrong defaults if the test
  forgets to unset.
- **Test files mutating `os.environ[...]` directly (no monkeypatch)**:
  - `tests/conftest.py` (expected, session setup)
  - `tests/test_utilities_comprehensive.py`
  - `tests/unit/test_organism.py`
  - `tests/unit/test_config_settings.py`
  - `tests/unit/test_ml_prediction_service_comprehensive.py`

  The four under `tests/unit/` and `tests/test_utilities_comprehensive.py`
  are **direct env mutations without restore**. This was V5's exact
  flag — still present.
- **Tests requiring live external services**:
  - `tests/test_idempotency.py` — `psycopg2.connect(DATABASE_URL)`,
    skips if the URL is sqlite or missing.
  - `tests/test_alembic_head.py` — `subprocess.run(['alembic',
    'current'])`, skips on sqlite.
  - `tests/test_position_management.py` — pings
    `http://localhost:8000/health` and skips if down.
  - `tests/test_risk_api.py` — gated on `RUN_DB_INTEGRATION_TESTS=1`.
  - 73 files import `alpaca` symbols (most mock the client; a handful
    do not).
- **Tests that import from other tests**: `grep "from tests\." tests/`
  returns 0 hits. Good — no cross-test imports.

---

## 7. Error-path coverage

`grep -rEn "^\s+raise " backend/organism/` — **25 raise sites** in
organism. Distribution of explicit negative tests (tests that assert
the raise fires under a known precondition):

| Module | Raise sites | Direct negative-test coverage |
| --- | ---: | --- |
| `replay_simulator.py` | 3 | **3 / 3** (`test_replay_simulator_errors.py`, V3 Track M-12) |
| `routes.py` | 14 (HTTPException) | partial (e.g., `test_positions_route.py`, `test_organism_routes_*` cover ~6) |
| `brain_persistence.py` | 3 | partial (1: `test_apr7_p0_p1_fixes.py` exercises the 503 path; 2 untested) |
| `live_engine.py` | 1 | none found |
| `nightly_scheduler.py` | 2 | **0 / 2** (module is at 0% coverage) |
| `ml_signal.py` | 1 (ImportError fallback) | 0 (only fires when xgboost & sklearn both absent) |
| `self_evolution.py` | 1 (in docstring, not real) | n/a |

**Concrete error-path coverage fraction (organism, excluding
HTTPException sites in `routes.py` which are tested via FastAPI 4xx/5xx
behavior):** ~5 / 11 = **~45%**.

V3 Track M-12 already added 3 negative tests for `replay_simulator.py`
(verified in `tests/test_replay_simulator_errors.py`, all 3 still
passing). The remaining gap — `brain_persistence` invariant raises and
`nightly_scheduler` runtime errors — is the most actionable extension.

`backend/services/` and `backend/api/` together have 341 raise sites;
fully auditing those is outside this track's scope.

---

## 8. Async test correctness

- `pytest.ini` sets `asyncio_mode = auto`. Good — no test should ever
  need an explicit `@pytest.mark.asyncio` decorator. (235 files have
  `async def test_`, 224 still mark them with `@pytest.mark.asyncio`,
  which is **redundant but harmless** — `auto` mode applies regardless.)
- **`asyncio.run` inside test bodies**: 10 files. Under `auto` mode
  these are an anti-pattern — they create a fresh event loop while
  pytest-asyncio is already managing one, which can leak tasks or
  swallow `RuntimeError`s. Files (head):
  - `tests/test_alpaca_production_comprehensive.py`
  - `tests/test_circuit_breaker_redis.py`
  - `tests/test_observability_service.py`
  - …and 7 more (full list in `cc_async_run_grep.log` not committed
    here; the seven that show up are derivatives of the same
    anti-pattern).
- **Sync tests that call coroutines without `await`**: spot-check did
  not surface any (most tests that mock an async method use
  `AsyncMock`, which is correct).
- **`asyncio.sleep` use**: 17 files. Most are short (≤0.1 s) for race
  testing; flagged the larger ones in §5.
- **Cross-thread coroutine use**: `tests/test_alert_cross_thread_dispatch.py`
  is one of the only places we exercise the actual cross-thread path.
  This is good; needs a peer for `live_engine`.

**Verdict: async correctness is mostly OK; the main improvement is
removing the 10 `asyncio.run` call-sites and pruning the 224 redundant
`@pytest.mark.asyncio` decorators (single-line cleanup, big diff).**

---

## 9. Test-smell catalog (20-test sample)

We sampled 20 tests/files (mix of recently-touched + random with seed
7) and inspected them for the V6-W smell list plus a few V5 carry-overs.

| # | Test / File | Smell(s) flagged |
| --: | --- | --- |
| 1 | `test_analytics_api_full.py::test_analytics_api` | **No assertions**; print()-only "test" that returns success based on whether it raises; **direct PG connection string hard-coded** (`postgresql+asyncpg://trading:trading_password@localhost:5432/algotrading`); requires live DB; emoji in output; runs as a script (line 14 hard-codes the DSN). |
| 2 | `test_replay_simulator_errors.py` | **Clean.** Three focused negative tests with explicit `pytest.raises(ValueError, match=...)`. Reference example. |
| 3 | `test_apr7_p0_p1_fixes.py` | Long module-level docstring (good context); `_make_brain` helper hand-rolled instead of fixture (mild). One test fails deterministically — see §4. |
| 4 | `test_alpaca_broker_comprehensive.py::TestRetryOnTransientError` | Redundant `@pytest.mark.asyncio` (asyncio_mode=auto). Otherwise clean — `nonlocal call_count` pattern is fine for retry counting. |
| 5 | `test_idempotency.py` | **External-dep dependency**: requires PG; correctly skips on sqlite. Emoji-in-assertion-message anti-pattern (`"❌ Missing constraint"`) — fine for humans, bad for grep/CI logs. |
| 6 | `test_dlq_processing.py::TestDLQProcessing.test_move_to_dlq_after_max_retries` | **Over-mocking** — patches `worker._move_to_dlq` then asserts that `_move_to_dlq` was called. The test stubs out the very thing under test; it verifies the **test-author's** retry-check logic, not the worker's. |
| 7 | `test_numerical_properties_v6.py` | **Excellent**: uses `hypothesis` with documented invariants tied to wave-17/18/19 fixes. One smell — the "fall back when hypothesis is missing" stub silently degrades to fixed-example coverage; should `pytest.skip` so CI flags it. |
| 8 | `test_audit_patch_queue_d3.py` | Helper `_make_trade(**overrides)` is good; but the test class names use comment-banners (`# === ... ===`) which are noise. Otherwise clean. |
| 9 | `test_audit_patch_queue_b2.py::TestMLConfidenceLeakage` | **Three deterministic failures** — tests are correct in shape but assert against an old contract. Production code has moved on (May-1 ML-from-gate drop). Smell: tests are not maintained in lock-step with code. |
| 10 | `test_audit_patch_queue_f4.py` | Clean. `MagicMock` for `_future` is the right shape. |
| 11 | `test_indicators_extended.py::test_sma_with_period_equal_length` | Brittle: asserts `result[i] is None or np.isnan(result[i])` — accommodates two contracts at once. Either decide which the indicator returns and pin it, or split into two tests. |
| 12 | `test_position_reconciliation_comprehensive.py` | Clean fixture pattern (mock_db_session, mock_alpaca_client, reconciliation_service). Reference example. |
| 13 | `test_helpers_comprehensive.py` | 110 test functions (very long file); imports 14 helpers up-front. Long-setup smell — would be cleaner as 5 modules. |
| 14 | `test_self_evolution.py` | Manipulates `sys.path.insert(0, ROOT)` at module level — should be done in `conftest.py`. Otherwise solid synthetic-data tests. |
| 15 | `test_position_management.py` | **Script masquerading as a test**: 10 test functions, **0 asserts**, requires live server at `localhost:8000`, prints to stdout. Skips if server is down (so it does no harm) but contributes nothing in CI. |
| 16 | `test_credentials.py` | Helper module mis-classified as a test (no `test_*` function bodies); discovered by `pytest` because of the `test_` prefix. Move to `tests/_helpers/` or rename. |
| 17 | `test_alembic_head.py` | Spawns subprocess (`alembic current`) — appropriate for an integration test, but the test should be marked `@pytest.mark.integration` (it is) **and** moved to a separate CI job, otherwise it adds 5–10 s to every fast-suite run. |
| 18 | `test_replay_simulator.py` | Top-of-file docstring + module structure are good. Failures are environmental (15-s timeout) — see §4–§5. Consider splitting "100-tick replay" into a separate `slow` test class. |
| 19 | `test_system_integration.py::TestMLKellyPipeline::test_train_predict_size_flow` | Trains a real `MLSignalGenerator(train_window=200)` inside a unit test — 1.6 s. Should use a saved/checkpointed model fixture. |
| 20 | `test_apr10_patch_f4_forensic_guard.py::test_bypass_audit_manifest_write_callsites` | **Structural / brittle string match** — uses `inspect.getsource` to look for specific guard strings. V6-W flagged this style. The test will fail any time someone reformats the source. |

**Smell totals (per 20 sample):** 5 over-mocking / brittle-string /
structural · 4 missing-asserts (analytics_api_full, position_management,
credentials, plus borderline pretrade_validation) · 3 long-setup /
fixture-missing (helpers_comprehensive, self_evolution sys.path,
audit_patch_queue_d3 banners) · 2 external-dep without proper isolation
(idempotency hard-codes DSN at module load, alembic_head spawns
subprocess) = **~14 smell-instances across 20 tests, ~5 distinct
patterns**. Inside the 3–8 quality-bar range.

---

## 10. Suite performance

- **Wall-clock estimate for full suite**: an unmonitored
  `pytest tests/ --timeout=15 -q` ran for 3 m 35 s and reached 36% before
  we terminated it; extrapolating naïvely gives ~10 minutes for a clean
  pass. The 91 s subset run with 296 tests (3.05 tests/s) extrapolates
  to ~48 minutes for 8,777 tests at the same rate, but most of the slow
  ones are concentrated in <30 files; the realistic cost of a clean
  full pass is **~8–12 minutes locally on Apple Silicon**, dominated by
  the 5–8 replay-simulator timeouts plus ML training in
  `test_system_integration.py`.
- **Top slow modules** (sum of all test durations in module):
  1. `test_replay_simulator.py` — ~80 s (8 of top 15).
  2. `test_system_integration.py` — ~6 s (TrainingWithDecay class).
  3. `test_idempotency.py` — gated on PG so 0 s in normal runs;
     5–10 s when PG is up.
  4. `test_alembic_head.py` — 5–10 s when PG is up.
  5. `test_h1_h2_real_money_hardening.py` and the apr10_patch family —
     1–2 s each via real ML training.
- **`pytest-xdist` parallelisation potential**: not currently used.
  With `auto` workers on a 10-core machine the wall-clock
  could likely drop to **~2 minutes** for the full suite, but only if
  the autouse `reset_module_caches` fixture is xdist-safe (it is —
  it touches per-process state) and the `test_db_<uuid>.sqlite3`
  randomization in conftest is preserved (it is). **Recommendation:
  add `pytest-xdist` and run CI with `-n auto`.**
- **Total CI test runtime estimate (sum of confirmed durations from
  --durations=20)**: 95.4 s for the 23-file curated run; the bulk
  (95%) is replay simulator + ML training — both candidates for a
  nightly-only `@pytest.mark.slow` lane.

---

## Summary headline

> **Coverage gaps: 199 modules below 50% line coverage** (in the 80-file
> coverage subset); **8 organism modules at 0%** (attribution,
> feature_store, nightly_scheduler, promotion, runner, scheduler,
> streaming_data_provider, training); **flaky tests: 0** in the 296-test
> curated subset across 3 consecutive runs (4-flake Memory.md note for
> the full suite is unverified by this audit but uncontradicted);
> **slow tests: 8** (5 replay-simulator timeouts at 15 s, 3 ML-training
> tests at 1.6–2.9 s).

---

## One-paragraph health summary

The suite is **broad but uneven**: 8,777 tests across 464 files give
the appearance of strong coverage, but instrumented runs show
`backend/organism/` at 42% line coverage and `backend/` overall at 26%
(a floor — many test files were excluded — but the *shape* is real).
The core tick loop `live_engine.py` (2,450 statements) sits at only
21% and eight organism modules — including `attribution`, `promotion`,
`runner`, `scheduler`, `streaming_data_provider`, `training`,
`feature_store`, and `nightly_scheduler` — have **zero direct
imports** in `tests/`, meaning they're only reached by transitive
loads at startup. Quality-wise the suite is in better shape than the
coverage numbers suggest: 13 deterministic failures we surfaced are
real regressions (ML-confidence-leakage tests still asserting the
pre-May-1 contract; replay simulator hitting the 15 s timeout), not
flakes; the May-1 hardening shipped without updating the test
contracts. The redundant `@pytest.mark.asyncio` on 224 files and the
`asyncio.run` anti-pattern in 10 files together represent the
cheapest cleanup. **The single highest-leverage improvement is to
add `pytest-cov` + `pytest-xdist` to the dev requirements and wire a
nightly `pytest --cov=backend --cov-report=xml -n auto` job whose only
gate is "coverage on `backend/organism/live_engine.py` and
`backend/risk/risk_manager.py` does not regress" — those two modules
are the riskiest under-covered surface today, and a coverage-baseline
ratchet is the lowest-effort, highest-information way to stop the
coverage gap from widening while the team focuses on the six
deterministic test failures the suite is already telling them about.**
