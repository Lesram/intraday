# Phase 7.2 Live Engine Extraction Report

Generated: 2026-05-06 UTC
Branch: `codex/v13-phase2-expectancy`

## Scope

This report covers behavior-preserved live-engine extraction work from the
Phase 7 roadmap. It did not promote or alter trading strategy behavior.

The first slice targeted candidate evidence fanout immediately before sizing
inside `_live_tick_inner`. While validating the W100 live-tick LOC ceiling, two
additional nearby observational/housekeeping blocks were extracted so the method
falls below the pinned ceiling without raising it.

The second slice isolated the earliest entry-blocker decision boundary:
governance halt, warmup, and stale-data entry blocks. This is a capital-impacting
gate, so the work converted Wave 40 marker/source tests into direct behavioral
checks before expanding the gate run.

## Extracted Helpers

| Helper | Responsibility | Live behavior |
|--------|----------------|---------------|
| `_record_candidate_evidence` | Sends the same pre-sizing candidates to Phase 5 candidate-filter shadow telemetry and Phase 6 strategy evidence telemetry. | Observability-only; exceptions are logged and swallowed. |
| `_record_signal_activity` | Appends the first 10 signal activity events to the tick result. | Dashboard/operator visibility only. |
| `_record_sizer_rejections` | Copies sizer rejection counts into `_last_gate_rejections`. | Telemetry only. |
| `_apply_intraday_seasonality_filter` | Applies the pre-existing late-session intraday allocation reduction in place. | Same sizing adjustment as before; now isolated and tested. |
| `SafetyGateResult` | Decision object for hard pass/block safety gates. | Data carrier only; no side effects. |
| `_evaluate_entry_blocker_gate` | Evaluates governance halt, warmup, and stale-data entry blockers without mutating tick state. | Same ordering as before: governance halt > prior block preservation > warmup > stale data. |

## Complexity Delta

| Measurement | Before P7.2 | After P7.2 |
|-------------|-------------|------------|
| `_live_tick_inner` LOC | 2802 at P7.0 baseline | 2741 |
| W100 ceiling | 2750 | PASS |
| Strategy behavior changed | No | No |

Safety-gate helper sizes after the second slice:

| Helper | LOC |
|--------|-----|
| `_evaluate_entry_blocker_gate` | 32 |
| `_stage_check_entry_blockers` | 23 |

## Behavioral Tests Added

- Candidate evidence fanout records to both recorders without mutating
  candidates.
- Candidate evidence fanout is a no-op when recorders are disabled.
- Failure in one candidate evidence recorder does not block the other recorder.
- Signal activity helper records only the first ten candidates and preserves
  message content.
- Sizer rejection helper preserves existing gate telemetry and adds sizer
  rejection counts.
- Intraday seasonality helper reduces late-session sizes and no-ops outside the
  late-session window.
- Entry-blocker gate allows clean state without mutating engine flags.
- Governance halt wins over simultaneous warmup and stale-data conditions.
- Warmup wins over stale data when governance is not halted.
- Stale data blocks entries only after warmup has cleared.
- Stage helper applies governance halt to `LiveTickResult` errors/activity.
- Prior entry blocks remain preserved unless governance halt overrides.

## Additional Test Hygiene Cleanup

The combined organism/replay gate exposed a separate test-order failure:
`ReplayEngine.__init__` left `ORGANISM_REPLAY_MODE=1` in process environment,
causing later scheduler tests to refuse construction with the production brain
path. The replay safety guard remains intact, but the env flag is now set only
while `ReplayEngine.run` constructs `OrganismLiveEngine`, then restored
immediately. A regression test locks constructor-time non-pollution.

## Verification

Focused checks:

- `pytest -q tests/test_phase3_candidate_shadow_telemetry.py --timeout=30`
- `pytest -q tests/test_v13_w100_live_tick_coverage.py --timeout=30`
- `pytest -q tests/test_wave40_fixes.py --timeout=30`
- `pytest -q tests/test_replay_simulator.py::test_replay_engine_constructor_does_not_pollute_replay_mode --timeout=30`

Required organism checks:

- `pytest -q tests/test_v13_w100_live_tick_coverage.py tests/test_organism_live_engine.py tests/test_organism_engine_scenarios.py tests/test_multi_tick_state.py tests/test_safety_invariants.py tests/test_replay_simulator.py tests/test_self_evolution.py --timeout=30`
  - Result after replay env fix: 148 passed, 3 warnings.

Repo gates:

- `scripts/ci/lint_ratchet.py`
- `scripts/ci/verify_findings_ledger.py`
- `scripts/ci/forbid_marker_only_critical_high.py`
- `scripts/ci/check_migrations.py`

## Next P7.2 Slice

The next extraction should stay outside order submission first: isolate another
decision-only block with direct behavioral tests, then run the same organism and
replay gates before considering deeper entry/exit loop movement.
