# Track HH v7 — Architecture / Code Organization Audit

**Repo:** `/Users/marselkei/VS/intra`
**Branch:** `rc-1.5-curated` @ `d44eace`
**Method:** Read-only structural audit. Deliverable is refactoring proposals ranked by ROI.
**Date:** 2026-05-02

---

## 0. Scale snapshot

| Layer | Files | LOC | Avg LOC/file |
|---|---:|---:|---:|
| `backend/organism/` | 41 | 26,654 | 650 |
| `backend/api/` | 51 | 18,976 | 372 |
| `backend/infra/` | 33 | 16,768 | 508 |
| `backend/services/` | 28 | 15,066 | 538 |
| `backend/ml/` | 18 | 9,274 | 515 |
| `backend/mlops/` | 11 | 8,478 | 770 |
| `backend/risk/` | 13 | 6,291 | 484 |
| `backend/strategies/` | 9 | 4,872 | 541 |
| `backend/integrations/` | 7 | 3,865 | 552 |
| `backend/models/` | 7 | 3,516 | 502 |
| `backend/data/` | 6 | 2,677 | 446 |
| `backend/analytics/` | 3 | 1,767 | 589 |
| **Total backend** | **~227** | **~140,530** | — |

Organism is the heaviest layer in absolute lines, almost entirely concentrated in two files (`live_engine.py` + `brain_persistence.py` = **8,520 lines / 32%** of the layer).

---

## 1. Top-10 largest files

| Rank | File | LOC |
|---:|---|---:|
| 1 | `backend/organism/live_engine.py` | **6,401** |
| 2 | `backend/services/backtest_service.py` | 2,775 |
| 3 | `backend/organism/brain_persistence.py` | 2,119 |
| 4 | `backend/ml/model_manager.py` | 1,988 |
| 5 | `backend/models/ensemble_model.py` | 1,846 |
| 6 | `backend/risk/risk_manager.py` | 1,832 |
| 7 | `backend/services/order_service.py` | 1,817 |
| 8 | `backend/api/routes/models.py` | 1,786 |
| 9 | `backend/config/base_settings.py` | 1,745 |
| 10 | `backend/api/routes/orders.py` | 1,555 |

13 files exceed 1,000 LOC. Memory.md noted ~3,600 lines for `live_engine.py`; current size is **6,401 lines**, an 78% increase since that note was written.

---

## 2. God-class inventory

### `OrganismLiveEngine` — the elephant

| Metric | Value |
|---|---:|
| Class LOC | ~6,050 (lines 351-6401) |
| Method count | **37** |
| `__init__` body | **374 lines** |
| `_live_tick_inner` body | **2,510 lines** (single async method) |
| `self.*` assignments in `__init__` | 52 |
| Distinct `self.*` attributes | 104 (185 references, 156 assignments overall) |
| Direct organism collaborators (constructed in `__init__`) | 17 (`signal_gen`, `alpha_scanner`, `breakout_scanner`, `pyramider`, `kelly_sizer`, `exit_engine`, `learner`, `regime_detector`, `_shadow_regime_detector`, `_orb_scanner`, `_eod_scanner`, `_mean_reversion_scanner`, `governance`, `evolution_engine`, `universe_selector`, `brain`, `transfer_engine`, `_feature_store`, `_telemetry`, `_bg_trainer`, `MarketScanner`) |

**`_live_tick_inner` decomposition** (visible from comment markers):

| # | Step | Approx line | Owner-able to a sub-component? |
|---:|---|---:|---|
| 0 | Stream health | 1556 | yes — Health/Watchdog |
| 0.5 | Stale data gate | 1573 | yes — Health/Watchdog |
| 1 | Governance check | 1594 | yes — Governance |
| 1.1 | Warmup gate | 1607 | yes — Gates |
| 1.2 | Stale data gate (entries) | 1621 | yes — Gates |
| 1.3 | EOD entry block + flatten | 1631 | yes — Lifecycle |
| 1.5 | Market scan (Phase 5) | 1661 | yes — Scanner |
| 2 | Fetch latest data + features | 1698 | yes — DataPipeline |
| 3 | Detect regime | 1719 | yes — RegimeStage |
| 4 | Get current positions | 1874 | yes — PositionSync |
| 5 | Check exits | 2056 | yes — ExitStage (~430 LOC) |
| 6 | Check pyramids | 2490 | yes — PyramidStage |
| 7 | Scan for new entries | 2631 | yes — EntryStage (~860 LOC, the heaviest) |
| 8 | Size positions (Kelly) | 3496 | yes — Sizing |
| 9 | Submit entry orders | 3544 | yes — Submission |
| 10 | Record trade outcomes | 3758 | yes — Outcomes |
| 11 | Periodic retrain + evolve | 3763 | yes — LearningStage |
| 12 | Brain save | 3920 | yes — Persistence |

