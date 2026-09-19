# Track NN — Reachability Audit (v8 NEW LENS)

**Repo / branch / commit**: `/Users/marselkei/VS/intra` @ `rc-1.5-curated` `5bc4046`
**Method**: AST + grep + import-graph + live DB inspection (`trading_platform_db_paper`).
**Scope**: 7 sub-sections from the v8 prompt.

The lens: **dead code with live-looking telemetry**. For every test, every endpoint, every class, every table — is the production path actually reached?

---

## 1. Tests-vs-imports divergence (Section 1)

Initial scan: 191 test files, 169 production import targets, **49 modules tested but never imported by production code**. After triaging false positives (entry-point modules reached by uvicorn / dynamic decorator registration / parent-package shadowing), the genuinely-orphan modules are:

| Orphan module | LOC class count | Triage |
|---|---|---|
| `backend/api/routes/position_import.py` | 3 endpoints | Imported by no router; **dead** |
| `backend/brokers/alpaca_production.py` | 5 classes | No prod importer; superseded by `backend/integrations/alpaca_broker.py` |
| `backend/brokers/broker_failover.py` | 3 classes (BrokerManager, AlpacaBrokerAdapter, BaseBroker) | `get_broker_manager` only referenced inside its own docstring; **dead** |
| `backend/config/coordinator.py` | — | No prod importer |
| `backend/features/alignment.py`, `backend/features/types.py`, `backend/features/validators.py` | — | No prod importer (only `feature_engineering.py` and `technical_indicators.py` are reached) |
| `backend/infra/order_guardrails.py` | OrderGuardrails class | `signals.py` imports `validate_order_guardrails` from `backend/infra/guardrails.py`, **not** from `order_guardrails.py` |
| `backend/infra/performance.py` | LRUCache, BatchProcessor, ConnectionPoolMonitor, AsyncTaskOptimizer, RingBuffer | No prod importer |
| `backend/ml/data_processing.py`, `backend/ml/ensemble_framework.py`, `backend/ml/pipeline.py`, `backend/ml/prediction_service.py`, `backend/ml/sentiment.py`, `backend/ml/validation.py` | 30+ classes total | No prod importer; only `model_manager`, `training`, `feature_engineering`, `staleness_detector` are alive |
| `backend/mlops/{deployment,feature_store,governance,model_optimization,model_serving,monitoring,pipeline}.py` | 35+ classes (~5k LOC) | The entire mlops package's internal modules are dead — only `mlops/__init__.py` re-exports symbols from `ml/model_manager.py` |
| `backend/models/order_integrity.py` | OrderStateMachine, OrderIntegrityService | No prod importer |
| `backend/monitoring/slo_alerts.py`, `backend/monitoring/slo_dashboard.py` | — | No prod importer |
| `backend/observability/metrics.py`, `backend/observability/tracing.py` | — | Only `backend/integrations/alpaca_stream.py` references `observability.metrics`; `tracing.py` has zero |
| `backend/risk/{advanced_risk,advanced_risk_manager,black_swan_protection,correlation_breakdown,margin_calculator,math,metrics,position_limits,risk_calculator,volatility_checker}.py` | 12+ risk classes | Only `risk/risk_manager.py` (`RiskManager`) and `risk/types.py` are alive in production. **`AdvancedRiskManager` is referenced only by `backend/optimization/portfolio_optimizer.py`, which itself is never imported.** |
| `backend/security/api_hardening.py` (SecurityMiddleware) | — | `get_security_middleware` only self-referenced |
| `backend/services/signal_service.py` | — | No prod importer |
| `backend/utils/{helpers,import_tracker,port_management,utilities,validators}.py` | — | No prod importer |

**False positives (re-classified as reachable):**
- `backend.api.main` — entrypoint via `uvicorn backend.api.main:socketio_app` (Dockerfile L110).
- `backend.api.health` — reached via `_register_health_endpoints` factory call in `backend/api/factory.py:204`.
- `backend.organism.replay_simulator` — used by tests + scripts/replay tools (legitimate dev-only utility).
- `backend.api.middleware` (package) — used by `middleware_setup.py`.

