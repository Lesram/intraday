# Codebase Coherence Audit (S16)

**Question:** Are we all clear on the codebase?
**Answer:** Mostly. ~7 dormant modules carry cost without value; live_engine.py is too big (5050 LOC); a few historical "Phase" markers don't match current architecture; the rest is coherent.

---

## Module size inventory (organism core)

| File | LOC | Notes |
|---|---|---|
| `live_engine.py` | **5050** | TOO BIG — 36 methods. Should split. |
| `brain_persistence.py` | 1869 | Large but justified — handles save/restore + F1-F4 hardening |
| `self_evolution.py` | 1247 | OK — evolution logic is intrinsically branched |
| `routes.py` | 865 | OK — many admin/diagnostic endpoints |
| `ml_signal.py` | 862 | OK |
| `diagnostic_checks.py` | 848 | OK |
| `adaptive_exits.py` | 754 | OK |
| `replay_simulator.py` | 741 | After S7 hardening; still coherent |
| `regime.py` | 697 | OK |
| `kelly_sizer.py` | 682 | OK |
| `background_trainer.py` | 591 | OK |
| `transfer_learning.py` | 581 | **DORMANT** (see below) |
| ... | | |

---

## Dormant modules — imported but never instantiated/called

These modules exist in the codebase, are imported somewhere, but their main classes/functions are never actually constructed or executed:

| Module | What it claims to do | Status | Recommendation |
|---|---|---|---|
| `transfer_learning.py` (581 LOC) | `TransferLearningEngine` for warm-start | Imported in `live_engine.py`. **Never instantiated** anywhere. Per CLAUDE.md memory, transfer-learning was gated by H4 freeze gate. | **Delete or document as unused.** Net cost: 581 LOC of confusion. |
| `attribution.py` (421 LOC) | `AttributionService` for trade attribution | Imported in `routes.py` (twice) and `training.py`. **Never instantiated** anywhere. | **Delete or refactor** to make it actually useful. Currently it's a museum piece. |
| `walk_forward.py` (466 LOC) | `WalkForwardEvaluator` + `AcceptanceGates` for offline strategy validation | Imported in `training.py`. **Never instantiated** anywhere. | Per its own docstring: "OFFLINE-ONLY... not used in the live model promotion path." Still: nothing references the offline path either. **Delete unless you have a plan.** |
| `training.py` (358 LOC) | `TrainingOrchestrator` for end-to-end training | Imported in `nightly_scheduler.py`. **Never instantiated.** | Likely dormant — same status as walk_forward. |
| `feature_store.py` (NN LOC) | `VersionedFeatureStore` | Imported in `live_engine.py` and `training.py`. **Never instantiated.** | Dormant. |
| `multi_timeframe.py` (NN LOC) | `add_multi_timeframe_features` | Imported in `live_engine.py`. **Never called.** | Dormant. |
| `promotion.py` (412 LOC) | `PromotionController` + `RollbackTrigger` for canary deployment | Imported in `nightly_scheduler.py`, `routes.py`, `lifespan.py`. **Never instantiated.** | Dormant. Was probably wired for a "canary deploy then promote" flow that never went live. |

**Total dormant LOC: ~3,000 lines** (estimating). That's about 15% of `backend/organism/`. They cost cognitive load (every reader has to figure out "is this used?") and risk (someone might wire one in by mistake).

### Active counterparts (verified)

For comparison, these were dormant-suspects but ARE actually live:

| Module | Active because |
|---|---|
| `ensemble_models.py` | `EnsemblePredictor` instantiated in `ml_signal.py:213`, used at inference `ml_signal.py:407` |
| `nightly_scheduler.py` | `start_organism_nightly_scheduler` called from `lifespan.py:169` |
| `runner.py` | `OrganismRunner` instantiated in `lifespan.py:160` |
| `decision_telemetry.py` | Imported and used in `live_engine.py` |
| `diagnostic_checks.py` + `diagnostic_scheduler.py` + `diagnostics.py` | All wired into the live engine via scheduler |

---

## Code-comment mismatches and historical residue

### `is_exploration` field — ghost of removed feature

Locations: `continuous_learner.py:191`, `brain_persistence.py:528, 1165, 1739`, `live_engine.py:3912, 3959, 3980, 4037`.

CLAUDE.md notes: *"Exploration: Fully removed — no execution path exists."* Per `improve9` H1 hardening.

But the `is_exploration` field still exists on `TradeRecord`, gets serialized to/from brain, gets read in 4 places in live_engine, gets passed through. **It always reads False**. Unused field, ~50 LOC of plumbing.

**Recommendation:** delete the field and the `_is_exploration` parameters. ~50 LOC simplification, zero behavior change.

### "Phase 4.4 / 4.5 / 4.6" references in code

Locations: `ensemble_models.py`, `ml_signal.py:209, 307, 404`, `self_evolution.py:119, 125, 348, 351, 914, 982`.

These reference `improve3-9.md` planning documents that are months old. Live code still says "Phase 4.4: Ensemble expansion" — the comment is fine but readers don't know what "Phase 4.4" was supposed to be.