This file is a textbook *transaction script* god-method. Steps 0-12 are all already commented and natural; they have very few cross-step shared variables — a pipeline/stage refactor would be mechanical.

### `OrganismBrain` (brain_persistence.py)

| Metric | Value |
|---|---:|
| Class LOC | ~1,950 |
| Method count | **48** |
| Save/load symmetry | 13 `_save_X` ↔ 13 `_load_X` methods + 4 `apply_*` |

Classic "kitchen-sink persistence" with one method per JSON file. Splitting into per-concern serializers (ML, learning, governance, regime, equity, evolved-params, trade history) would reduce coupling.

---

## 3. Coupling matrix

### Top fanout (modules importing the most)

| Fanout | Module |
|---:|---|
| **49** | `backend.organism.live_engine` |
| 33 | `backend.api.routes_setup` |
| 31 | `backend.api.lifespan` |
| 24 | `backend.api.routes.models` |
| 22 | `backend.api.routes.orders` |
| 15 | `backend.api.factory` |
| 15 | `backend.api.routes.positions` |
| 13 | `backend.infra.outbox_worker` |
| 13 | `backend.api.routes.signals` |
| 11 | `backend.organism.background_trainer` |

`live_engine` has 49 distinct backend imports — far more than any other module. Of these, 24 are organism-internal (it pulls in **24 of 41** organism siblings).

### Top fanin (modules imported by the most)

| Fanin | Module |
|---:|---|
| 64 | `backend.utils.logger` |
| 45 | `backend.infra.schemas` |
| 35 | `backend.infra.db` |
| 35 | `backend.infra.security` |
| 18 | `backend.integrations.alpaca_broker` |
| 16 | `backend.infra.alerting` |
| 15 | `backend.config` |
| 12 | `backend.utils.market_hours` |
| 11 | `backend.utils.secure_pickle` |
| 10 | `backend.api.socketio_server` |

Healthy: pure infra/utils dominate the fanin table. No organism module is in the top 10.

### Organism-internal edges

24 organism→organism edges from `live_engine` alone (all eager). Other organism cross-edges (eager): `alpha_scanner→ml_signal`, `continuous_learner→{ml_signal, ml_features}`, `ml_signal→ml_features`, `promotion→governance`, `runner→{governance, regime}`, `training→{attribution, feature_store, governance, walk_forward}`, `diagnostic_checks→diagnostics`. Graph is **DAG-shaped** internally, with `live_engine` as the sole top-level orchestrator — coupling concentrated, not tangled.

---

## 4. Circular dependencies

After excluding self-loops (same-module within a package), one **true cross-module cycle** exists:

| Cycle | Notes |
|---|---|
| `backend.api.routes.models` ↔ `backend.ml.lifecycle` | `routes/models.py` imports `ml.lifecycle` at top level; `ml.lifecycle` lazy-imports `routes.models` (or vice versa). Should be one-way: routes → ml, never ml → routes. |

A 3-way cycle exists *inside the api layer* (`api.factory → api.routes_setup → api.routes.auth → api.factory`) — broken only because `routes.auth → api.factory` is a lazy import. Architecturally fragile but not currently failing.

The organism layer is **cycle-free** — confirmed by AST scan including nested imports.

---

## 5. Layering violations

Intended layering (top to bottom): `api → services → organism → integrations → infra`.