---

## 2. Function-level reachability sample (Section 2)

20 random non-private functions from `backend/organism/` (seed=8):

| File:line | Function | Prod calls | Verdict |
|---|---|---|---|
| `replay_simulator.py:615` | `from_alpaca` | 1 (self) | Test/replay only; OK |
| `diagnostic_checks.py:353` | `check_order_no_dup_entries` | 0 (registered via `@diagnostics.check` decorator) | OK (decorator-registered) |
| `diagnostic_checks.py:409` | `check_order_cooldown_maps` | 0 (decorator) | OK |
| `background_trainer.py:316` | `submit_retrain` | 1 (`live_engine.py:3956`) | Reachable |
| `replay_simulator.py:177` | `submit_symbol_order` | 5 | Reachable |
| `regime.py:614` | `check_drift` | 1 (`runner.py:112`) | Reachable |
| `feature_store.py:240` | `get_latest_snapshot` | **0** | **ORPHAN** — `VersionedFeatureStore.get_latest_snapshot` defined but no live caller. The store *writes* snapshots but never reads them back. |
| `promotion.py:67` | `to_dict` | 134 (overloaded name) | OK |
| `streaming_data_provider.py:184` | `get_latest_quote` | 4 | Reachable |
| `decision_telemetry.py:402` | `append` | 991 (overloaded name) | OK |
| `replay_simulator.py:366` | `current_simulated_time` | 0 (only self/scripts) | OK (replay-time hook) |
| `diagnostic_checks.py:714` | `check_governance_config` | 0 (decorator) | OK |
| `routes.py:240` | `resume_trading` | 2 | Reachable |
| `regime.py:71` | `to_dict` | 134 (overloaded) | OK |
| `brain_persistence.py:431` | `apply_to_signal_generator` | 1 (`live_engine.py:875`) | Reachable |
| `scheduler.py:133` | `start` | 16 (overloaded) | OK |
| `brain_persistence.py:197` | `total_runs` | 0 outside file | **ORPHAN** — `@property total_runs` exposed but no consumer reads it. Manifest field is read directly via `_manifest.get("total_runs")` instead. |
| `diagnostic_checks.py:582` | `check_streaming_health` | 0 (decorator) | OK |
| `decision_telemetry.py:58` | `to_dict` | 134 (overloaded) | OK |
| `ml_signal.py:625` | `load_calibration` | 2 | Reachable |

**Hits**: 2 of 20 functions are genuinely orphan (`get_latest_snapshot`, `total_runs` property). Estimated 10% orphan rate at function level.

---

## 3. Orphan classes (Section 3) — top 30

Of 453 plain logic classes (Pydantic / Enum / dataclass / Protocol / Exception excluded), **213 (47%)** have zero instantiations or name-references outside their defining file in non-test production code.

Top 30 representative orphans by domain:

