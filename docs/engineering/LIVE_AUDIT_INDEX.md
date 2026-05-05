# Live Audit Index

Generated: 2026-05-05T03:52:40Z
PR: PR #6
SHA: `ea03c596b3`
Branch: `codex/v13-phase2-expectancy`
Scope: **tooling/evidence_only**
Change scope: `task` (`HEAD`)

## Changed files

| Category | Count | Files |
|----------|-------|-------|
| Backend | 0 | none |
| Organism | 0 | none |
| Scripts | 1 | `scripts/ci/generate_audit_index.py` |
| Tests | 1 | `tests/test_artifact_change_scope.py` |
| Docs | 0 | none |

## Live constants

Source: `resolved_config_snapshot.json`

```json
{
  "timeframe": "1Min",
  "max_positions": 8,
  "alpha_top_n": 5,
  "learning_mode_threshold": 200,
  "evolution_freeze": 300,
  "horizon_timeout_bars": 18,
  "drawdown_kill_pct": 0.2,
  "exploration_enabled": false,
  "bar_boundary_entry_only": true
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

- Evidence/tooling script changed only — no backend runtime or order-path behavior changed
