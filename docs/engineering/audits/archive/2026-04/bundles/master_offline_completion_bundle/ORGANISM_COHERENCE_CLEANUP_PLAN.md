# Organism Coherence Cleanup Plan

## Decisions for each dormant/dead/partial feature

### 1. Exploration routing (live_engine.py:2205-2235) → **REMOVE**
**Why**: ~30 lines of dead code routing candidates to a queue nobody processes. Comment explicitly says "no executor ever processed it." Confuses anyone reading the entry logic.
**Risk**: Zero — the code literally does nothing except log and `continue`.
**Timing**: Next cleanup commit. Not urgent.

### 2. runner.py → **REMOVE from lifespan loading**
**Why**: Legacy pre-scheduler orchestrator. Loaded in `lifespan.py:153-161` but never called by live_engine or scheduler. Creates false impression of an active orchestration layer.
**Risk**: Zero — `app.state.organism_runner` is never read by any live code path.
**Timing**: Next cleanup commit.

### 3. Nightly scheduler → **REVIVE LATER (post real-money Stage 1)**
**Why**: Designed for overnight model retraining, walk-forward validation, and candidate promotion. Currently disabled (`ORGANISM_NIGHTLY_ENABLED` not in .env). The organism retrains ML models intra-session via background_trainer, but the deeper overnight analysis (walk-forward + promotion) never runs.
**Risk of reviving now**: Medium — could introduce untested model promotion into a system that's still finding its edge.
**Decision**: Keep dormant through Stage 1. Revive when the organism has 500+ trades and the background trainer has proven stable.
**What to do now**: Nothing. Document that it exists and why it's off.

### 4. Promotion pipeline → **KEEP DORMANT (tied to nightly scheduler)**
**Why**: Only fires after nightly training completes. If nightly scheduler is dormant, promotion is dormant.
**Decision**: Revive together with nightly scheduler.

### 5. training.py orchestrator → **KEEP DORMANT (tied to nightly scheduler)**
**Same reasoning**: Used only by nightly_scheduler. Dormant until nightly is revived.

### 6. Self-evolution activation at 300 trades → **KEEP ACTIVE but MONITOR**
**Why**: The system is 7 trades from crossing this threshold. Evolution was intentionally frozen for the first 300 trades to prevent premature parameter drift. The design intent is to activate it. The current `evolved_params.json` values are reasonable (inspected in the audit). No parameter is dangerous.
**Risk**: Parameter changes could affect entry/exit behavior. But the system has been running on the SAME hardcoded parameters since inception, and evolution was the designed next step.
**Decision**: Allow activation. Monitor the first 2 sessions after trade 300 for behavioral changes. See Prompt 5 (PRE_300 audit) for details.

### 7. Scattered constants → **SIMPLIFY LATER**
**Why**: Thresholds are defined in 6+ files with no central config. Changing one requires finding related values elsewhere. This is technical debt, not a bug.
**Decision**: BACKLOG. Create a `config.py` or `constants.py` when doing a major refactor. Not urgent for real-money prep.

### 8. composite_indicators.py → **KEEP (it IS used)**
**Why**: The coherence audit initially flagged it as dead, but it's imported and called by ml_features.py:380-384. It contributes composite technical indicators to the feature matrix.
**Decision**: Keep. No action needed.

### 9. ensemble_models.py → **KEEP as soft optional**
**Why**: Provides an ensemble blend if available, falls back to single XGB gracefully. Zero risk when absent. May add value later with more training data.
**Decision**: Keep as-is. Evaluate utility after 500+ trades.

### 10. walk_forward.py → **KEEP DORMANT (tied to nightly)**
**Why**: Used only for offline validation in the training orchestrator. Live gating uses the simpler `brain.walk_forward_gate()`. The full walk-forward is a deeper analysis tool.
**Decision**: Dormant until nightly scheduler is revived.

## Summary table

| Item | Decision | Priority | Effort |
|---|---|---|---|
| Exploration routing | **REMOVE** | Next cleanup | 5 min (delete 30 lines) |
| runner.py loading | **REMOVE** | Next cleanup | 5 min (remove 4 lines from lifespan) |
| Nightly scheduler | **REVIVE LATER** (post Stage 1) | After 500 trades | Medium |
| Promotion pipeline | **DORMANT** (tied to nightly) | After nightly | — |
| training.py | **DORMANT** (tied to nightly) | After nightly | — |
| Self-evolution at 300 | **KEEP ACTIVE, MONITOR** | Imminent (7 trades) | Monitor only |
| Scattered constants | **BACKLOG** | Later refactor | Medium |
| composite_indicators | **KEEP** (actually used) | — | — |
| ensemble_models | **KEEP** (soft optional) | — | — |
| walk_forward.py | **DORMANT** (tied to nightly) | After nightly | — |
