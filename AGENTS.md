# Intra agent operating contract

This repository runs a paper-traded intraday equity system. Every agent must treat trading-safety, state integrity, and reproducibility as first-class constraints.

## Objectives
- Improve risk-adjusted expectancy, not trade count for its own sake.
- Keep learning mode simple and auditable.
- Never change live-trading behavior without tests, replay evidence, and a runtime-config snapshot.

## Authority model
- Codex / ChatGPT: architecture, spec, review, acceptance.
- Claude Code: implementation, refactor, targeted tests, CI repair.
- GitHub Actions: neutral referee.
- Optional OpenHands: orchestration only, never the source of truth.

## Mandatory PR workflow
Changes to these paths MUST go through a pull request — never push directly to main:
- `backend/**`
- `tests/**`
- `docs/architecture/**`
- `docker-compose*.yml`
- `.env*`

Small documentation fixes outside these paths may be committed directly.

## Repo-critical surfaces
Highest-risk files are under:
- `backend/organism/`
- `backend/integrations/`
- `backend/infra/`
- `backend/risk/`
- `backend/brokers/`
- `docs/architecture/`
- `tests/test_organism_*`
- `tests/test_algorithm_improvements.py`
- `tests/test_multi_tick_state.py`
- `tests/test_safety_invariants.py`
- `tests/test_replay_simulator.py`

## Trading invariants
Agents must preserve these invariants unless the task explicitly changes them:
- No live exploration execution path.
- Learning mode ignores ML for main-book ranking/confidence/sizing.
- Learning mode uses fixed ATR-dollar risk sizing, not Kelly.
- Evolution strategy params stay frozen until at least 300 clean post-reset trades.
- Entry path for alpha and pure breakout must share the same hard safety gates.
- EOD entry block and flatten must remain active.
- Runtime config must be snapshotted and included in reports.
- No secrets committed to the repo.

## Required process for every code task
1. Read the task and restate scope in a machine-readable plan.
2. Identify affected files and tests before editing.
3. Make the smallest coherent change set that fixes the target issue.
4. Run targeted tests for affected files.
5. Run safety/regression tests for organism state, exits, sizing, and replay.
6. Generate the artifact pack: `python scripts/ci/generate_artifacts.py full`
7. Generate audit index: `python scripts/ci/generate_audit_index.py`
8. If any invariant changes, update `docs/architecture/mapss.md` and the runtime snapshot generator.

## Required artifact pack
Every PR and post-close run must produce these under `artifacts/`:

| Artifact | Generator | Purpose |
|----------|-----------|---------|
| `task_report.json` | `generate_artifacts.py` | SHA, branch, files changed, test results, risks, follow-ups |
| `runtime_config_snapshot.json` | `write_runtime_snapshot.py` | All live organism constants — diff against docs |
| `changed_files.json` | `generate_artifacts.py` | Categorized list of changed paths |
| `test_summary.json` | `generate_artifacts.py` | Per-suite pass/fail counts |
| `replay_summary.json` | `generate_artifacts.py` | Replay test pass/fail + output tail |
| `grep_assertions.json` | `generate_artifacts.py` | Trading invariant grep checks |

Additionally: `docs/engineering/LIVE_AUDIT_INDEX.md` is regenerated with current SHA, changed files, live constants, and open risks.

## Required checks by path
### If files under `backend/organism/` change
Run at minimum:
- `pytest -q tests/test_organism_live_engine.py`
- `pytest -q tests/test_organism_engine_scenarios.py`
- `pytest -q tests/test_multi_tick_state.py`
- `pytest -q tests/test_safety_invariants.py`
- `pytest -q tests/test_replay_simulator.py`
- `pytest -q tests/test_self_evolution.py`

### If files under `backend/integrations/`, `backend/brokers/`, or reconciliation paths change
Run at minimum:
- `pytest -q tests/test_order_integrity_comprehensive.py`
- `pytest -q tests/test_position_reconciliation.py`
- `pytest -q tests/test_position_reconciliation_comprehensive.py`

### If config / env / deployment paths change
Run at minimum:
- `pytest -q tests/test_settings_comprehensive.py`
- `pytest -q tests/test_config_coordinator_comprehensive.py`
- `pytest -q tests/test_system_integration.py`

## Done means
A task is not done until all are true:
- Changed files are committed on a feature branch and PR is open.
- Required tests are green.
- No dead-code branch can still submit a live order.
- Runtime config snapshot matches actual live constants.
- Relevant docs are updated.
- The full artifact pack is generated and attached to the PR.
- Audit index is current.

## Reporting format
Every task must output a JSON report at `artifacts/task_report.json` with:
- `task_id`
- `summary`
- `sha`
- `branch`
- `files_changed`
- `commands`
- `tests_passed`
- `tests_failed`
- `runtime_behavior_changed`
- `docs_updated`
- `risks`
- `follow_ups`

## Deploy gates for paper trading
A PR that changes organism logic must not merge unless:
- required tests pass,
- replay / simulation artifact exists,
- runtime-config snapshot exists,
- grep assertions pass (no invariant violations),
- at least one reviewer approves,
- no secret scan failures,
- no diff between runtime snapshot and documented live constants unless explicitly acknowledged.

## Post-close KPI auto-issue
The `paper-postclose-audit` workflow runs daily at 22:15 UTC and automatically opens a GitHub issue when:
- Any test suite fails
- Replay tests fail
- Trading invariant grep checks fail
- Runtime snapshot cannot be generated
- Exploration is enabled (should always be disabled)

## FROZEN-SURFACE REGIME (from 2026-07-29)

The platform is DONE and the repo is **research-only**. The decision surface is
FROZEN at `FROZEN_AT=2026-07-07T20:36:49Z` (`artifacts/phase2/param_freeze.json`;
check with `python scripts/phase2_freeze.py --verify` — run it after ANY change,
it must exit 0). Any change to the six hashed functions (entry direction, exit
engine, regime detector, Kelly sizer, `_live_tick_inner`, selector routing),
`exit_env`, `regime_policy`, `routing_data_env` (including the data feed), or
`strategy_config` RESETS the forward verdict clock and requires **Marsel's
explicit sign-off first** — never as a side effect.

Allowed WITHOUT sign-off:
- Session rows for the stand-down table, generated at session close only:
  `python scripts/ops/standdown_session_row.py`
- Research scripts under `scripts/research/` (read-only vs the platform; see
  its README)
- NEW strategy modules entering through the Strategy registry, **shadow-first
  under Rule A** — no live capital until the pre-registered gate passes
- Docs and reports

Explicitly PARKED until post-verdict (do not pick these up):
- `live_engine.py` decomposition
- OrganismBrain env-aware default (flagged chip)
- CI trio cleanup (frontend npm-audit, bandit, Quality Summary)
- Any tuning of frozen parameters

Certification chain: the three red-team verdicts under `reports/`
(`REDTEAM_ROUND2_REMEDIATION_VERDICT_2026-07-24.md`,
`REDTEAM_ROUND3_CLOSEOUT_CERTIFICATION_2026-07-24.md`, and the round-1 verdict
recorded in `OPS_WORKORDER_COMPLETION_2026-07-23.md`).