| Violation | Location | Severity |
|---|---|---|
| `organism.scheduler` → `api.socketio_server` (lazy) | `backend/organism/scheduler.py:288` | **Medium** — strategy layer reaching up into HTTP/WS layer for broadcasts. Should be inverted via an event bus / observer interface owned by organism, with api subscribing. |
| `infra.guardrails` → `services.quote_manager` (eager) | `backend/infra/guardrails.py:27` | **High** — infra is supposed to be terminal. This makes infra depend on a higher layer. |
| `infra.outbox_worker` → `services.trading_execution_mode` (lazy) | `backend/infra/outbox_worker.py:357` | **Medium** — infra reaching into services. |
| `integrations.alpaca_stream_production` → `services.lot_tracker_service` (eager) | `backend/integrations/alpaca_stream_production.py:29` | **Medium** — integrations should expose data/orders, not depend on portfolio/services concepts. |
| `organism.routes` exists at all | `backend/organism/routes.py` (882 lines, defines `APIRouter`, 22 endpoints) | **Medium** — strategy module defining HTTP layer. Belongs under `backend/api/routes/organism.py`. Currently the only file outside `backend/api/` that defines `APIRouter`. |
| Organism → integrations leaks (lazy) | `live_engine:1534` (alpaca_stream), `routes.py:617` (alpaca_broker), `streaming_data_provider:26` (alpaca_market_data_stream — eager) | **Low/Medium** — strategy directly knows about Alpaca. Acceptable behind interfaces; the eager one in `streaming_data_provider` is the worst offender. |

The good news: **no `organism → api` eager imports** at all (only one lazy from `scheduler`). The HTTP layer separation is mostly held.

---

## 6. Lazy import inventory

**Total lazy imports inside organism functions/methods: 136**

| File | Lazy imports |
|---|---:|
| `live_engine.py` | **43** |
| `brain_persistence.py` | 18 |
| `background_trainer.py` | 17 |
| `routes.py` | 10 |
| `diagnostic_checks.py` | 8 |
| `ensemble_models.py` | 7 |
| Others (15 files) | 33 combined |

**Why are they lazy? Sampled comments and code:**

- `dispatch_alert_from_thread` (16 sites) — locally re-imported at every error path despite being needed at hot frequency. Rationale unclear. Default policy should be top-of-file unless a circular dep exists.
- `from backend.organism.trading_phase` (in live_engine, multiple) — pure data accessor, no good reason to be lazy.
- `from backend.integrations.alpaca_stream` (live_engine:1534) — defensive against missing module in unit tests. Could be top-level guarded with `try/except ImportError`.
- `from backend.organism.live_engine` inside `replay_simulator.py:548-562` and `diagnostic_checks.py` — **legitimate**, breaks cycle.
- `from backend.organism.diagnostics` in `diagnostic_scheduler.py` — **legitimate** lazy.
- `msvcrt`/`fcntl` in `brain_persistence.py:323` — **legitimate** OS-conditional.
- `pickle`, `pandas`, `copy` in `background_trainer.py` — defer-on-use to skip startup cost; defensible.

**Estimated count of lazy imports that could/should be eager: ~70-90 of 136**, mostly the repeated `dispatch_alert_from_thread` block and `trading_phase` re-imports inside `live_engine.py`.

---

## 7. Inheritance vs composition

Inheritance hierarchies in the codebase are **shallow**. Among 124 classes with non-trivial bases, the **maximum chain depth is 3**, and only one such case exists (`EmailValidator → StringValidator → ValidatorBase`). All other inheritance is depth-2:

- `*Strategy(BaseStrategy)` — 15 subclasses in `backend/strategies/{trading_strategies,advanced_strategies}.py`. Healthy template-method pattern. **But almost none are wired live** — only `walk_forward.py` (offline backtesting) and `services/multi_strategy_live_runner.py` reference them. The "real" strategies are composition-based inside `OrganismLiveEngine` (alpha/breakout/orb/eod/mean-reversion/pyramider). **The two strategy systems duplicate intent** — see Finding §10.
- `*Config(BaseSettings)` — pydantic settings classes. Fine.
- `*(Base)` — SQLAlchemy declaratives. Fine.
- `*(str, Enum)` — enum tag. Fine.

**`OrganismLiveEngine` is composition-heavy** (17 collaborators), which is the right choice. The class size problem is *coordination*, not inheritance.

