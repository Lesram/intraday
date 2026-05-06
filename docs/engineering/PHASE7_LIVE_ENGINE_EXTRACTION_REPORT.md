# Phase 7.2 Live Engine Extraction Report

Generated: 2026-05-06 UTC
Branch: `codex/v13-phase2-expectancy`

## Scope

This slice completed the first behavior-preserved live-engine extraction from
the Phase 7 roadmap. It did not promote or alter trading strategy behavior.

The primary target was the candidate evidence fanout immediately before sizing
inside `_live_tick_inner`. While validating the W100 live-tick LOC ceiling, two
additional nearby observational/housekeeping blocks were extracted so the method
falls below the pinned ceiling without raising it.

## Extracted Helpers

| Helper | Responsibility | Live behavior |
|--------|----------------|---------------|
| `_record_candidate_evidence` | Sends the same pre-sizing candidates to Phase 5 candidate-filter shadow telemetry and Phase 6 strategy evidence telemetry. | Observability-only; exceptions are logged and swallowed. |
| `_record_signal_activity` | Appends the first 10 signal activity events to the tick result. | Dashboard/operator visibility only. |
| `_record_sizer_rejections` | Copies sizer rejection counts into `_last_gate_rejections`. | Telemetry only. |
| `_apply_intraday_seasonality_filter` | Applies the pre-existing late-session intraday allocation reduction in place. | Same sizing adjustment as before; now isolated and tested. |

## Complexity Delta

| Measurement | Before P7.2 | After P7.2 |
|-------------|-------------|------------|
| `_live_tick_inner` LOC | 2802 at P7.0 baseline | 2741 |
| W100 ceiling | 2750 | PASS |
| Strategy behavior changed | No | No |

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

## Verification

Focused checks:

- `pytest -q tests/test_phase3_candidate_shadow_telemetry.py --timeout=30`
- `pytest -q tests/test_v13_w100_live_tick_coverage.py --timeout=30`

Required organism checks:

- `pytest -q tests/test_organism_live_engine.py --timeout=30`
- `pytest -q tests/test_organism_engine_scenarios.py --timeout=30`
- `pytest -q tests/test_multi_tick_state.py tests/test_safety_invariants.py --timeout=30`
- `pytest -q tests/test_self_evolution.py --timeout=30`
- `pytest -q tests/test_replay_simulator.py --timeout=30`

Repo gates:

- `scripts/ci/lint_ratchet.py`
- `scripts/ci/verify_findings_ledger.py`
- `scripts/ci/forbid_marker_only_critical_high.py`
- `scripts/ci/check_migrations.py`

## Next P7.2 Slice

The next extraction should isolate a `SafetyGateResult` or equivalent from the
entry blocker/gate region. That slice is higher risk than telemetry fanout
because it touches capital-impacting pass/block decisions, so it should start
with pre-existing behavioral tests or new tests before code movement.

