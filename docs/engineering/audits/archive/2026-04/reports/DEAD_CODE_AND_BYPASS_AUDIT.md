# Dead Code and Bypass Audit

**Date**: 2026-04-23 | **Live**: `ce06d41` | **HEAD**: `33d6138` | **Scope**: `backend/organism/**`, config, scripts

Hunting for: duplicate logic, split source-of-truth, scattered constants, dead routing, stale flags, hidden bypasses, dangerous defaults, log-level hiding of failures, TODO/HACK/FIXME with correctness impact.

All findings are triaged P0/P1/P2/P3 and classified by category.

---

## Severity legend
- **P0** — correctness / risk blocker; resolve before any deploy
- **P1** — hidden bypass, silent failure, or correctness drift under realistic conditions
- **P2** — architectural drift; correctness risk over releases
- **P3** — technical debt; cleanup

---

## FINDINGS

### D-01 | P0 | risk | Drawdown kill 4× more permissive in container than code default

- **Evidence**: `governance.py` default `ORGANISM_DRAWDOWN_KILL_PCT=0.05`; `.env` / container env sets `0.20`. Runtime wins.
- **Impact**: Kill switch at 20% equity drawdown instead of 5%. A code reader expects −5% auto-halt; runtime tolerates −20% before halting. **4× the permissible drawdown** before protective cooldown.
- **Action**: Decide canonical value (0.05 for tiny pilot, 0.10–0.15 for larger). Add startup validator that logs WARN if `resolved[k] / default[k] > 1.5` for any risk parameter.

---

### D-02 | P0 | mechanical | Uncommitted worktree reverts Exp4 + G3 backward toward live

- **Evidence**: `git diff HEAD`:
  - `backend/organism/adaptive_exits.py`: −43 lines of Exp4 chop-trail widen/disable logic; restored to pre-Exp4 standard lookup
  - `backend/organism/pyramider.py`: −8 lines (G3 NaN guard: `if not math.isfinite(current_price) or current_price <= 0: return PyramidAction("none")`)
  - `scripts/generate_experiment_observation_report.py`: −80 lines (giveback section)
  - `monitoring/memory_monitoring.json`: threshold edit
- **Impact**:
  - No single commit describes "what's running". Any rebuild from worktree ships ambiguous code.
  - Exp4 loss of MFE giveback reduction — the $195/5-session leak persists.
  - G3 loss of silent-NaN pyramid disable — rare but could occur on streaming hiccup.
- **Action**: Resolve before anything else. Two options:
  1. `git restore backend/organism/adaptive_exits.py backend/organism/pyramider.py scripts/generate_experiment_observation_report.py monitoring/memory_monitoring.json` → returns to HEAD-clean
  2. `git add` + commit with explicit reason like "revert Exp4 + G3 to align with observational stability plan"
- **Recommended**: Option 1 (restore). Exp4 and G3 were added for reasons; reverting quietly creates future confusion.

---

### D-03 | P0 | edge / algorithm | Negative expectancy lifetime (−$1.92/trade)

- **Evidence**: `TRADING_EDGE_BASELINE_REPORT.md`; `PLATFORM_STATE_SNAPSHOT_APR23.md §15`.
- **Impact**: Platform is mechanically ready but algorithmically unprofitable. Real money blocked.
- **Action**: Ship Exp4 (chop-trail widen) after bundling the hardening commits; run 5–10 more paper sessions; evaluate.

---

### D-04 | P1 | architecture | Confidence authority split across 3 modules

- **Evidence**:
  - `ml_signal.py:486` — `_compute_effective_confidence()` (canonical per docstring)
  - `alpha_scanner.py:157` — uses `effective_confidence` if >0 else raw
  - `kelly_sizer.py:110` — `_ML_CONFIDENCE_MIN = 0.5` standalone threshold
  - `live_engine.py:2170–2184` — explicit weight blend (production or learning)
- **Impact**: If `_compute_effective_confidence`'s empirical precision bin is stale, alpha_scanner and kelly_sizer diverge. Four independent readers of the same concept.
- **Action**: Single authority in `ml_signal`. `kelly_sizer` and `alpha_scanner` consume from signal_gen. Docstring in `ml_signal` declares "effective_confidence is canonical blend".

