# Phase 4 Shadow Advancement Plan

Generated: 2026-05-05 UTC
Branch: `codex/v13-phase2-expectancy`

## Operating Rule

Phase 4 is shadow-only. Its job is to turn Phase 3 evidence into auditable
model and telemetry machinery without changing live ranking, confidence,
sizing, exits, or order submission.

Live promotion is explicitly out of scope for this phase. A candidate can only
graduate from Phase 4 into a later promotion discussion if it has:

- Offline evidence against the same cached bars and train/validation split.
- Replay evidence that includes fills, slippage, sizing, exits, and opportunity
  cost.
- At least one liquid paper-trading shadow session with outcome joins.
- A runtime-config snapshot proving shadow switches and live constants.

## Phase 4 Scope

Completed in this phase:

- `scripts/phase4_shadow_target_model.py` trains offline classifiers for the
  current `close_return_h1` target and the Phase 3 `close_return_h5` candidate.
- `scripts/phase4_candidate_shadow_analysis.py` summarizes runtime
  candidate-filter shadow telemetry and refuses promotion without live shadow
  samples and outcomes.
- Focused tests cover current/past-only features, temporal splits, proxy
  metrics, live-promotion blocking, missing telemetry files, invalid JSONL, and
  outcome summaries.
- Reports:
  - `docs/engineering/PHASE4_SHADOW_TARGET_MODEL_REPORT.md`
  - `docs/engineering/PHASE4_CANDIDATE_SHADOW_ANALYSIS_REPORT.md`

Not completed in this phase by design:

- No production ML target change.
- No candidate-filter no-entry gate.
- No runtime enablement of candidate-filter shadow telemetry.
- No changes under `backend/organism/`, broker, risk, or order paths.

## Promotion Gates

The target-model lane uses these gates before even calling a candidate
shadow-worthy:

- Candidate validation samples must meet the floor.
- Candidate balanced accuracy must beat current by at least `0.03`.
- Candidate selected proxy mean bps must beat current by at least `1.0`.
- Live promotion remains blocked regardless of offline results until replay and
  live shadow evidence exist.

The candidate-filter telemetry lane uses these gates:

- Each filter needs at least `30` live shadow events.
- Each filter needs at least `20` events with outcome fields.
- Even then, the only allowed recommendation is replay review, not live
  promotion.

## Evidence Commands

```bash
./venv/bin/python scripts/phase4_shadow_target_model.py
./venv/bin/python scripts/phase4_candidate_shadow_analysis.py
./venv/bin/python -m pytest -q tests/test_phase4_shadow_target_model.py tests/test_phase4_candidate_shadow_analysis.py --timeout=30
```

## Current Verdict

Phase 4 is complete as a shadow evidence layer, not as a live-profit change.
The five-bar model remains a research candidate, but it failed the balanced
accuracy gate and must not be promoted. Candidate-filter analysis is ready, but
there are currently no shadow telemetry rows to analyze.

## Phase 5 Follow-Up

Phase 5 has started the paper shadow evidence loop. See
`docs/engineering/PHASE5_SHADOW_EVIDENCE_LOOP_REPORT.md`.