| File:line | Class | Domain | Notes |
|---|---|---|---|
| `backend/risk/black_swan_protection.py:127` | `BlackSwanProtection` | Risk | "Black swan" name; never wired |
| `backend/risk/correlation_breakdown.py` | (entire module) | Risk | No prod importer |
| `backend/risk/margin_calculator.py:21` | `MarginCalculator` | Risk | No prod importer |
| `backend/risk/volatility_checker.py:25` | `VolatilityChecker` | Risk | No prod importer |
| `backend/risk/position_limits.py` | (entire module) | Risk | No prod importer |
| `backend/risk/risk_calculator.py` | (entire module) | Risk | No prod importer |
| `backend/risk/advanced_risk.py:653` | `AdvancedRiskManager` | Risk | Only referenced by `backend/optimization/portfolio_optimizer.py` (itself orphan) |
| `backend/risk/advanced_risk.py:129` | `VolatilityRegimeDetector` | Risk | Same |
| `backend/risk/advanced_risk.py:552` | `DrawdownMonitor` | Risk | Same |
| `backend/risk/risk_manager.py:171` | `AsyncRiskManager` | Risk | Sibling of `RiskManager` (which IS used); never instantiated |
| `backend/security/api_hardening.py:435` | `SecurityMiddleware` | Security | `get_security_middleware` only self-referenced |
| `backend/infra/security_hardening.py:128` | `SimpleRateLimiter` | Security | No prod caller |
| `backend/infra/security_hardening.py:404` | `JWTValidator` | Security | No prod caller |
| `backend/infra/security_hardening.py:460` | `JwtVerifier` | Security | Sibling JWT helper; orphan |
| `backend/infra/security_hardening.py:612` | `InputValidator` | Security | No prod caller |
| `backend/api/middleware/rate_limit.py:70` | `SlidingWindowRateLimiter` | Security | No prod caller |
| `backend/brokers/broker_failover.py:298` | `BrokerManager` | Broker | `get_broker_manager` only referenced in its own docstring |
| `backend/brokers/broker_failover.py:182` | `AlpacaBrokerAdapter` | Broker | Same |
| `backend/brokers/alpaca_production.py:120` | `ProductionAlpacaClient` | Broker | Superseded by `backend/integrations/alpaca_broker.py` |
| `backend/models/order_integrity.py:316` | `OrderStateMachine` | Order audit | No prod importer; references `audit_logger` |
| `backend/models/order_integrity.py:593` | `OrderIntegrityService` | Order audit | Wraps OrderStateMachine; orphan |
| `backend/strategies/trading_strategies.py:995` | `StrategyManager` | Strategy umbrella | Never instantiated; superseded by `MultiStrategyLiveRunner` |
| `backend/strategies/advanced_strategies.py:686` | `SqueezeBreakoutStrategy` | Strategy | Defined, never registered into runner |
| `backend/strategies/advanced_strategies.py:860` | `FailedBreakoutReversalStrategy` | Strategy | Defined, never registered |
| `backend/strategies/advanced_strategies.py:990` | `MultiTimeframeBreakoutStrategy` | Strategy | Defined, never registered |
| `backend/mlops/governance.py:661` | `MLOpsGovernanceService` | MLOps | Orphan |
| `backend/mlops/feature_store.py:397` | `FeatureStore` (3rd implementation) | MLOps | Naming collision: `backend/organism/feature_store.py:VersionedFeatureStore` is the live one |
| `backend/ml/prediction_service.py:362` | `PredictionService` | ML serving | Whole prediction-service file is orphan |
| `backend/analytics/realtime_risk_analytics.py:142` | `RealTimeRiskAnalytics` | Analytics | `analytics = RealTimeRiskAnalytics(...)` only inside its own `__main__` block |
| `backend/optimization/portfolio_optimizer.py` | (entire module) | Portfolio | No prod importer |

By-file orphan-density leaders: `backend/ml/validation.py` (8 orphan classes), `backend/mlops/{model_optimization,feature_store,deployment,pipeline}.py` (7 each), `backend/config/base_settings.py` (7), `backend/models/ensemble_model.py` (5), `backend/infra/production.py` (5), `backend/infra/performance.py` (5), `backend/brokers/alpaca_production.py` (5).

---

## 4. Endpoint reachability (Section 4)

`backend/api/routes_setup.py` includes 26 routers. Diff against `backend/api/routes/*.py`:

