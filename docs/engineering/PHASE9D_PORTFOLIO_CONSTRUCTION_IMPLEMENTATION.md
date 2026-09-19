# Phase 9D Portfolio Construction Implementation

Date: 2026-05-10

## Verdict

Phase 9D is implemented as evidence-only portfolio construction. It does not change live ranking, sizing, order placement, gates, promotion state, or runtime flags.

The current generated verdict is intentionally `portfolio_authorized=false`: there are no Phase 9 strategy league rows with portfolio-eligible evidence yet. Replay-eligible evidence is not enough for portfolio risk budgets.

## What Changed

- Added `backend/organism/evidence/portfolio_construction.py`.
- Added `scripts/phase9d_portfolio_construction.py`.
- Added focused tests in `tests/test_phase9d_portfolio_construction.py`.
- Documented the Phase 9D gate in `docs/architecture/mapss.md`.

## Phase 9D Gate

A strategy can receive an advisory portfolio allocation only after all of these are true:

- Verdict is portfolio-eligible, such as `micro_paper_eligible` or stronger; `replay_eligible` remains blocked.
- Sample size meets the portfolio threshold.
- Profit factor is at least `1.20`.
- Average R is positive.
- Same-symbol, random-null, and delayed-entry alpha are all positive.
- Symbol and session concentration are inside limits.
- Portfolio has at least two validated strategies from at least two independent strategy families.
- Pairwise strategy correlation is at or below `0.75`.
- Weighted beta is at or below `0.35` in absolute value.

## Current Output

The generated artifact is:

- `artifacts/phase9d_portfolio_construction/phase9d_portfolio_summary.json`
- `artifacts/phase9d_portfolio_construction/PHASE9D_PORTFOLIO_CONSTRUCTION_REPORT.md`

Current blockers:

- `not_enough_validated_strategies`
- `not_enough_independent_strategy_families`

Required next step:

- `collect_and_validate_more_strategy_families`

## Safety Boundary

The script and module are advisory. Even if a future evidence set produces `portfolio_authorized=true`, live promotion remains `false` and must still go through human review, replay, micro-paper controls, runtime config snapshots, and deploy gates before any live behavior changes.
