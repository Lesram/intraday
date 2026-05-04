# Live Audit Index

Generated: 2026-05-04T21:04:33Z
PR: n/a
SHA: `9f4639deec`
Branch: `codex/v13-phase2-expectancy`
Scope: **backend_logic**
Change scope: `task` (`HEAD`)

## Changed files

| Category | Count | Files |
|----------|-------|-------|
| Backend | 3 | `backend/api/routes/strategy_health.py`, `backend/organism/brain_persistence.py`, `backend/organism/strategy_attribution.py` |
| Organism | 2 | `backend/organism/brain_persistence.py`, `backend/organism/strategy_attribution.py` |
| Tests | 1 | `tests/test_phase2_strategy_attribution.py` |
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

- 2 organism file(s) changed — require replay verification