| Route file | Mounted? | Notes |
|---|---|---|
| `admin_trading.py` | yes | |
| `audit.py` | yes | |
| `auth.py` | yes | |
| `auto_breakout_scanner.py` | yes | |
| `backtest.py` | yes | |
| `chart_templates.py` | yes (public + protected) | |
| `drawings.py` | yes | |
| **`health.py`** | indirect | Reached via `_register_health_endpoints` factory using `create_health_endpoints()` |
| `indicators.py` | yes | |
| `lots.py` | yes | |
| `market_data.py` | yes | |
| `models.py` | yes | |
| `monitoring.py` | yes | |
| `multi_strategy_live.py` | yes | |
| `observability.py` | yes | |
| `optimizations.py` | yes | |
| `orders.py` | yes | |
| **`position_import.py`** | **NO** | **Defines 3 routes (`@router.get`, `.post`, `.delete`) at prefix `/positions`. Never imported into `routes_setup.py` or anywhere else (only `scripts/check_imports.py` mentions it). The endpoints `POST /positions/import-from-alpaca`, `GET /positions/imported`, `DELETE /positions/imported/{id}` are unreachable.** |
| `positions.py` | yes | |
| `risk.py` | yes | |
| `scanner.py` | yes | |
| `settings.py` | yes | |
| `signals.py` | yes | |
| `strategy.py` | yes | |
| `system.py` | yes | |
| `trades.py` | yes | |
| `watchlists.py` | yes | |

Plus `backend/api/portfolio.py` (file outside `routes/`) is mounted as `portfolio_router` and defines 6 routes — those work.

**1 orphan route file with 3 endpoints**: `position_import.py`.

---

## 5. Database table reachability (Section 5)

`docker exec trading_platform_db_paper psql ...` returned 26 public tables. All 26 have an ORM `__tablename__` declaration in `backend/infra/schemas.py`. None is fully orphan, but two are write-only / read-only asymmetric:

| Table | Live row count | Writers in code | Readers in code | Issue |
|---|---|---|---|---|
| `outbox_events` | 1393 sent / 5 failed | `OutboxRepo.add_order_submit_event` (services/order_service.py, api/routes/{signals,positions,orders}.py) | `OutboxRepo.claim_batch` (infra/outbox_worker.py) | **Healthy** — outbox worker IS started in `lifespan.py:167-169`. |
| `tick_telemetry` | **0** | `live_engine.py:5780` | none | **WRITE-ONLY, AND ZERO ROWS WRITTEN.** Comment at `live_engine.py:5760-5765` documents that `from backend.infra.database import ...` was the wrong import — fixed to `backend.infra.db` on 2026-05-02. After fix: still zero rows in DB — either current container hasn't been rebuilt to pick up the fix, or the surrounding `try/except` swallows another error silently. Telemetry consumers reading from this table will see no data. |
| `model_lifecycle_events` | (not queried) | `living_policy.py`, `feature_store.py` (writes) | `living_policy._load_latest_snapshot` (reads) | OK |
| `audit_logs` | (not queried) | `AuditsRepo.create_audit_log` (`infra/repositories/audits.py`), `services/audit_service.py` | seed scripts, audit_service queries | Reachable but most production code paths bypass it (the live engine never calls `create_audit_log`). |

No physical orphan tables. **One zero-write production table** (`tick_telemetry`) — production telemetry pipe is broken end-to-end despite an inline fix comment claiming repair.

---

## 6. Worker / background task reachability (Section 6)