---

### D-05 | P1 | structural | Exploration half-removed (flag + routing remain, execution gone)

- **Evidence**:
  - Comment `# 9b. EXPLORATION BUCKET — REMOVED` at `live_engine.py:2624`
  - Flag read `EXPLORATION_ENABLED = _env_bool("ORGANISM_EXPLORATION_ENABLED", False)` at line 186
  - Routing block `_route_exploration = ...` at lines 2241–2261
  - `ORGANISM_EXPLORATION_ENABLED=false` in runtime env
- **Impact**: Misleading for maintainers. Setting flag true has no effect. `_route_exploration` flag is set but not consumed.
- **Action**: Delete:
  - `EXPLORATION_ENABLED` global
  - The `_route_exploration` block (lines 2241–2261)
  - `_exploration_rejects` tracking list in `kelly_sizer.py`
  - Doc: move "exploration has been removed" to a single README entry in organism module.

---

### D-06 | P1 | architecture | Learning-mode threshold declared in two modules

- **Evidence**:
  - `kelly_sizer.py:198` `_RISK_BUDGET_TRADE_THRESHOLD = 200`
  - `alpha_scanner.py` `learning_mode` parameter (threshold 200 implicitly)
  - `live_engine.py:564–567` `_is_learning_mode` property
- **Impact**: If one module says trades < 200 and another says trades ≥ 200, gates and sizing disagree on which formula is authoritative.
- **Action**: Extract to `governance.py` or `OrganismConfig`; one source, all consumers read it.

---

### D-07 | P1 | ops | Alerting wired at HEAD (`33d6138`) but NOT in live container

- **Evidence**: Commit `33d6138` adds `backend.infra.alerting.send_alert()` hooks in `diagnostic_scheduler.py:194+`, `brain_persistence.py:297+`, `ml_signal.py:357+`. Image built at `ce06d41`.
- **Impact**: "Critical" events (brain-save guard fire, feature-drift, pre-open fail) log locally but **never page anyone**.
- **Action**: Deploy hardening bundle + set `SLACK_WEBHOOK_URL` in `.env`.

---

### D-08 | P1 | risk | Per-trade notional + daily max-loss env-gated default-off

- **Evidence**: Commit `bb5cbb5`. Code reads `ORGANISM_MAX_NOTIONAL` and `ORGANISM_MAX_DAILY_LOSS` envs; default 0 = disabled.
- **Impact**: Even if `bb5cbb5` deploys, without envs set the circuit-breakers are inert.
- **Action**: Deploy + set both envs to non-zero values before first real-money tick. Recommend `ORGANISM_MAX_NOTIONAL=2500`, `ORGANISM_MAX_DAILY_LOSS=500` for $5k Stage-1 pilot.

---

### D-09 | P1 | mechanical | NaN pyramid guard G3 reverted in worktree

- **Evidence**: `pyramider.py` diff — `math.isfinite(current_price)` check removed.
- **Impact**: If streaming provider injects NaN into current_price, NaN comparisons are silently False, and pyramid logic disables with no log. G3 added explicit early-return.
- **Action**: Decide keep / remove. Recommend KEEP (low-cost defensive guard). If keeping, restore worktree to HEAD.

---

### D-10 | P1 | structural | Fitness gate split — telemetry static vs live dynamic

- **Evidence**:
  - `decision_telemetry.py:45` — `fitness_gate: float = 0.45` (static dataclass default)
  - `live_engine.py:2916` — `0.45 if (not learning_mode and _sym_tc >= 10) else 0.0`
- **Impact**: Operator dashboards show `effective_fitness_gate=0.45` while actual runtime used 0.0. Hides true rejection count / reason.
- **Action**: Pass computed gate to telemetry; remove static default.

---

### D-11 | P2 | algorithm | Calibration map reset on every retrain

- **Evidence**: `ml_signal.py:202` — calibration map is instance field, NOT persisted.
- **Impact**: After retrain, one-epoch uncalibrated window; `effective_confidence` falls back to raw → may be overstated.
- **Action**: Persist map to brain. On retrain, blend: `new_cal = 0.5 * old + 0.5 * recomputed`. Or load from brain on retrain.

