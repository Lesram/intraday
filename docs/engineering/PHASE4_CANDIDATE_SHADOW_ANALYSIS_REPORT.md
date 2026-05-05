# Phase 4 Candidate Shadow Analysis Report

Generated: 2026-05-05 UTC
Branch: `codex/v13-phase2-expectancy`
Tool: `scripts/phase4_candidate_shadow_analysis.py`

## Verdict

The analyzer is ready, but there is no live shadow evidence yet.

The current telemetry path has `0` rows, so the candidate filters from Phase 3
remain unvalidated in production-like flow. This is not a regression; it means
candidate-filter telemetry has not been enabled for a liquid paper session or no
matching rows were written.

## Evidence Command

```bash
./venv/bin/python scripts/phase4_candidate_shadow_analysis.py
```

Outputs:

- `artifacts/phase4_candidate_shadow_analysis/summary_candidate_shadow_analysis.json`
- `artifacts/phase4_candidate_shadow_analysis/candidate_shadow_filter_summary.csv`

## Results

| Metric | Value |
| --- | ---: |
| Total rows | `0` |
| Valid events | `0` |
| Invalid rows | `0` |
| Filters observed | `0` |
| Recommendation | `await_live_shadow_session` |

## Promotion Discipline

The analyzer requires at least `30` events per filter and at least `20` outcome
events per filter before it will mark a filter eligible for replay review. It
still does not allow live promotion; replay and a live shadow session with
outcome joins are separate requirements.

## Recommendation

For the next liquid paper session, enable:

```text
ORGANISM_CANDIDATE_FILTER_SHADOW_TELEMETRY_ENABLED=true
```

Keep it as telemetry only. After the session, run this analyzer, then join rows
to fill/outcome evidence before considering any no-entry gate.
