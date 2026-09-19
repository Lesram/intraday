# Live Full-Brain-Save Route Discovery

**Date:** 2026-04-08 UTC
**Mode:** READ-ONLY. No container restart, no rebuild, no POST calls during this task, no docker exec python.
**Goal:** Determine whether the existing running codebase exposes any route that can trigger a FULL brain save — specifically writing `ml_classifier.joblib`, `ml_regressor.joblib`, `reference_feats.csv`, and `evolved_params.json` — from the live in-process engine, without deploying new code.

## Executive Answer

**NO CLEAR SAFE ROUTE EXISTS.**

Every call path that ultimately writes ML joblibs funnels through `BrainPersistence.save()`, which is gated by the walk-forward regression check in `live_engine._save_brain()`. There is no pre-existing bypass. The live engine's current walk-forward state (`current_sharpe=-0.791` vs `best_sharpe` decayed to ~0.011 in `BrainPersistence._manifest`, with the real learner best of 2.8956 held only in `learner.state`) guarantees every gate evaluation fails, so the full save code path never runs, so `_save_ml_models()` never executes.

## Call Tree — The Only Path to ML Joblibs

```
<route handlers that touch live engine>
  │
  └─→ LiveEngine._save_brain()                         backend/organism/live_engine.py:4279
        │
        ├─ self.brain.walk_forward_gate(...)           line 4296
        │     └─ if not should_save: return            line 4301  ← ALL GATED PATHS STOP HERE
        │
        └─ self.brain.save(...)                        line 4334  ← ONLY CALL SITE in entire repo
              │
              └─ BrainPersistence.save()               backend/organism/brain_persistence.py:238
                    │
                    └─ self._save_ml_models(tmp, sig)  line 278   ← ONLY CALL SITE for _save_ml_models
                          │
                          └─ secure_dump_to_path(
                                signal_gen._clf,
                                target/"ml_classifier.joblib")   line 622-624
                                signal_gen._reg,
                                target/"ml_regressor.joblib")    line 625-627
```

**Hard constraint:** `_save_ml_models()` is called exactly once in the entire backend (verified by grep `_save_ml_models\(`), and that call is inside `BrainPersistence.save()` at line 278. `BrainPersistence.save()` is called exactly once in the entire backend (verified by grep `\.brain\.save\(|brain_persistence\.save\(|BrainPersistence.*save`), and that call is inside `live_engine._save_brain()` at line 4334. Both are downstream of the walk-forward gate at line 4301.

## All Callsites of `_save_brain()`

| File | Line | Context | Callable from a running route? | Gated by walk-forward? |
|---|---:|---|---|---|
| `live_engine.py` | 1112 | `LiveEngine.shutdown()` — graceful shutdown | Only on container stop | Yes (line 4296) |
| `live_engine.py` | 2644 | Inside `live_tick()` every 20 ticks | Via `POST /organism/tick` | Yes |
| `live_engine.py` | 3861 | After fills recorded (`if closed:`) | Only when real fills settle | Yes |

**None bypass the walk-forward gate.** All three enter `_save_brain()` at line 4279, hit the gate at line 4296, and fall into the gated `save_essential_state` path (line 4307) if the gate fails. The gated path deliberately does NOT call `_save_ml_models` — per `brain_persistence.py:538–539` the joblibs are documented as "only on gate pass".

## POST Route Candidates (from `backend/organism/routes.py`)

### 1. `POST /api/v1/organism/tick` — line 299
**What it does:** Calls `engine.live_tick()` on the running engine instance, which may call `_save_brain()` every 20 ticks (line 2643: `if self._tick_count % 20 == 0`).
**Runs in live process:** ✅ yes.
**Bypasses gate:** ❌ no (`_save_brain` → walk_forward_gate).
**Writes joblibs:** ❌ no (gate fails).
**Already proven empirically**: 10 POSTs executed during the prior recovery step. 9th hit `tick_count=6760`, `brain_saved=true`, but only runtime-truth files were written. Joblibs remained missing. Manifest stayed inconsistent on `generation/best_sharpe/ml_is_trained/feature_count`.
**Safety rank:** SAFE to call (proven), but insufficient for full recovery.

