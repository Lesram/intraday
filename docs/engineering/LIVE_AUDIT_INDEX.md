# Live Audit Index

Generated: 2026-05-04T08:26:22Z
PR: n/a
SHA: `bac86a65f3`
Branch: `codex/v13-root-fixes`
Scope: **backend_logic**
Change scope: `task` (`HEAD`)

## Changed files

| Category | Count | Files |
|----------|-------|-------|
| Backend | 1 | `backend/services/audit_service.py` |
| Organism | 0 | none |
| Tests | 1 | `tests/test_audit_chain_locking.py` |
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

- 1 backend runtime file(s) changed — require targeted verification
