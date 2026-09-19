# APR-8 Patch C Report

**Commit:** `93593a2` — fix(brain): walk_forward_gate reads authoritative learner.state.best_sharpe
**Status:** COMMITTED (not pushed, not deployed)

## Files changed
- `backend/organism/brain_persistence.py` — remove `_last_sharpe_decay_date` field, add `learner` kwarg to `walk_forward_gate`, remove `*= 0.95` decay mutation, prefer `learner.state.best_sharpe` over `_manifest` fallback.
- `backend/organism/live_engine.py` — `_save_brain` passes `learner=self.learner` to the gate.
- `tests/test_apr7_p0_p1_fixes.py` — drop the daily-decay persistence test; add tests for learner-authoritative read, no-mutation, manifest-fallback, and field-removed.

## Gate formula (verified from code)
`walk_forward_gate` computes `current_sharpe = mean(returns)/std(returns) * sqrt(252)` over the last N trades, then returns `should_save = (current_sharpe / best_sharpe) >= regression_threshold (0.95)`; if `best_sharpe <= 0` it always passes.

## Authoritative source verified
`backend/organism/continuous_learner.py:150` — `LearningState.best_sharpe: float = -np.inf`; updated monotonically at lines 397-398 (`if sharpe_proxy > self.state.best_sharpe: self.state.best_sharpe = sharpe_proxy`). Always a float (no None). Saved to `learning_state.json` and restored.

## Test results
- `tests/test_apr7_p0_p1_fixes.py` — **12 passed** in 1.07s
- Organism subset (`test_organism_live_engine.py test_organism_engine_scenarios.py test_multi_tick_state.py test_safety_invariants.py test_self_evolution.py`) — **107 passed** in 60.22s

## Hard-stop checks
- `_last_sharpe_decay_date` grep — only appears in historical docs/bundles and the test's "field removed" assertion. No live references.
- Gate return signature unchanged: `tuple[bool, str]`.
- `regression_threshold=0.95` default unchanged.
- No deploy, no restart, no touch of Patches A/B.