### 2. `POST /api/v1/organism/train` — line 189
**What it does:** Calls `_run_nightly_tick(app)` (`nightly_scheduler.py:34`), which instantiates `TrainingOrchestrator(sessionmaker, governance)` and calls `orchestrator.run_training(source="nightly", current_weights=...)`.
**Runs in live process:** ✅ yes — same process.
**But:** This is the **"slow brain" training loop** — a completely separate code path that:
  - Pulls fills from the DB via `sessionmaker`
  - Produces a new candidate weights dict
  - Evaluates the candidate via its own walk-forward check
  - If accepted, hands it to `promotion.begin_promotion(...)` (shadow stage)
  - Does NOT touch `live_engine.signal_gen`, `live_engine.learner`, or `live_engine._save_brain()`
  - Does NOT call `brain.save()` or `_save_ml_models()`
**Writes joblibs:** ❌ NO. Confirmed by grep: `nightly_scheduler.py` and `training.TrainingOrchestrator` have zero calls to `brain.save` or `_save_ml_models`. The "training" here is candidate weight production for the promotion pipeline, not fitting the live ML classifier/regressor.
**Bypasses gate:** Irrelevant — doesn't reach the ML save path at all.
**Side effects:** Produces a candidate in the promotion shadow pipeline. May mutate `app.state.organism_promotion` state. Could trigger a policy rollout if the candidate is promoted by the separate promotion loop later.
**Safety rank:** MEDIUM — benign in isolation but introduces candidate state into the promotion pipeline, which is an unintended side effect for a recovery task. Does NOT help recover ML joblibs.

### 3. `POST /api/v1/organism/promote` — line 229
**What it does:** Calls `promotion.evaluate_and_advance({})`. Advances an already-queued candidate through the promotion stages.
**Runs in live process:** ✅ yes.
**Writes joblibs:** ❌ no (no call to `brain.save`).
**Safety rank:** RISKY — mutates promotion state, returns 404 if no candidate queued.

### 4. `POST /api/v1/organism/rollback` — line 243
**What it does:** Rolls back a promotion candidate.
**Writes joblibs:** ❌ no.
**Safety rank:** RISKY — mutates promotion state.

### 5. `POST /api/v1/organism/freeze` / `/unfreeze` / `/halt` / `/resume` — lines 197/205/213/221
**What they do:** Toggle governance flags only (`gov.freeze()`, `gov.unfreeze()`, etc.).
**Writes joblibs:** ❌ no.
**Safety rank:** SAFE but irrelevant.

### 6. `POST /api/v1/organism/compute-attribution` — line 264
**What it does:** Triggers fresh attribution computation from DB sessions. Writes to an attribution store.
**Writes joblibs:** ❌ no.
**Safety rank:** MEDIUM — DB writes, irrelevant to this recovery.

### 7. `POST /api/v1/organism/close-shorts` — line 547
**What it does:** Forces close of legacy short positions.
**Writes joblibs:** ❌ no. Also places orders — dangerous side effect.
**Safety rank:** HIGH RISK — do NOT call.

### 8. `POST /api/v1/organism/cleanup-orders` — line 610
**What it does:** Cleans up stuck orders.
**Writes joblibs:** ❌ no.
**Safety rank:** MEDIUM.

### 9. `POST /api/v1/organism/diagnostics/run` — line 810
**What it does:** Runs deep diagnostics.
**Writes joblibs:** ❌ no (read-only diagnostic).
**Safety rank:** SAFE but irrelevant.

## Walk-Forward Gate Bypass Search

Searched for any path that could bypass the gate:
- `grep -rn 'walk_forward' backend/` — referenced only in `brain_persistence.py` (the gate itself) and `live_engine.py:4296` (the single caller). No "skip gate" flag, no `force=True` parameter, no debug bypass.
- `grep -rn 'force.*save|bypass.*gate|skip.*gate' backend/organism/` — no matches.
- `BrainPersistence.save()` signature (line 238): no `force` parameter. Atomic two-phase write; takes everything through `_save_ml_models`.

