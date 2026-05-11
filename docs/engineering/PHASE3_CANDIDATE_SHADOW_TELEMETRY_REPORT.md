# Phase 3 Candidate-Filter Shadow Telemetry Report

Generated: 2026-05-04
Branch: `codex/v13-phase2-expectancy`
Module: `backend/organism/candidate_shadow_telemetry.py`

## Verdict

Candidate-filter shadow telemetry is now available, but disabled by default.

This closes the Phase 3 blocker left by the fill-path replay: the platform now
has a runtime capture path for the two candidate filters that could not be
validated from stale cached bars. It does not block entries, reorder
candidates, change Kelly sizing, or submit orders. It only records matching
live-pipeline candidates when explicitly enabled.

## Runtime Switches

Disabled default:

```text
ORGANISM_CANDIDATE_FILTER_SHADOW_TELEMETRY_ENABLED=false
```

Default output path:

```text
ORGANISM_CANDIDATE_FILTER_SHADOW_TELEMETRY_PATH=organism_brain/candidate_filter_shadow_telemetry.jsonl
```

The runtime snapshot generator now includes both keys so audit artifacts can
show whether telemetry was actually enabled in a paper session.

## Captured Filters

The recorder writes JSONL rows for candidates matching:

- `conf_45_55`: `0.45 <= confidence < 0.55`
- `alpha_breakout_chop`: inferred `entry_source == "alpha+breakout"` while
  `regime == "chop"`

Each row includes tick, timestamp, symbol, regime, direction, confidence,
effective confidence, breakout score, predicted return, ranking score, inferred
entry source, and matched filter tags.

## Safety Properties

- The recorder is disabled unless explicitly enabled by env.
- The live-engine call happens after candidate filtering and before Kelly
  sizing.
- The telemetry block does not append candidates, call Kelly sizing, submit
  orders, or mutate gates.
- Write failures are logged and swallowed so telemetry cannot break a tick.

## Recommendation

Enable this only for paper shadow sessions when collecting Phase 3 evidence.
After at least one full liquid trading session, analyze the JSONL against
subsequent trade outcomes and fill-path bars before considering any live
no-entry gate.
