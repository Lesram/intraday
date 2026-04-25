# LIVE AUDIT INDEX — pr-deploy-eb90fa3-eb90fa3

**Target deploy commit:** `eb90fa369e2739f77c7b1789aa47bd8b83184912`
**Live commit at audit time:** `ce06d41`
**Bundle composed:** 2026-04-25 (Saturday weekend prep)

This bundle accompanies the Monday-pre-open deploy of `eb90fa3` per AGENTS.md two-step review convention (commit + export).

## Composition

`eb90fa3` is `ce06d41` + 8 commits, +1144 / −13 LOC, 14 new tests:

| # | Commit | Subject | Category |
|---|---|---|---|
| 1 | `15cc0a4` | G1 exit-level restore warning + G2 cooldown-on-success-only + G3 NaN pyramid guard | Mechanical |
| 2 | `b97f903` | Exp 4 — chop trailing-stop giveback control (5.0× ATR widen, default) | Strategy |
| 3 | `679ffd2` | H1 production risk-budget cap + H2 feature drift guard | Real-money |
| 4 | `bb5cbb5` | Per-trade notional cap + daily max-loss circuit breaker | Risk |
| 5 | `33d6138` | Slack/webhook alert wiring | Ops |
| 6 | `c306074` | H5 settings API enforces frozen/halted state | Governance |
| 7 | `0ac6e2d` | Canonical drawdown-kill resolution + startup validator | Governance |
| 8 | `eb90fa3` | Compose drawdown-kill fallback aligned with code default | Config |

## Files in this bundle

| File | Purpose |
|---|---|
| `WEEKEND_STATE_AND_STRATEGY_PACK.md` | master weekend audit (single source of truth) |
| `CURRENT_LIVE_STATE_SNAPSHOT.md` | live container truth, file-SHA forensic identification |
| `RC_DEPLOY_READINESS_RECHECK.md` | full preflight checklist + deploy reasoning |
| `MASTER_ISSUE_LEDGER_REFRESH.md` | full P0/P1/P2/P3 ledger |
| `PREFLIGHT_SUMMARY.md` | preflight test/replay/spec-drift results |
| `test_summary.txt` | full pytest output (7857 passed, 37 pre-existing flakes, 43/43 changeset tests pass) |
| `replay_summary.txt` | replay regression (25/26 pass; 1 known throttle flake) |
| `spec_drift.txt` | spec-drift CI: no drift detected |
| `commits_ce06d41_to_eb90fa3.txt` | 8-commit chain |
| `diffstat_ce06d41_to_eb90fa3.txt` | file-level diff stat |
| `manifest.json` | brain manifest at audit time |
| `learning_state.json` | learning state at audit time |
| `resolved_config_snapshot.json` | resolved runtime config at audit time |
| `runtime_defaults_snapshot.json` | runtime defaults at audit time |
| `live_process_runtime_snapshot.json` | live container runtime state at audit time |

## Deploy gate

**GREEN.**

- Changeset tests: 43/43 ✅
- Replay regression: 25/26 (1 pre-existing flake, not changeset-related) ✅
- Spec drift: none ✅
- Brain backup: taken ✅
- Worktree clean: ✅
- Live commit verified: `ce06d41` (file-SHA forensic) ✅

## Recommended deploy

**Monday 2026-04-27, 8:30–9:00 ET**, operator at keyboard for first 30 minutes.

**Rollback path:** `organism_brain_backup_pre_eb90fa3_20260425/` (in `artifacts/deploy_preflight_eb90fa3/`); revert container to `ce06d41`.

## Sign-off

This bundle was produced by Claude Opus 4.7 (1M context) in agent-led mode at the operator's authorization ("take the lead, 100%"). The deploy decision and the actual deploy execution remain with the operator.