**Recommendation:** either update comments to reference current architecture, or annotate *"Phase 4.4 = ensemble was added; see docs/architecture/improve3-9.md for context."* Not blocking but mild rot.

### `# queue was dead code — no executor ever processed it`

Location: `live_engine.py` near where exploration was removed.

This comment is honest! It documents prior dead code that was removed. Good. Keep this style; it's the right pattern.

### Half-finished implementations / `pass` blocks

Found 13 `pass`-only or `...`-only code blocks in `backend/organism/`. Inspected the worst:

- `scheduler.py:26 (...)` — abstract Protocol body. Fine.
- `ensemble_models.py:40, 52, 59` — three exception-class bodies. `class CustomError(Exception): pass`. Fine.
- `attribution.py:205` — exception suppression. Fine, defensive.
- `background_trainer.py:243, 486` — exception suppression in async paths. Fine.
- `brain_persistence.py:108, 309, 313` — exception suppression around legacy load paths. Fine.
- `diagnostic_scheduler.py:120` — silenced `tick.error_count` decrement. Fine.

None are half-implemented features. All are intentional. Good.

---

## live_engine.py is too big (5050 LOC)

The biggest single file in the codebase. 36 methods on `OrganismLiveEngine`. The hot tick path (`live_tick`) is ~1500 LOC by itself.

**Reading concerns:**
- Hard to navigate (which method does X?)
- Hard to test in isolation (one mock setup serves 36 methods)
- High merge-conflict surface
- Comments / dead code accumulate because moving them is scary

**The right structural fix (RC-3+ candidate):** split into:
- `live_engine.py` — orchestrator, stays small (~500 LOC)
- `entry_pipeline.py` — alpha → composite → gate → admit
- `exit_pipeline.py` — exit decisions, pyramider integration
- `position_manager.py` — open/closed positions, broker reconciliation
- `regime_pipeline.py` — regime detection + per-regime parameter selection
- `engine_state.py` — fingerprints, F4 forensic guards, brain handoff
- Each <800 LOC.

**Why not now**: this is a multi-day refactor. Risk of behavior change unless every line is moved verbatim. Phase C-1 (already documented) is logically adjacent; could be done together. RC-4 candidate.

**Mitigation in the meantime**: when adding new code to live_engine.py, don't pile more onto the bottom — add to the appropriate section, with a clear section header. Several recent additions (RC-1.5 fixes, shadow telemetry) followed this pattern; verify going forward.

---

## Test coverage gaps

Quick sample:
- `transfer_learning.py` — no tests visible (it's dormant)
- `attribution.py` — no tests visible
- `walk_forward.py` — no tests visible
- `promotion.py` — no tests visible
- `multi_timeframe.py` — no tests visible
- `feature_store.py` — no tests visible

Not surprising: dormant modules don't get test coverage. **But it means we can't safely delete them either** — no way to know what would break. A migration path:
1. Comment-out the imports
2. Run full test suite
3. If green: delete the module
4. If red: the import was actually load-bearing somewhere, fix that.

This is a Sunday afternoon item if you want it. ~30 minutes per dormant module to verify and delete. Could clean up ~3000 LOC.

---

## Nothing-burgers (things I checked that were FINE)

- No silent `try/except: pass` around critical paths
- No `eval()` or `exec()` of user input
- No SQL string concatenation (we use ORM)
- No shell-injection patterns
- No globals being mutated from multiple threads
- No imports of `random` without seed (where determinism matters)
- F1-F4 brain-persistence hardening is intact and well-tested
- Drawdown-kill / governance / risk-budget paths are well-tested
- The hot tick path (entry decision) IS tested (gate logic, regime, ML inference, sizing)

---

## Findings ranked by priority

| Severity | Finding | Action |
|---|---|---|
| P3 | ~3,000 LOC of dormant modules (`transfer_learning`, `attribution`, `walk_forward`, `training`, `feature_store`, `multi_timeframe`, `promotion`) | Sunday cleanup: comment imports, run tests, delete if green |
| P3 | `is_exploration` field carries through all of brain persistence + live_engine but always False | ~50 LOC simplification, zero behavior change |
| P3 | "Phase 4.4 / 4.5 / 4.6" comments reference removed docs | Update or annotate comments |
| P2 | `live_engine.py` at 5050 LOC | RC-4 candidate: split into 6 modules |
| P0 (anti-finding) | F1-F4 hardening | Solid. Don't touch. |
| P0 (anti-finding) | Risk paths | Solid. Don't touch. |
| P1 (anti-finding) | RC-1.5 changes | Verified clean (this audit didn't find anything new) |

---

## Verdict

**The codebase is structurally clear** in the parts that run. The parts that don't run (~15% of organism LOC) are confusing rather than broken. None of the dormant modules pose a *risk* to the live path; they pose a *cognitive cost*.

The biggest single coherence win available: cleanup pass on the dormant modules + `is_exploration` plumbing. ~30 minutes of careful work for ~3,000 LOC removed. Pure clarity gain. No behavior change.

If you want, I can do that pass next. Otherwise it queues as Sunday work.