---

## 8. Public surface cleanup candidates

`__all__` is declared in **only 2 of 41 organism modules** (`scheduler.py`, `routes.py`). For the other 39, every non-`_` symbol is technically public.

Modules where >50% of public exports are never imported externally (candidates either to underscore-prefix or to expose via a constants module):

| Module | Unused public symbols | Total public |
|---|---:|---:|
| `diagnostic_checks` | 40 | 40 |
| `routes` | 37 | 37 (HTTP handlers — would normally not be imported) |
| `mean_reversion_scanner` | 14 | 15 |
| `orb_scanner` | 13 | 14 |
| `market_scanner` | 9 | 11 |
| `eod_scanner` | 9 | 10 |
| `composite_indicators` | 8 | 8 |
| `universe_selector` | 8 | 9 |
| `decision_telemetry` | 7 | 7 (dataclass exports — externally only `DecisionSnapshot` is used) |
| `brain_persistence` | 6 | 7 (constants like `MAX_BACKUPS`, `LOCK_FILE`) |
| `self_evolution` | 6 | 6 (only `EvolutionEngine`/`EvolvedParams`/`apply_evolved_params` would be imports — but the report shows none referenced externally; that's because external users go through `live_engine` aggregator) |

**No "underscore-prefixed but imported externally" violations found in organism/** — i.e., the existing privacy convention is respected; just under-applied.

---

## 9. Repeated-pattern catalog (top 5)

### P-1. `dispatch_alert_from_thread` wrap-and-pray (16 sites)

Every site repeats the same boilerplate:

```python
try:
    from backend.infra.alerting import (
        AlertCategory, AlertSeverity, send_alert,
        dispatch_alert_from_thread,
    )
    _x = local_var  # bind for closure
    dispatch_alert_from_thread(
        lambda: send_alert(AlertCategory.SYSTEM_ERROR, ...,
                           context={"x": _x}, ...)
    )
except Exception:
    pass
```

Sites: `live_engine.py` (3), `ml_signal.py` (1), `brain_persistence.py` (1), `background_trainer.py` (1), `services/order_service.py` (1), `infra/outbox_worker.py` (1), `api/lifespan.py` (1), plus several inside helpers.

**Refactor:** a `safe_alert(category, severity, msg, **ctx)` helper in `backend/infra/alerting.py` that owns the lazy import + try/except. Reduces ~10 lines per site to 1.

### P-2. `_now_fn` clock-injection stanza

Repeated verbatim in `regime.py`, `continuous_learner.py`, `promotion.py`, `governance.py`, plus assigned externally in `replay_simulator.py` and `live_engine.py`:

```python
if now_fn is None:
    self._now_fn = lambda: datetime.now(UTC)
else:
    self._now_fn = now_fn
```

`replay_simulator.py:543-562` then reaches into multiple components to override this attribute by name (`_now_fn_components`).

**Refactor:** a `ClockMixin` (or function-scoped `make_clock(now_fn)` helper) plus a registry in replay_simulator (`Clock.set_replay_now(replay_now)` instead of attribute-stamping). Makes test-time clock injection one-liner and removes the implicit "must call your clock attribute `_now_fn`" contract.

### P-3. Per-key env helpers (`_env_int`, `_env_float`, `_env_str`, `_env_bool`)

Defined in `live_engine.py:151-165` and **39 call sites in that file alone**. Defined again in `backend/config/config.py`. Two implementations of the same helper.

`os.getenv` appears **383 times** across `backend/`, with only 9 of 75 files actually importing from `backend.config.settings`. The pydantic `Settings` class in `config/base_settings.py` (1,745 LOC, 12 sub-Config classes) is the canonical home, but most of the codebase does not use it.

**Refactor:** consolidate `_env_*` into `backend.config.env` with a single source. Migrate `live_engine.py` constants section to populate from a typed `LiveEngineConfig(BaseSettings)` once — *per call*, not once-at-import — so tests can override.

### P-4. Atomic `_write_json` (mostly consolidated, one outlier)

`brain_persistence.py:_write_json` (helper at line 2035) is used **12 times within that module**. `diagnostic_scheduler.py:109-113` re-implements the `tempfile + os.replace` pattern inline. `brain_persistence.py:1398-1410` writes `trade_history.csv` atomically using a hand-rolled variant.

**Refactor:** lift `_write_json` to `backend/infra/atomic_io.py` and add `atomic_write_text(path, text)` so the CSV path and `diagnostic_scheduler` reuse it. Three sites, two minutes each.

### P-5. Per-state save/load symmetry in `OrganismBrain`

13 paired `_save_X` / `_load_X` methods (`_save_ml_models`/`_load_ml_models`, `_save_governance_state`/`_load_governance_state`, etc.), each ~10-30 lines, each with its own try/except + filename + JSON shape.

**Refactor:** declarative serializer registry:

```python
SERIALIZERS = [
    ManifestSerializer(), MLModelsSerializer(), MLStateSerializer(),
    LearningStateSerializer(), TradeHistorySerializer(), EquityCurveSerializer(),
    EpochMetricsSerializer(), ExtraCountersSerializer(), EvolvedParamsSerializer(),
    GovernanceStateSerializer(), RegimeStateSerializer(),
    EvaluationEventHistorySerializer(),
]
class Serializer(Protocol):
    filename: str
    def save(self, target: Path, source: Any) -> None: ...
    def load(self, target: Path) -> Any: ...
```

Each serializer becomes ~30 LOC; `OrganismBrain.save/load` becomes a 5-line loop. Eliminates 26 near-duplicate methods.

---

## 10. Strategy module coupling — two parallel "strategy" systems

`backend/strategies/{trading_strategies,advanced_strategies}.py` define **15 `BaseStrategy` subclasses** (Momentum, MeanReversion, Breakout, Ensemble, OrderFlowImbalance, etc.). This is the historical "framework" surface.

`backend/organism/{alpha_scanner,breakout_scanner,mean_reversion_scanner,orb_scanner,eod_scanner,pyramider}.py` define **the actually-running strategies** as composition objects inside `OrganismLiveEngine`. They share **no base class, no interface**, no common config schema with `backend/strategies/`.

Cross-references:
- `backend/strategies/trading_strategies.py` is imported by `backend/organism/walk_forward.py` (offline) and `backend/services/multi_strategy_live_runner.py` (separate live path used by `multi_strategy_live` API/scheduler — partially competing with organism).
- `backend/organism/` modules do **not** inherit from `BaseStrategy`.

This is **conceptual duplication that costs bug-finding time**: two parallel test surfaces, two living-policy concepts (`backend/strategies/living_policy.py` vs organism's policy), two ways to be a "strategy" in the codebase.

`backend/api/routes/multi_strategy_live.py` and `services/multi_strategy_live_*` form a parallel tick-loop substrate. Memory.md does not document the relationship between this and the organism path.

---

## 11. Configuration sprawl

Distinct settings entry-points discovered:

| File | Purpose | Status |
|---|---|---|
| `backend/config/base_settings.py` | 12 pydantic `BaseSettings` classes + master `Settings` (1,745 LOC) | **Canonical** |
| `backend/config/settings.py` | Dataclass façade + back-compat re-exports | Active |
| `backend/config/unified.py` | `UnifiedSettings` pydantic | **Deprecated** (warns) |
| `backend/config/coordinator.py` | "Single point of access" | **Deprecated** (warns) |
| `backend/config/config.py` | Legacy module | Active |
| `backend/config.py` (top-level) | Compatibility shim that fakes `__path__` for the package | Active |
| `backend/settings.py` (top-level) | `SettingsProxy` with `__getattr__` forwarding | Active |

That is **7 different settings entry-points**, two of which are formally deprecated but still present, two of which are compatibility shims. Combined with **383 `os.getenv` calls** throughout `backend/` (only 9 files import from `backend.config.settings`), the result is that *most code* does not read settings through the canonical path.

Only **3 of 41** organism modules import from `backend.config` at all (`market_scanner`, `governance`, plus a couple via `kelly_sizer`); the rest go via `os.getenv` or local module-level constants. `live_engine.py` defines its own four `_env_*` helpers and 39 call sites.

---

## 12. Refactoring proposals — ranked by ROI

ROI = (impact on coupling/maintainability/test-surface) ÷ (effort).

### R-1 — Split `OrganismLiveEngine._live_tick_inner` into pipeline stages **[ROI: HIGH]**

**Effort:** 3-5 days
**Impact:** removes the largest single point of cognitive load in the codebase.

Each numbered step (0-12) becomes a small `Stage` class with a `run(ctx: TickContext) -> StageResult` method. `TickContext` is a dataclass that owns the per-tick scratch state (currently 100+ implicit `self._foo` writes). `OrganismLiveEngine` becomes an orchestrator (~200 LOC) that wires stages and feeds them context.

The work is *mostly mechanical* because the step boundaries are already commented. Bonus: stages become unit-testable in isolation (currently each test setup must instantiate the full engine).

Suggested initial split:
1. `HealthGuards` (steps 0, 0.5, 1, 1.1, 1.2, 1.3) — 4 small classes
2. `DataPipeline` (step 2 — fetch + features) + `RegimeStage` (step 3)
3. `ExitStage` (step 5 — 430 LOC, the most complex)
4. `EntryStage` (steps 6-9 — 1,050 LOC, the biggest win)
5. `LearningStage` (steps 10-11)
6. `PersistenceStage` (step 12)

After R-1, `live_engine.py` should be < 1,500 LOC.

### R-2 — Consolidate the seven config entry-points to one **[ROI: HIGH]**

**Effort:** 2-3 days
**Impact:** removes a confusion source that has caused real production gotchas (Memory.md notes "Paper compose gotcha: APP_ENVIRONMENT must be development not paper").

Steps:
1. Delete `backend/config/coordinator.py` and `backend/config/unified.py` (both already DeprecationWarning).
2. Make `backend/config.py` a real `__init__.py` move (or remove the shim and update affected imports).
3. Fold `backend/settings.py` into `backend/config/settings.py`.
4. Add a `LiveEngineConfig(BaseSettings)` so `live_engine.py`'s 21 module-level `_env_int`/`_env_str` constants come from one typed object.
5. Migrate `live_engine.py:_env_*` helpers to a shared `backend.config.env` module.

This does not require touching the 383 `os.getenv` call sites — that is a multi-week migration. It just removes the ambiguity about *which* settings module is canonical.

### R-3 — Split `OrganismBrain` into a serializer registry **[ROI: HIGH]**

**Effort:** 2 days
**Impact:** drops `brain_persistence.py` from 2,119 → ~800 LOC and surfaces the brain's actual schema (currently implicit across 26 `_save_X`/`_load_X` methods).

Pattern in §9 P-5. Each persisted concern becomes a `Serializer` class with `filename: str`, `save(target, source)`, `load(target) -> data`. The save/load symmetry becomes mechanical instead of hand-maintained.

### R-4 — Move `backend/organism/routes.py` to `backend/api/routes/organism.py` **[ROI: MEDIUM]**

**Effort:** half a day
**Impact:** restores the layering invariant. Currently this is the only `APIRouter` outside `backend/api/`.

Mostly an `mv` + `routes_setup.py` registration update. Strategy code does not call `organism/routes.py`, so cycles are not at risk.

### R-5 — Lift the alert-dispatch and atomic-write patterns into shared helpers **[ROI: MEDIUM]**

**Effort:** half a day
**Impact:** removes ~150 lines of repeated boilerplate; eliminates the "did you remember to wrap it in try/except + thread-dispatch" cognitive overhead at 16 sites.

- `backend/infra/alerting.py` adds `safe_alert(category, severity, msg, **ctx)` that owns the lazy import + try/except + thread dispatch.
- `backend/infra/atomic_io.py` (new) hosts `write_json_atomic(path, data)` + `write_text_atomic(path, text)`. Migrate `brain_persistence._write_json` callers + `diagnostic_scheduler` + the trade-history CSV writer.

### R-6 — Reconcile or retire the `backend/strategies/` framework **[ROI: MEDIUM-HIGH]**

**Effort:** 1-2 weeks (decision-heavy)
**Impact:** removes a large class of "wait, which strategy system is this?" confusion and ~4,800 LOC of partly-dead code.

Two paths:
- (A) **Retire** `backend/strategies/` framework entirely. The 15 `BaseStrategy` subclasses are not used in the organism live path; only `walk_forward.py` and the secondary `multi_strategy_live_runner` reference them. If those use cases can be served by organism scanners, delete the entire `backend/strategies/{trading_strategies,advanced_strategies}.py` (2,358 LOC).
- (B) **Promote** `BaseStrategy` to be the actual organism scanner interface. `AlphaScanner`, `BreakoutScanner`, `MeanReversionScanner` etc. would inherit from it. Provides a uniform plug-in surface.

Decision needed before refactor; either way, ROI is high once chosen.

### R-7 — Break the `api.routes.models ↔ ml.lifecycle` cycle **[ROI: LOW-MEDIUM]**

**Effort:** half a day
**Impact:** the only true cross-module circular dependency. Currently held together by lazy imports.

Move shared types/interfaces to a third module (`backend/ml/types.py`) that both can import. One-directional data flow restored.

### R-8 — Trim infra layer leaks **[ROI: MEDIUM]**

**Effort:** 1 day each
**Impact:** keeps the layering invariant honest.

- `infra/guardrails.py` → `services/guardrails.py` (it already calls `services.quote_manager`).
- `infra/outbox_worker.py` lazy import of `services.trading_execution_mode` → flip ownership: `services` module exposes a callback the worker uses.
- `integrations/alpaca_stream_production.py` → take `LotTracker` via constructor injection, not eager import.

### R-9 — Lazy-import audit pass **[ROI: LOW-MEDIUM]**

**Effort:** half a day
**Impact:** removes ~70 of 136 lazy imports in organism layer.

Sweep `live_engine.py`'s 43 lazy imports first — most are `dispatch_alert_from_thread` and `trading_phase` re-imports. Subsumed by R-5 for alerts; rest can move to top-of-file.

### R-10 — Apply `__all__` to organism modules **[ROI: LOW]**

**Effort:** half a day
**Impact:** narrows the public surface without behavioral risk; clarifies module contracts.

Of 41 organism modules, only 2 declare `__all__`. For each module, infer the actually-imported names from the public-surface scan in §8 and codify them.

---

## TL;DR

Architecture is **DAG-clean and shallow-inheritance** at the macro level — only one true cross-module circular dependency, no inheritance chain deeper than 3, no organism→api eager imports. Coupling is concentrated, not tangled.

The technical debt is concentrated in **two god-files** (`live_engine.py` 6,401 LOC with a single 2,510-line method, and `brain_persistence.py` 2,119 LOC with 48 methods on one class) and **one structural smell**: seven config entry-points with 383 `os.getenv` calls and 39 home-rolled `_env_*` calls inside `live_engine.py` alone. A secondary debt is *strategy-system duplication* — two parallel "strategy" frameworks (`backend/strategies/` template-method tree vs `backend/organism/` composition tree) that don't share a base class and are partly redundant.

---

## Synthesis

The architecture is **healthy where it most matters for safety**: layering between api/services/integrations/infra is mostly preserved (one organism→api leak, two infra→services leaks); the dependency graph is acyclic at the module level (one cross-module cycle held together by lazy imports); inheritance is universally shallow with composition correctly chosen for the live engine. Where it is loud is the **strategy core**: `OrganismLiveEngine` has absorbed every responsibility (37 methods, 104 attributes, 17 collaborators, a single 2,510-line tick method, 374-line `__init__`) and `OrganismBrain` mirrors that pathology on the persistence side (48 methods, 26 hand-paired save/load methods, every JSON file gets its own pair). Two systemic patterns repeat across the codebase and are now load-bearing in production code (`_now_fn` clock injection, `dispatch_alert_from_thread` boilerplate); these are cheap to consolidate. The single most leveraged refactor would be R-1 — decomposing the tick loop into a pipeline of stages with a shared `TickContext` — because the step boundaries are already commented, the work is mechanical, and it unlocks unit-testability for sub-stages that currently require booting the entire engine. After that, R-2 (settings consolidation) and R-3 (brain serializer registry) together cut ~3,000 LOC of repetitive plumbing without changing behavior.
