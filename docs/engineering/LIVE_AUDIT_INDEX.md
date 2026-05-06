# Live Audit Index

Generated: 2026-05-06T05:45:07Z
PR: PR #6
SHA: `2539975d49`
Branch: `codex/v13-phase2-expectancy`
Scope: **backend_logic**
Change scope: `working-tree` (`HEAD+working-tree`)

## Changed files

| Category | Count | Files |
|----------|-------|-------|
| Backend | 2 | `backend/organism/live_engine.py`, `backend/organism/replay_simulator.py` |
| Organism | 2 | `backend/organism/live_engine.py`, `backend/organism/replay_simulator.py` |
| Scripts | 0 | none |
| Tests | 2 | `tests/test_replay_simulator.py`, `tests/test_wave40_fixes.py` |
| Docs | 1 | `docs/engineering/PHASE7_LIVE_ENGINE_EXTRACTION_REPORT.md` |

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
