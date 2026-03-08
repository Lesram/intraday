# Live Audit Index

Generated: 2026-03-08T05:26:08Z
PR: PR #3
SHA: `c3a80fef27`
Branch: `control-plane-operationalize`

## Changed files

| Category | Count | Files |
|----------|-------|-------|
| Backend | 0 | none |
| Organism | 0 | none |
| Tests | 1 | `tests/test_organism_integration_smoke.py` |
| Docs | 2 | `docs/engineering/CONTROL_PLANE.md`, `docs/engineering/LIVE_AUDIT_INDEX.md` |

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

## Artifact pack (committed)

| Artifact | Path |
|----------|------|
| Runtime config snapshot | `docs/engineering/pr3_artifacts/runtime_config_snapshot.json` |
| Task report | `docs/engineering/pr3_artifacts/task_report.json` |
| Test summary | `docs/engineering/pr3_artifacts/test_summary.json` |
| Replay summary | `docs/engineering/pr3_artifacts/replay_summary.json` |
| Grep assertions | `docs/engineering/pr3_artifacts/grep_assertions.json` |

## Test results

- **Test suites (6)**: 165 passed, 0 failed
- **Replay tests**: 26 passed, 0 failed
- **Grep assertions**: 15/15 pass

## Reference paths

- Latest improve doc: `docs/architecture/improve9.md`
- Latest trading report: `none`
- Runtime snapshot: `docs/engineering/pr3_artifacts/runtime_config_snapshot.json`
- Grep assertions: `docs/engineering/pr3_artifacts/grep_assertions.json` (status: **pass**)

## Open risks

- None identified