---

### D-12 | P2 | algorithm | Ensemble predict_proba silently falls back to 0.5

- **Evidence**: `ensemble_models.py:281` — bare `except Exception: results[name] = 0.5`.
- **Impact**: If a model is broken (corrupt joblib, missing dependency), confidence silently returns 0.5 — **neutral/ambiguous**. No alert. Downstream proceeds with degraded signal.
- **Action**: `except Exception as e: logger.error("model %s crashed: %s", name, e); raise` or at minimum `logger.error` + mark model unhealthy.

---

### D-13 | P2 | algorithm | Regime PSI silent-zero on exception

- **Evidence**: `regime.py:606–609` — bare `except Exception: return 0.0`.
- **Impact**: If PSI calculation fails (e.g., Inf in histogram), returns 0.0 = "no regime shift detected". System continues assuming stability.
- **Action**: Log warning with histogram shape / values before returning 0.0. Or raise.

---

### D-14 | P2 | ops | Governance state transitions have no audit log

- **Evidence**: `governance.py:102–116` — `freeze()`, `unfreeze()`, `halt_trading()`, `resume_trading()` mutate state without before/after snapshots or caller context.
- **Impact**: If org is frozen in production, no log of who triggered or why.
- **Action**: Wrap state transitions with `logger.critical("Freeze triggered", extra={"before": ..., "after": ..., "caller": ...})`. Append to a governance audit log.

---

### D-15 | P2 | structural | Kelly drawdown floor can invert cutoff

- **Evidence**: `kelly_sizer.py:550–561` — no validation that `drawdown_floor < max_drawdown_cutoff`.
- **Impact**: Pathological constructor call (floor=0.3, cutoff=0.2) makes risk scale 1.0 at max drawdown — opposite of intended.
- **Action**: Add `__post_init__` assertion.

---

### D-16 | P2 | structural | Four regime tables with no sync guarantee

- **Evidence**: `adaptive_exits.py:130–181` — `REGIME_STOP_ATR`, `REGIME_TRAIL_ATR`, `REGIME_TP_R`, `REGIME_MAX_BARS` are independent dicts.
- **Impact**: If a new regime label is added elsewhere (e.g., `recovery`), these tables silently fall back to defaults. No error.
- **Action**: Single `RegimeConfig` dataclass; validate at init that all RegimeDetector labels have entries in all tables.

---

### D-17 | P2 | structural | Evolved-params application lacks version tag

- **Evidence**: `live_engine.py:2665–2668` pushes evolved params into `AdaptiveExitEngine` by manual scale. No generation/version stamp.
- **Impact**: If evolution freezes/unfreezes, stale-base scaling may persist. Hard to debug.
- **Action**: Add `params_generation` to evolved_params; engines reject stale versions or log warning.

---

### D-18 | P2 | ops | Decision telemetry uses stale defaults for some gates

- **Evidence**: See D-10. Also confidence_gate defaults to 0.40 in telemetry while actual runtime may be 0.25 (learning) or 0.45 (defensive).
- **Action**: Pass computed gates to telemetry constructor.

---

### D-19 | P3 | structural | Background trainer force-reset mutates private state

- **Evidence**: `live_engine.py:2655–2656` — directly sets `_bg_trainer._is_training = False` and `_future = None` if stuck.
- **Impact**: Unsafe mutation; orphaned resources if training thread still running.
- **Action**: Add `reset()` method on background trainer; call public API.

---

### D-20 | P3 | structural | Universe selector protects open-position symbols only

- **Evidence**: `universe_selector.py:91` — protected set checked in rotate only when symbol has open position.
- **Impact**: Protected symbol can be rotated out when flat if fitness decays.
- **Action**: Clarify contract. Either protect always, or rename parameter.

---

### D-21 | P3 | ops | `/organism/train` returns untyped dict; silent partial failures

- **Evidence**: `routes.py:190–195` — result dict not validated.
- **Impact**: Training crash in background_trainer silently returns `{}`; caller can't distinguish.
- **Action**: Typed `TrainResponse`.

---