| Worker / scheduler | Defining file | Started where? | Verdict |
|---|---|---|---|
| `OutboxWorker` | `backend/infra/outbox_worker.py:57` | `backend/api/lifespan.py:169` (`start_outbox_worker`) | Reachable |
| `multi_strategy_live_scheduler` | `backend/services/multi_strategy_live_scheduler.py` | `backend/api/lifespan.py:243` — but **gated `_organism_active`-OFF**: with `.env:ENABLE_ORGANISM_SCHEDULER=1` and `MULTI_STRATEGY_LIVE_ENABLED=1`, the `elif _organism_active:` branch fires and logs "Multi-strategy live scheduler skipped — organism engine is active". | **Dead under current env** — the entire `MultiStrategyLiveRunner` + 10 strategy plug-ins are not driven by this scheduler. |
| `auto_breakout_scanner_scheduler` | `backend/services/auto_breakout_scanner_scheduler.py` | `backend/api/lifespan.py:263` (gated by `AUTO_BREAKOUT_SCAN_ENABLED=1`, which IS set) | Reachable. Inside, `MultiStrategyLiveRunner.run_once()` is invoked **only when** `AUTO_BREAKOUT_AUTO_TRADE` is truthy — that env var is **not set in `.env`**, so the runner is built but `run_once()` is never called. |
| `scheduled_reconciliation` | `backend/services/scheduled_reconciliation.py` | `backend/api/lifespan.py:322` (`start_reconciliation_scheduler`, OPT-IN env) | Conditional |
| `diagnostic_scheduler` | `backend/organism/diagnostic_scheduler.py` | `backend/organism/scheduler.py:118` | Reachable |
| `nightly_scheduler` | `backend/organism/nightly_scheduler.py` | imported by `scripts/runtime/...` and `scheduler.py` | Reachable |
| `lifecycle_scheduler` | `backend/ml/lifecycle_scheduler.py` | gated by `ENABLE_ML_LIFECYCLE_SCHEDULER=1` (set in .env, line 117) | Reachable |
| Alpaca outbox dispatcher | `backend/integrations/alpaca_outbox.py:70` | reached transitively via `outbox_worker._process_event` → `handle_order_submitted_event` | Reachable |

**1 functional-orphan worker**: `multi_strategy_live_scheduler` is wired but always skipped because it is mutually exclusive with the organism scheduler and the latter is on. Effect: the entire `backend/strategies/` plug-in path described in Section 7 has no live driver.

---

## 7. Strategy plug-in reachability (Section 7)

Of 15 `BaseStrategy` subclasses across `backend/strategies/`:

| Strategy | Defined | Tested? | Instantiated in prod? | By whom | Verdict |
|---|---|---|---|---|---|
| `EnsembleStrategy` | trading_strategies.py:192 | yes | self only (`StrategyManager.__init__`) | `StrategyManager` (orphan) | DEAD |
| `MeanReversionStrategy` | trading_strategies.py:305 | yes | yes | `walk_forward.py`, `multi_strategy_live_runner.py` | Reachable through walk-forward (offline) only |
| `MomentumStrategy` | trading_strategies.py:390 | yes | yes | walk_forward + multi_strategy_live_runner | Same |
| `RegimeFilteredMomentumStrategy` | trading_strategies.py:483 | no | yes | walk_forward + multi_strategy_live_runner | Same |
| `BreakoutStrategy` | trading_strategies.py:617 | no | yes | walk_forward + multi_strategy_live_runner | Same |
| `RebalancingStrategy` | trading_strategies.py:777 | yes | **NO** | none | DEAD |
| `StatisticalArbitrageStrategy` | trading_strategies.py:845 | yes | yes | walk_forward + multi_strategy_live_runner | Same |
| `AdaptiveRegimeMomentumStrategy` | advanced_strategies.py:41 | no | yes | multi_strategy_live_runner | Same |
| `OrderFlowImbalanceStrategy` | advanced_strategies.py:177 | no | yes | multi_strategy_live_runner | Same |
| `VolatilityStructureStrategy` | advanced_strategies.py:311 | no | yes | multi_strategy_live_runner | Same |
| `CrossSectionalMomentumStrategy` | advanced_strategies.py:441 | no | yes | multi_strategy_live_runner | Same |
| `MicrostructureAlphaStrategy` | advanced_strategies.py:550 | no | yes | multi_strategy_live_runner | Same |
| `SqueezeBreakoutStrategy` | advanced_strategies.py:686 | no | **NO** | none | DEAD |
| `FailedBreakoutReversalStrategy` | advanced_strategies.py:860 | no | **NO** | none | DEAD |
| `MultiTimeframeBreakoutStrategy` | advanced_strategies.py:990 | no | **NO** | none | DEAD |

