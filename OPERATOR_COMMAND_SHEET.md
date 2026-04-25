# OPERATOR COMMAND SHEET
**As of:** 2026-04-25 (Saturday)

## Current state
- **Live container:** `ce06d41` (verified by file-SHA forensics).
- **Repo HEAD:** `eb90fa3` — fully tested, ready to deploy.
- **Worktree:** clean. Audit trail archived to `docs/engineering/audits/archive/2026-04/`.
- **Brain:** gen 124, 396 trades, healthy, manifest+learning_state coherent.
- **Equity:** $111,531 paper, −0.23% from peak, no halts in 12 sessions.
- **Live-window expectancy:** −$0.59/trade. Stable but unprofitable.

## The decision is already made
- ✅ `eb90fa3` is the next release candidate. No fork in the road.
- ✅ Exp 4 IS in the bundle. Decision made.
- ✅ Hardening (G1/G2/G3, H1/H2, notional cap, daily max-loss, alert wiring, drawdown-kill canonical, H5 governance, compose alignment) IS in the bundle.

## The next deploy
**`eb90fa3`. Monday 2026-04-27. 8:30–9:00 ET. Operator at keyboard for first 30 min.**

Run-book: `MONDAY_DEPLOY_eb90fa3.md` at repo root.

## What to observe (5–10 sessions post-deploy)
| Metric | Baseline (ce06d41, 12 sessions) | Week-1 target |
|---|---|---|
| Pyramid_cut share | 31.3% | **≤ 22%** |
| Trailing_stop avg PnL | −$0.60 | **≥ $0** |
| Win rate | 31.3% | **≥ 35%** |
| Expectancy | −$0.59 | **≥ −$0.30** |
| Halt / freeze events | 0 | 0 |
| Alert wiring delivery on synthetic test | n/a | 100% |

## What must be true before real-money (Stage 1)
1. `eb90fa3` deployed clean
2. 5+ clean post-deploy sessions
3. Notional cap reject path verified live
4. Daily max-loss kill verified live
5. Alert wiring delivery verified
6. Drawdown-kill startup validator log line confirmed
7. No regression in execution latency / brain save / ML retrain
8. Expectancy ≥ neutral over 5 sessions
9. G1/G2/G3 reduces pyramid_cut share ≥30% relative
10. Exp 4 reduces trailing-stop giveback measurably
11. Brain backup rotation in place
12. Stage-1 risk parameter set documented (capital, per-trade cap %, daily max-loss %, max positions, universe trim)

All twelve must be green. Earliest realistic Stage-1 cutover: **2026-05-12 (Mon)**.

## What NOT to do this window
- No new audits / master plans / comprehensive reviews.
- No code changes during observation.
- No real capital movements.
- No remote pushes without explicit confirmation.
- No third-party voice added — close, don't expand, the review surface.

## Single source of truth references
- Master pack: `WEEKEND_STATE_AND_STRATEGY_PACK.md`
- PR review bundle: `docs/engineering/reviews/pr-deploy-eb90fa3-eb90fa3/`
- Preflight artifacts: `artifacts/deploy_preflight_eb90fa3/`
- Brain backup: `artifacts/deploy_preflight_eb90fa3/organism_brain_backup_pre_eb90fa3_20260425/`
- Monday run-book: `MONDAY_DEPLOY_eb90fa3.md`
