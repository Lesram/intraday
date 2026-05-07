# Live Audit Index

Generated: 2026-05-07T01:09:35Z
PR: PR #6
SHA: `01c6e52a40`
Branch: `codex/v13-phase2-expectancy`
Scope: **backend_logic**
Change scope: `working-tree` (`HEAD+working-tree`)

## Changed files

| Category | Count | Files |
|----------|-------|-------|
| Backend | 1 | `backend/api/routes/data_integrity_health.py` |
| Organism | 0 | none |
| Scripts | 0 | none |
| Tests | 1 | `tests/test_v13_w95_data_integrity.py` |
| Docs | 1 | `docs/engineering/LIVE_AUDIT_INDEX.md` |

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
