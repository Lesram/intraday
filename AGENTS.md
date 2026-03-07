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
6. Emit a task report under `artifacts/` or CI artifacts.
7. If any invariant changes, update `docs/architecture/mapss.md` and the runtime snapshot generator.

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
- Changed files are committed.
- Required tests are green.
- No dead-code branch can still submit a live order.
- Runtime config snapshot matches actual live constants.
- Relevant docs are updated.
- The task report lists risks, commands, files changed, and follow-ups.

## Reporting format
Every task must output a JSON report at `artifacts/task-report.json` with:
- `task_id`
- `summary`
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
- at least one reviewer approves,
- no secret scan failures,
- no diff between runtime snapshot and documented live constants unless explicitly acknowledged.