**Critical context**: even the "yes — multi_strategy_live_runner" strategies are only instantiated in two places:
1. `backend/organism/walk_forward.py` — offline backtest evaluator, not a tick path.
2. `backend/services/multi_strategy_live_runner.py` — driven by `multi_strategy_live_scheduler` (Section 6: skipped) **or** `auto_breakout_scanner_scheduler.run_once()` (gated by `AUTO_BREAKOUT_AUTO_TRADE`, not set).

**Verdict**: **None of the 15 BaseStrategy subclasses participates in the live trading tick loop in the current paper deploy.** The live trading engine (`backend/organism/live_engine.py` + `backend/organism/alpha_scanner.py`) does not import `BaseStrategy` at all (grep confirms). The `backend/strategies/` package (≈4,872 LOC + advanced_strategies.py) is **decorative** under the current organism-active configuration — re-confirms V7 HH finding "barely wired live."

---

## Severity tiers

### Critical (security / financial path orphan)
1. **`backend/api/routes/position_import.py` — 3 unreachable endpoints (`POST /positions/import-from-alpaca`, `GET /positions/imported`, `DELETE /positions/imported/{id}`).** Documented as part of the position-import feature, but the file is not imported by `routes_setup.py`. A duplicate `prefix="/positions"` with `positions.py` would be a routing conflict if ever wired. Severity: Critical because this is a *financial position management* endpoint set that operators may believe is live.
2. **`backend/strategies/` 15-class plug-in surface — no live driver.** All 15 BaseStrategy subclasses (~4,872 LOC + `advanced_strategies.py`) only run inside (a) offline walk-forward backtests or (b) a multi-strategy scheduler that is hard-mutex'd OFF when the organism scheduler is active (which it always is in `.env`). Production trading goes through `live_engine.py` → `alpha_scanner.py`, neither of which imports `BaseStrategy`. Severity: Critical because this is the largest body of "live-looking but never executed" code in the repo.
3. **`backend/risk/{black_swan_protection,correlation_breakdown,margin_calculator,position_limits,volatility_checker,risk_calculator,advanced_risk_manager,advanced_risk}.py` — 8 risk modules orphan.** Names that scream "production-grade risk controls" — never instantiated on the live tick path. Live risk uses only `backend/risk/risk_manager.RiskManager`. Severity: Critical because the audit surface implies multi-layer risk defense that does not exist at runtime.

### High (audit / compliance / observability orphan)
4. **`tick_telemetry` table is write-only AND has zero rows.** `live_engine.py:5760` writes via `TickTelemetry(...)`, but the live DB shows `count=0`. An inline comment dated 2026-05-02 admits a previous import path was wrong (`backend.infra.database` vs `backend.infra.db`) and silently swallowed by `except Exception`. The fix is on disk but the deployed container apparently hasn't picked it up, OR another silent failure persists. Any dashboard or audit consumer reading `tick_telemetry` sees nothing.
5. **`backend/models/order_integrity.py:OrderStateMachine` + `OrderIntegrityService` — orphan.** Both classes exist with audit_logger plumbing; never instantiated. Order audit story therefore relies entirely on `audit_logs` table writes, which only `AuditsRepo` performs and `live_engine.py` never invokes.
6. **`backend/security/api_hardening.py:SecurityMiddleware` and `backend/infra/security_hardening.py:{SimpleRateLimiter, JWTValidator, JwtVerifier, InputValidator}` — orphan.** Six security helpers that look like a hardening layer but are not wired into the FastAPI middleware stack. (Real auth lives in `backend/infra/security.py:get_authenticated_user` which IS used.)