### D-22 | P3 | ops | Observation tooling for exploration was promised but not delivered

- **Evidence**: `live_engine.py:2261–2266` comment references "improve9 A7: Log exploration-eligible candidates" — no log line.
- **Action**: Delete comment (exploration is dead) OR add the log if feature is ever re-introduced.

---

### D-23 | P3 | structural | `_exploration_rejects` tracked but never acted on

- **Evidence**: `kelly_sizer.py:134–135` appends; `live_engine.py:2308` reads for telemetry only.
- **Action**: Remove if unused OR wire a spike alert.

---

### D-24 | P3 | ops | `ORGANISM_EXPLORATION_ENABLED` read but never consumed

- **Evidence**: `live_engine.py:186`. Covered by D-05.

---

### D-25 | P3 | docs | 90+ untracked `*_REPORT.md` at repo root

- **Evidence**: `git status --short` output.
- **Impact**: Cognitive clutter; operator cannot distinguish current-cycle reports from archival.
- **Action**: Move historical reports into `docs/engineering/reviews/` or `docs/engineering/post_close/`. Keep only 5–10 most recent at root. (Low priority; does not affect correctness.)

---

## DUPLICATE CONSTANTS (not triaged individually; P2 collectively)

| Constant | Locations | Recommendation |
|---|---|---|
| `LEARNING_MODE_TRADES = 200` | live_engine (implicit), kelly_sizer (`_RISK_BUDGET_TRADE_THRESHOLD`), alpha_scanner (param) | Single source in `governance.py` |
| `EVOLUTION_FREEZE_TRADES = 300` | live_engine | OK (single) |
| `ALPHA_TOP_N = 5` | live_engine env, alpha_scanner constructor | env → wired (OK) |
| `MAX_OPEN_POSITIONS = 8` | live_engine env, sector gate | env → wired (OK) |
| `inverse_etfs = ["DOG","PSQ","RWM","SH"]` | config, live_engine, alpha_scanner | Confirm single source |
| `REGIME_*` tables | adaptive_exits (4 tables) | Merge into RegimeConfig |
| confidence weights | live_engine 2170–2184, alpha_scanner | Single authority — see D-04 |

---

## DANGEROUS DEFAULTS / INVERSIONS

| Parameter | Default | Runtime | Delta | Fix |
|---|---|---|---|---|
| `drawdown_kill_pct` | 0.05 | 0.20 | **+300% permissive** | D-01 |
| `max_changes_per_day` | 100 | 500 (per D-08 context) | +400% | low priority |
| `_ML_CONFIDENCE_MIN` | 0.5 | 0.5 (hardcoded) | — | OK |
| `risk_budget_production` | 0.0025 | 0.0025 | — | OK |
| `SLACK_WEBHOOK_URL` | (none) | (none) | — | **Set before deploy** |
| `ORGANISM_MAX_NOTIONAL` | 0 (disabled) | 0 (disabled) | — | **Set to $2500** for Stage 1 |
| `ORGANISM_MAX_DAILY_LOSS` | 0 (disabled) | 0 (disabled) | — | **Set to $500/day** for Stage 1 |

---

## SILENT-FAILURE LOG LEVELS

| Site | Current | Should be |
|---|---|---|
| `ensemble_models.py:281` | `except: results[name] = 0.5` | `logger.error`, re-raise or mark unhealthy |
| `regime.py:606` | `except: return 0.0` | `logger.warning` with context |
| `governance.py:102–116` | silent state change | `logger.critical` with before/after/caller |
| `live_engine.py:2655` | private mutation | public API |
| `pyramider.py` (HEAD has G3) | — | KEEP G3 |

---

## TOP 5 TO FIX NOW (BEFORE ANY DEPLOY)

1. **D-02** — resolve worktree (P0 mechanical)
2. **D-01** — decide canonical drawdown_kill_pct + startup validator (P0 risk)
3. **D-07 + D-08** — deploy alerting + risk caps with envs set (P1 ops/risk)
4. **D-05** — remove exploration dead code (P1 structural)
5. **D-04 + D-06** — unify confidence and learning-mode authority (P1 architecture)

— End of Dead Code and Bypass Audit —
