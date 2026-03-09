# Live Audit Index

Generated: 2026-03-09T00:34:45Z
PR: PR #3
SHA: `1756a1547c`
Branch: `control-plane-operationalize`
Scope: **backend_logic**

## Changed files

| Category | Count | Files |
|----------|-------|-------|
| Backend | 2 | `backend/organism/kelly_sizer.py`, `backend/organism/live_engine.py` |
| Organism | 2 | `backend/organism/kelly_sizer.py`, `backend/organism/live_engine.py` |
| Tests | 5 | `tests/test_decision_telemetry.py`, `tests/test_multi_tick_state.py`, `tests/test_organism_integration_smoke.py`, `tests/test_self_evolution.py`, `tests/test_semantic_invariants.py` |
| Docs | 32 | `docs/architecture/mapss.md`, `docs/engineering/CONTROL_PLANE.md`, `docs/engineering/LIVE_AUDIT_INDEX.md`, `docs/engineering/baseline_reviews/baseline-3d7f7c1/BASELINE_AUDIT_CONTEXT.md`, `docs/engineering/baseline_reviews/baseline-3d7f7c1/CODEBASE_INDEX.md`, `docs/engineering/baseline_reviews/baseline-3d7f7c1/backend_file_inventory.json`, `docs/engineering/baseline_reviews/baseline-3d7f7c1/config_file_inventory.json`, `docs/engineering/baseline_reviews/baseline-3d7f7c1/core_backend_snapshot.tar.gz`, `docs/engineering/baseline_reviews/baseline-3d7f7c1/docs_file_inventory.json`, `docs/engineering/baseline_reviews/baseline-3d7f7c1/full_backend_tree.txt` |

## Live constants

Source: `resolved_config_snapshot.json`

```json
{
  "timeframe": "1Min",
  "max_positions": 15,
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

- 2 organism file(s) changed — require replay verification