### Medium (logic-path orphan)
7. **`backend/mlops/` package internals — 7 modules orphan (~5k LOC).** Only `mlops/__init__.py` re-exports symbols from `ml/model_manager.py`. The 7 internal modules (`pipeline`, `deployment`, `feature_store`, `model_optimization`, `model_serving`, `governance`, `monitoring`) are entirely unreachable.
8. **`backend/ml/{data_processing,ensemble_framework,pipeline,prediction_service,sentiment,validation}.py` — orphan.** Live ML uses only `model_manager`, `staleness_detector`, `training`, `feature_engineering`, `drift`, `lifecycle`, `lifecycle_scheduler`. The other six modules (~30 classes) are inert.
9. **`backend/optimization/portfolio_optimizer.py` — entire module orphan.** Imports `AdvancedRiskManager` (also orphan) but no production code imports `portfolio_optimizer` itself.
10. **`backend/brokers/{alpaca_production,broker_failover}.py` — orphan.** The live broker chain runs through `backend/integrations/alpaca_broker.py` + `alpaca_outbox.py`. The `brokers/` package's own `BrokerManager`/`AlpacaBrokerAdapter`/`ProductionAlpacaClient` classes are dormant — `get_broker_manager` is only referenced inside its own docstring.

### Low (utility orphan)
- `backend/utils/{helpers,import_tracker,port_management,utilities,validators}.py` — five unused utility modules.
- `backend/infra/performance.py` — 5 internal performance helpers (LRUCache, BatchProcessor, ConnectionPoolMonitor, AsyncTaskOptimizer, RingBuffer) all orphan.
- `backend/infra/object_pool.py` — Poolable, ObjectPool, AsyncObjectPool — orphan.
- `backend/observability/tracing.py` — orphan.
- `backend/monitoring/{slo_alerts,slo_dashboard}.py` — orphan.
- `backend/api/middleware/rate_limit.py:SlidingWindowRateLimiter` — orphan.
- `backend/strategies/trading_strategies.py:StrategyManager` (umbrella class) — orphan.
- `backend/organism/feature_store.py:VersionedFeatureStore.get_latest_snapshot` — write-only persistence path; reader exists but no caller invokes it.
- `backend/organism/brain_persistence.py:total_runs` `@property` — bypassed; consumers read `_manifest.get("total_runs")` directly.

---

## Summary

**Reachability findings: 10 (3 Critical, 3 High, 4 Medium) + ~15 Low.** Largest orphan: **`backend/strategies/` (~4,872 LOC + 15 BaseStrategy subclasses) — fully decorative under the current organism-active deploy.**

### TL;DR

The wave-31 reachability lens generalizes uncomfortably well across the repo. Of 453 plain logic classes, 213 (47%) have no callers outside their own file or tests; of 15 `BaseStrategy` subclasses, **zero** are exercised by the live tick loop because the only schedulers that drive them are mutex'd off (`multi_strategy_live_scheduler` skips when organism is active) or env-flag-disabled (`auto_breakout_scanner_scheduler` requires `AUTO_BREAKOUT_AUTO_TRADE` which is unset). The risk story is the most dangerous instance: 8 risk-themed modules (`black_swan_protection`, `correlation_breakdown`, `margin_calculator`, `volatility_checker`, `position_limits`, `risk_calculator`, `advanced_risk_manager`, `advanced_risk`) are entirely uninstantiated, yet their presence in the tree implies a multi-layer defense that doesn't exist at runtime. Three operationally important orphans deserve immediate attention: (1) `position_import.py` defines three financial-action endpoints that no router mounts; (2) `tick_telemetry` is write-targeted but has zero live rows despite an inline fix comment dated 2026-05-02; and (3) `OrderStateMachine`/`OrderIntegrityService` are unwired, leaving order auditability dependent on a single `AuditsRepo` path that the live engine itself never invokes. The smaller orphans — entire `backend/mlops/` internals (~5k LOC), 6 of 14 `ml/` modules, the `brokers/` package, `portfolio_optimizer.py`, `SecurityMiddleware` — together represent a substantial fraction of the codebase that audit tools, tests, and reviewers can confuse for live behavior. The recommended remediation is not deletion but explicit `# DEAD CODE — gated by X` markers plus a CI check that fails when a `tests/test_*.py` imports a module that no production importer references, so that "tested but unreachable" cannot land silently again.
