# Live Audit Index

Candidate validation only: this index and its resolved values describe the isolated
`3fd6a3f71f` source build. They do not describe the installed paper process. The
network-denied live snapshot is explicitly unreachable. Deployment remains PR #17
until a separate accepted activation; see `artifacts/task_report.json` and
`artifacts/operations_evidence/final_validation.json` for current evidence.

Generated: 2026-09-19T23:52:01Z
PR: n/a
SHA: `3fd6a3f71f`
Branch: `codex/operations-evidence-integrity`
Scope: **backend_logic**
Change scope: `base` (`ffc0e5c0595bb21e1c71f0ba7e5d6f55af7fc189...HEAD`)

## Changed files

| Category | Count | Files |
|----------|-------|-------|
| Backend | 7 | `backend/organism/brain_persistence.py`, `backend/organism/close_accounting.py`, `backend/organism/continuous_learner.py`, `backend/organism/entry_evidence.py`, `backend/organism/live_engine.py`, `backend/organism/live_engine_fills.py`, `backend/organism/replay_simulator.py` |
| Organism | 7 | `backend/organism/brain_persistence.py`, `backend/organism/close_accounting.py`, `backend/organism/continuous_learner.py`, `backend/organism/entry_evidence.py`, `backend/organism/live_engine.py`, `backend/organism/live_engine_fills.py`, `backend/organism/replay_simulator.py` |
| Scripts | 3 | `scripts/ops/paper_daily_evidence.py`, `scripts/ops/standdown_session_row.py`, `scripts/runtime/write_runtime_snapshot.py` |
| CI | 1 | `.github/workflows/paper-readiness.yml` |
| Tests | 10 | `tests/test_entry_evidence.py`, `tests/test_live_engine_fill_accounting.py`, `tests/test_organism_engine_scenarios.py`, `tests/test_organism_live_engine.py`, `tests/test_paper_daily_evidence.py`, `tests/test_pending_close_accounting.py`, `tests/test_replay_close_accounting.py`, `tests/test_runtime_snapshot_auth.py`, `tests/test_standdown_session_row.py`, `tests/test_walkforward_persistence.py` |
| Docs | 3 | `docs/architecture/mapss.md`, `docs/engineering/OPERATIONS_EVIDENCE_RELEASE.md`, `docs/runbooks/PAPER_DAILY_EVIDENCE.md` |

## Resolved constants — candidate validation environment

Source: `resolved_config_snapshot.json`

```json
{
  "timeframe": "1Day",
  "max_positions": 8,
  "alpha_top_n": 5,
  "learning_mode_threshold": 200,
  "evolution_freeze": 300,
  "horizon_timeout_bars": 18,
  "drawdown_kill_pct": 0.05,
  "exploration_enabled": false,
  "bar_boundary_entry_only": true,
  "candidate_filter_shadow_telemetry_enabled": false,
  "strategy_evidence_telemetry_enabled": false,
  "phase9_shadow_engines_enabled": false
}
```

## Snapshot files

- Defaults: `artifacts/runtime_defaults_snapshot.json`
- Resolved config: `artifacts/resolved_config_snapshot.json`
- Live process: `artifacts/live_process_runtime_snapshot.json`

## Reference paths

- Latest improve doc: `docs/architecture/improve9.md`
- Latest trading report: `docs/trading_report_2026.md`
- Grep assertions: `artifacts/grep_assertions.json` (status: **pass**)
- Semantic invariants: `tests/test_semantic_invariants.py`

## Open risks

- 7 organism file(s) changed — require replay verification