**There is no pre-existing code path that bypasses the walk-forward gate to write ML joblibs.** The only way to cause `_save_ml_models()` to run in the current running image is to make the gate return `should_save=True`. Since the gate compares `current_sharpe` (−0.791) against `best_sharpe` (either the decayed 0.011 in `_manifest` or the 2.8956 in `learner.state`, depending on which the gate reads), and since the current sharpe is negative from today's losing session, **no same-day gate evaluation will pass without a code patch**.

## Additional Observation: Container Graceful Shutdown

`LiveEngine.shutdown()` at `live_engine.py:1108` calls `_save_brain()` on graceful shutdown. This is still gated. So even a clean `docker compose stop` would NOT persist ML joblibs — and any restart loses the in-memory models.

## Summary Table

| Route | In-process | Calls `_save_brain`? | Bypasses gate? | Writes joblibs? | Safety |
|---|:---:|:---:|:---:|:---:|:---:|
| `POST /organism/tick` | ✅ | ✅ (every 20 ticks) | ❌ | ❌ | SAFE (already used) |
| `POST /organism/train` | ✅ | ❌ | n/a | ❌ | Medium (wrong path) |
| `POST /organism/promote` | ✅ | ❌ | n/a | ❌ | Risky |
| `POST /organism/rollback` | ✅ | ❌ | n/a | ❌ | Risky |
| `POST /organism/freeze,unfreeze,halt,resume` | ✅ | ❌ | n/a | ❌ | Safe (irrelevant) |
| `POST /organism/compute-attribution` | ✅ | ❌ | n/a | ❌ | Medium (irrelevant) |
| `POST /organism/close-shorts` | ✅ | ❌ | n/a | ❌ | HIGH RISK |
| `POST /organism/cleanup-orders` | ✅ | ❌ | n/a | ❌ | Medium |
| `POST /organism/diagnostics/run` | ✅ | ❌ | n/a | ❌ | Safe (irrelevant) |
| `POST /organism/compute-attribution` | ✅ | ❌ | n/a | ❌ | Medium (irrelevant) |

## Is There Any Existing Safe Route to Recover ML Artifacts Without Redeploy?

**NO.** Every path to `_save_ml_models()` is gated by the walk-forward check that is guaranteed to fail with today's sharpe. No route exposes a `force=True` / `skip_gate` flag. No promotion / train / tick path touches the live signal_gen ML objects in a way that writes joblibs.

## Implications / What This Means for Recovery

To write `ml_classifier.joblib` and `ml_regressor.joblib` from the live in-process engine you must either:

1. **Wait for the walk-forward gate to pass naturally.** Requires the live `current_sharpe` (from the last 100 trades) to recover above ~0.95× of `best_sharpe`. With `best_sharpe=2.8956` (from `learner.state`, if the gate reads that source) or `best_sharpe=0.011` (from `_manifest`, if it reads that), this will not happen during pre-open and is uncertain post-open.

2. **Patch a narrow code change** (which is out of scope for this read-only task): add a `force: bool = False` parameter to `BrainPersistence.save()` OR add a new admin route `POST /organism/save?force=true` that calls `engine.brain.save(...)` directly, skipping the gate. This would ship via a controlled rebuild.

3. **Accept the risk** and leave the ML models in-memory only until (a) the market open first tick produces a positive-sharpe run that passes the gate, or (b) an admin bypass path is added via a controlled patch.

## Files Referenced

- `backend/organism/routes.py` — route definitions (lines 104, 137, 150, 164, 189, 197, 205, 213, 221, 229, 243, 264, 284, 299, 338, 362, 396, 470, 495, 547, 610, 665, 683, 704, 724, 741, 774, 788, 810)
- `backend/organism/live_engine.py` — `_save_brain` (4279), gate check (4296), `brain.save` call (4334), `shutdown` (1108), `live_tick` save (2644), post-fill save (3861)
- `backend/organism/brain_persistence.py` — `save` (238), `_save_ml_models` call (278), `_save_ml_models` def (620), `save_essential_state` (507)
- `backend/organism/nightly_scheduler.py` — `_run_nightly_tick` (34)
- `backend/utils/secure_pickle.py` — `secure_dump_to_path` (185)

## Method

All evidence collected via host-side `grep` against the repo and `Read` of specific line ranges. No container POST calls issued during this task. No imports, no docker exec python. No file mutations.
