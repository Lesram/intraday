# Live Audit Index

Generated: 2026-03-08T06:33:26Z
PR: PR #3
SHA: `a79694b58e`
Branch: `control-plane-operationalize`

## Changed files

| Category | Count | Files |
|----------|-------|-------|
| Backend | 0 | none |
| Organism | 0 | none |
| Tests | 4 | `tests/test_decision_telemetry.py`, `tests/test_multi_tick_state.py`, `tests/test_organism_integration_smoke.py`, `tests/test_self_evolution.py` |
| Docs | 8 | `docs/architecture/mapss.md`, `docs/engineering/CONTROL_PLANE.md`, `docs/engineering/LIVE_AUDIT_INDEX.md`, `docs/engineering/pr3_artifacts/grep_assertions.json`, `docs/engineering/pr3_artifacts/replay_summary.json`, `docs/engineering/pr3_artifacts/runtime_config_snapshot.json`, `docs/engineering/pr3_artifacts/task_report.json`, `docs/engineering/pr3_artifacts/test_summary.json` |

## Live constants

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
  "bar_boundary_entry_only": true
}
```

## Reference paths

- Latest improve doc: `docs/architecture/improve9.md`
- Latest trading report: `none`
- Runtime snapshot: `artifacts/runtime_config_snapshot.json`
- Grep assertions: `artifacts/grep_assertions.json` (status: **pass**)

## Open risks

- None identified
